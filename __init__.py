#
# Rhythmweb - a web site for your Rhythmbox.
# Copyright (C) 2007 Michael Gratton.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

import cStringIO
import cgi
import fnmatch
import os
import sys
import time

def getfqdn(name=''):
      return name
import socket
socket.getfqdn=getfqdn

import math
from wsgiref.simple_server import WSGIRequestHandler
from wsgiref.simple_server import make_server

import gtk
import gobject

import rb
import rhythmdb

# try to load avahi, don't complain if it fails
try:
      import dbus
      import avahi
      use_mdns = True
except:
      use_mdns = False


class RhythmwebPlugin(rb.Plugin):

    def __init__(self):
          super(RhythmwebPlugin, self).__init__()

    def activate (self, shell):
          self.db = shell.props.db
          self.shell = shell
          self.player = shell.get_player()
          self.shell_cb_ids = (
                self.player.connect ('playing-song-changed',
                                     self._playing_entry_changed_cb),
                self.player.connect ('playing-changed',
                                     self._playing_changed_cb)
                )
          self.db_cb_ids = (
                self.db.connect ('entry-extra-metadata-notify',
                                 self._extra_metadata_changed_cb)
                ,)
          self.port = 8000
          self.server = RhythmwebServer('', self.port, self)
          self._mdns_publish()

    def deactivate(self, shell):
          self._mdns_withdraw()
          self.server.shutdown()
          self.server = None

          for id in self.shell_cb_ids:
                self.player.disconnect(id)

          for id in self.db_cb_ids:
                self.db.disconnect(id)

          self.player = None
          self.shell = None
          self.db = None

    def _mdns_publish(self):
          if use_mdns:
                bus = dbus.SystemBus()
                avahi_bus = bus.get_object(avahi.DBUS_NAME, avahi.DBUS_PATH_SERVER)
                avahi_svr = dbus.Interface(avahi_bus, avahi.DBUS_INTERFACE_SERVER)

                servicetype = '_http._tcp'
                servicename = 'Rhythmweb on %s' % (socket.gethostname())

                eg_path = avahi_svr.EntryGroupNew()
                eg_obj = bus.get_object(avahi.DBUS_NAME, eg_path)
                self.entrygroup = dbus.Interface(eg_obj,
                                                 avahi.DBUS_INTERFACE_ENTRY_GROUP)
                self.entrygroup.AddService(avahi.IF_UNSPEC,
                                           avahi.PROTO_UNSPEC,
                                           0,
                                           servicename,
                                           servicetype,
                                           "",
                                           "",
                                           dbus.UInt16(self.port),
                                           ())
                self.entrygroup.Commit()

    def _mdns_withdraw(self):
          if use_mdns and self.entrygroup != None:
                self.entrygroup.Reset()
                self.entrygroup.Free()
                self.entrygroup = None

    def _playing_changed_cb(self, player, playing):
          self._update_entry(player.get_playing_entry())

    def _playing_entry_changed_cb(self, player, entry):
          self._update_entry(entry)

    def _extra_metadata_changed_cb(self, db, entry, field, metadata):
          if entry == self.player.get_playing_entry():
                self._update_entry(entry)

    def _update_entry(self, entry):
          if entry:
                artist   = self.db.entry_get(entry, rhythmdb.PROP_ARTIST)
                album    = self.db.entry_get(entry, rhythmdb.PROP_ALBUM)
                title    = self.db.entry_get(entry, rhythmdb.PROP_TITLE)
                duration = self.db.entry_get(entry, rhythmdb.PROP_DURATION)
                eid      = self.db.entry_get(entry, rhythmdb.PROP_ENTRY_ID)
                stream = None
                stream_title = \
                    self.db.entry_request_extra_metadata(entry,
                                                         'rb:stream-song-title')
                if stream_title:
                      stream = title
                      title = stream_title
                      if not artist:
                            artist = self.db.\
                                entry_request_extra_metadata(entry,
                                                             'rb:stream-song-artist')
                      if not album:
                            album = self.db.\
                                entry_request_extra_metadata(entry,
                                                             'rb:stream-song-album')
                self.server.set_playing(artist, album, title, stream,duration,eid)
          else:
                self.server.set_playing(None, None, None, None,None,None)


class RhythmwebServer(object):

      def __init__(self, hostname, port, plugin):
            self.plugin = plugin
            self.running = True
            self.artist = None
            self.album = None
            self.title = None
            self.stream = None
            self.duration = None
            self.eid      = None
            self._httpd = make_server(hostname, port, self._wsgi,
                                      handler_class=LoggingWSGIRequestHandler)
            self._watch_cb_id = gobject.io_add_watch(self._httpd.socket,
                                                     gobject.IO_IN,
                                                     self._idle_cb)

      def shutdown(self):
            gobject.source_remove(self._watch_cb_id)
            self.running = False
            self.plugin = None
            
      def set_playing(self, artist, album, title, stream,duration,eid):
            self.artist = artist
            self.album = album
            self.title = title
            self.stream = stream
            self.duration = duration
            self.eid=eid

      def _open(self, filename):
            filename = os.path.join(os.path.dirname(__file__), filename)
            return open(filename)

      def _idle_cb(self, source, cb_condition):
            if not self.running:
                  return False
            self._httpd.handle_request()
            return True

      def _wsgi(self, environ, response):
            path = environ['PATH_INFO']
            if path in ('/', ''):
                  return self._handle_interface(environ, response)
            elif path.startswith('/stock/'):
                  return self._handle_stock(environ, response)
            elif path.startswith('/get-xml-pl/'):		
                  return self._make_playlist_xml(response)
            else:
                  return self._handle_static(environ, response)

      def _handle_interface(self, environ, response):
            player = self.plugin.player
            shell = self.plugin.shell
            db = self.plugin.db

            # handle any action
            if environ['REQUEST_METHOD'] == 'POST':
                  params = parse_post(environ)
                  if 'action' in params:
		       
                        action = params['action'][0]
                        if action == 'play':		
                              if not player.get_playing():
                                    if not player.get_playing_source():
                                          return self._play_entry(params,response)
                                    else:
                                          return self._play(params,response)
                              else:
                                    return self._pause(params,response)
                        elif action == 'pause':
                              player.pause()
                        elif action == 'play-entry':
                              return self._play_entry(params,response)		    
                        elif action == 'next':
                              player.do_next()
                        elif action == 'prev':
                              player.do_previous()
                        elif action == 'stop':
                              player.stop()
                        elif action == 'set-vol':
                              return self._setvolume(params,response)
                        elif action == 'get-vol':
                              return self._getvolume(params,response)
                        elif action == 'vol-up':
                              player.set_volume(player.get_volume() + 0.1)
                        elif action == 'vol-down':
                              player.set_volume(player.get_volume() - 0.1)
                        elif action == 'get-xml-pl':
                              return self._make_playlist_xml(db,playlist_rows,response)
                        elif action == 'get-playing':
                              return self._getplaying(params,response)
                        elif action == 'set-play-time':
                              return self._setplaypos(params,response)
                        elif action == 'search':
                              return self._player_search_term(params, response)
                        
                  return return_redirect('/', environ, response)

          # display the page
            player_html = open(resolve_path('index.html'))
            response_headers = [('Content-type','text/html; charset=UTF-8')]
            response('200 OK', response_headers)
            return player_html.read() 

      def _make_playlist_xml(self,response):
            db = self.plugin.db
            libquery = (rhythmdb.QUERY_PROP_EQUALS, rhythmdb.PROP_TYPE,db.entry_type_get_by_name('song'))
            
            response_headers = [('Content-type','text/xml; charset=UTF-8')]
            response('200 OK', response_headers)
            return self._query_to_xml(libquery)

      def _query_to_xml(self, query):
            db = self.plugin.db
            playlist_rows = self._player_search(query)
            playlist = cStringIO.StringIO()
            plsize = playlist_rows.get_size()
            playlist.write('<?xml version="1.0" encoding="utf-8" ?>');
            playlist.write('<rows>')
            playlist.write('  <page>1</page>')
            playlist.write('  <total>1</total>')
            playlist.write('  <records>%s</records>' % plsize )
            rindex = 0;
            for row in playlist_rows:
                  entry = row[0]
                  rindex = rindex + 1
                  playlist.write('<row>')
                  #playlist.write('  <cell>%s</cell>' % rindex )
                  playlist.write('  <cell>%s</cell>' % db.entry_get(entry, rhythmdb.PROP_TRACK_NUMBER) )
                  playlist.write('  <cell><![CDATA[<a href="#" name="playingtrack_%s">' % db.entry_get(entry, rhythmdb.PROP_ENTRY_ID))		
                  playlist.write(db.entry_get(entry, rhythmdb.PROP_TITLE))
                  playlist.write('</a>]]></cell><cell><![CDATA[')
                  playlist.write(db.entry_get(entry, rhythmdb.PROP_ARTIST))
                  playlist.write('  ]]></cell><cell><![CDATA[')
                  playlist.write(db.entry_get(entry, rhythmdb.PROP_ALBUM))
                  playlist.write('  ]]></cell><cell><![CDATA[')

                  tm_dur = db.entry_get(entry, rhythmdb.PROP_DURATION)
                  tm_min = int(math.ceil(tm_dur/60))
                  tm_sec = tm_dur%60

                  if tm_sec<10:
                        tm_sec = '0%s' %tm_sec
                        
                  playlist.write('%s:%s' % (tm_min,tm_sec) )
                  playlist.write('  ]]></cell><cell><![CDATA[')
                  playlist.write(db.entry_get(entry, rhythmdb.PROP_GENRE))
                  playlist.write('  ]]></cell><cell><![CDATA[')
                  playlist.write('%s' % db.entry_get(entry, rhythmdb.PROP_ENTRY_ID))
                  playlist.write('  ]]></cell>')
                  playlist.write('</row>')
                  if rindex > 200:
                        break

            playlist.write('</rows>')
            return playlist.getvalue()
            
      def _player_search(self, search):
            #"""perform a player search"""
            
            db = self.plugin.db
            query = db.query_new()
            db.query_append(query, search)
            query_model = db.query_model_new_empty()
            db.do_full_query_parsed(query_model, query)
            
            return query_model;

      def _player_search_term(self, params, response):
            #"""Search library for term""""
            term = params['term'][0]
            libquery = (rhythmdb.QUERY_PROP_LIKE, rhythmdb.PROP_ARTIST_FOLDED, term)
            
            response_headers = [('Content-type','text/xml; charset=UTF-8')]
            response('200 OK', response_headers)
            
            return self._query_to_xml(libquery)

      def _setvolume(self, params, response):
            player = self.plugin.player
            player.set_volume(float(params['vol'][0]))
            json = '{}'
            response_headers = [('Content-type','text/plain; charset=UTF-8')]
            response('200 OK', response_headers)
            return json

      def _getvolume(self, params, response):
            player = self.plugin.player
            curvol = player.get_volume()
            json = '{current_vol:%s}' % curvol
            response_headers = [('Content-type','text/plain; charset=UTF-8')]
            response('200 OK', response_headers)
            return json

      def _pause(self, params, response):
            player = self.plugin.player
            player.pause()
            json = '{pause:true}'
            response_headers = [('Content-type','text/plain; charset=UTF-8')]
            response('200 OK', response_headers)
            return json

      def _play(self, params, response):
            player = self.plugin.player
            player.play()
            json = '{pause:false}'
            response_headers = [('Content-type','text/plain; charset=UTF-8')]
            response('200 OK', response_headers)
            return json

      def _play_entry(self, params, response):
            player = self.plugin.player
            shell = self.plugin.shell
            db = self.plugin.db

            entryid = params['location'][0]
            pentry = db.entry_lookup_by_id(int(entryid))
            sys.stdout.write('location value received : %s' %params['location'][0])

            sys.stdout.write('entry title: %s' % db.entry_get(pentry, rhythmdb.PROP_ARTIST))
            player.play_entry(pentry)
            json = '{}'
            response_headers = [('Content-type','text/plain; charset=UTF-8')]
            response('200 OK', response_headers)
            return json

      def _setplaypos(self, params, response):
            player = self.plugin.player
            player.set_playing_time(int(params['pos'][0]))
            response_headers = [('Content-type','text/plain; charset=UTF-8')]
            response('200 OK', response_headers)
            json = '{}'
            return json

      def _getplaying(self, params, response):
            player = self.plugin.player
            playing = '<span id="not-playing">Not playing</span>'
            if self.stream or self.title:

                  tm_dur = self.duration
                  tm_min = int(math.floor(tm_dur/60))
                  tm_sec = tm_dur%60
	    


                  playing = ''
                  if self.title:
                        playing = '<cite id="title">%s</cite>' % self.title
                  if self.artist:
                        playing = ('%s by <cite id="artist">%s</cite>' %
                                   (playing, self.artist))
                  if self.album:
                        playing = ('%s from <cite id="album">%s</cite>' %
                                   (playing, self.album))
                  if self.stream:
                        if playing:
                              playing = ('%s <cite id="stream">(%s)</cite>' %
                                         (playing, self.stream))
                        else:
                              playing = self.stream
                  playing = '<a href="#playingtrack_%s">%s</a> <span id="dur-sec-count">%s</span><span id="elp-sec-count">%s</span>' % (self.eid,playing,tm_dur,player.get_playing_time())
                
            response_headers = [('Content-type','text/html; charset=UTF-8')]
            response('200 OK', response_headers)
            return playing


      def _handle_stock(self, environ, response):
            path = environ['PATH_INFO']
            stock_id = path[len('/stock/'):]

            icons = gtk.icon_theme_get_default()
            iconinfo = icons.lookup_icon(stock_id, 24, ())
            if not iconinfo:
                  iconinfo = icons.lookup_icon(stock_id, 32, ())
            if not iconinfo:
                  iconinfo = icons.lookup_icon(stock_id, 48, ())
            if not iconinfo:
                  iconinfo = icons.lookup_icon(stock_id, 16, ())

            if iconinfo:
                  filename = iconinfo.get_filename()
                  icon = open(filename)
                  lastmod = time.gmtime(os.path.getmtime(filename))
                  lastmod = time.strftime("%a, %d %b %Y %H:%M:%S +0000", lastmod)
                  response_headers = [('Content-type','image/png'),
                                      ('Last-Modified', lastmod)]
                  response('200 OK', response_headers)
                  return icon
            else:
                  response_headers = [('Content-type','text/plain')]
                  response('404 Not Found', response_headers)
                  return 'Stock not found: %s' % stock_id

      def _handle_static(self, environ, response):
            rpath = environ['PATH_INFO']

            path = rpath.replace('/', os.sep)
            path = os.path.normpath(path)
            if path[0] == os.sep:
                  path = path[1:]
                  
            path = resolve_path(path)

            # this seems to cause a segfault
            #f = self.plugin.find_file(path)
            #print str(f)

            if os.path.isfile(path):
                  lastmod = time.gmtime(os.path.getmtime(path))
                  lastmod = time.strftime("%a, %d %b %Y %H:%M:%S +0000", lastmod)
		
                  content_type = 'text/css'
                  if fnmatch.fnmatch(path, '*.js'):
                      content_type = 'text/javascript'
                  elif fnmatch.fnmatch(path, '*.xml'):
                        content_type = 'text/xml'
                  elif fnmatch.fnmatch(path, '*.png'):
                        content_type = 'image/png'
                  elif fnmatch.fnmatch(path, '*.ico'):
                        content_type = 'image/ico'
                  elif fnmatch.fnmatch(path, '*.html'):
                        content_type = 'text/html'
                        
                  response_headers = [('Content-type',content_type),
                                            ('Last-Modified', lastmod)]
                  response('200 OK', response_headers)
                  return open(path)
            else:
                  response_headers = [('Content-type','text/plain')]
                  response('404 Not Found', response_headers)
                  return 'File not found: %s' % rpath

          
class LoggingWSGIRequestHandler(WSGIRequestHandler):

      def log_message(self, format, *args):
            # RB redirects stdout to its logging system, to these
            # request log messages, run RB with -D rhythmweb
            sys.stdout.write("%s - - [%s] %s\n" %
                             (self.address_string(),
                              self.log_date_time_string(),
                              format%args))


def parse_post(environ):
      if 'CONTENT_TYPE' in environ:
            length = -1
            if 'CONTENT_LENGTH' in environ:
                  length = int(environ['CONTENT_LENGTH'])
                  #if environ['CONTENT_TYPE'] == 'application/x-www-form-urlencoded':
                  #    return cgi.parse_qs(environ['wsgi.input'].read(length))
            if environ['CONTENT_TYPE'] == 'multipart/form-data':
                  return cgi.parse_multipart(environ['wsgi.input'].read(length))
            else:
                  return cgi.parse_qs(environ['wsgi.input'].read(length))
      return None

def return_redirect(path, environ, response):
      if not path.startswith('/'):
            path_prefix = environ['REQUEST_URI']
            if path_prefix.endswith('/'):
                  path = path_prefix + path
            else:
                  path = path_prefix.rsplit('/', 1)[0] + path
      scheme = environ['wsgi.url_scheme']
      if 'HTTP_HOST' in environ:
            authority = environ['HTTP_HOST']
      else:
            authority = environ['SERVER_NAME']
      port = environ['SERVER_PORT']
      if ((scheme == 'http' and port != '80') or
          (scheme == 'https' and port != '443')):
            authority = '%s:%s' % (authority, port)
      location = '%s://%s%s' % (scheme, authority, path)
      status = '303 See Other'
      response_headers = [('Content-Type', 'text/plain'),
                          ('Location', location)]
      response(status, response_headers)
      return [ 'Redirecting...' ]

def resolve_path(path):
      return os.path.join(os.path.dirname(__file__), path)


