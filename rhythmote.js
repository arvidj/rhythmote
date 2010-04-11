var playminelp = 0;
var playsecelp = 0;
var playsecdur = 0;
var pltmOut  = 0;
var pltmUpdt = 0;
var curTrackTime = '';
var curVolume = 0;
var docWidth = 0;

var jqGridOptions = { 
    url:'/get-xml-pl/', 
	datatype: "xml", 
	colNames:['Track#', 'Title', 'Artist','Album','Time','Genre','Track id'], 
	colModel:[ {name:'id',index:'id', width:30, sortable:false}, 
			   {name:'title',index:'title', width:150}, 
			   {name:'artist',index:'artist', width:80, align:"left"}, 
			   {name:'album',index:'album', width:100, align:"left"}, 
			   {name:'time',index:'time', width:30,align:"center"}, 
			   {name:'genre',index:'genre', width:55},
			   {name:'trackid',index:'trackid',hidden:true} ], 
	rowNum:-1,
	postData:{action:'get-xml-pl'},
	pginput:false,
	pgtext:'',
	loadonce:true,
	rownumbers:true,
	gridview:true,
	recordpos:'center',
    pgbuttons:false,
	recordtext:'{1} out of {2} total tracks',
	rowList:[], 
	imgpath: 'jquery/jqGrid-3.4.2/themes/coffee/images',
	sortname: 'id', 
	viewrecords: true, 
	sortorder: "desc",
	width:docWidth*.95,
	height:'auto',
	caption:"Music library"
};

$(function(){

	docWidth = $(document).width();
	$().ajaxStop(function(){$.unblockUI();$('#container').css("visibility","visible");}); 
	$.blockUI({ 
		message:'Loading music library, please wait...',
		css: 
		{
            border: 'none', 
            padding: '15px', 
            backgroundColor: '#000', 
            '-webkit-border-radius': '10px', 
            '-moz-border-radius': '10px', 
            opacity: '.5', 
            color: '#fff' 
        }
	}); 
	//volume Slider
	make_volctrl();
	make_play_pos_ctrl();
	
	
	//hover states on the static widgets
	$('button#volumedown,button#volumeup,ul#icons button').hover(
		function() { $(this).addClass('ui-state-hover'); }, 
		function() { $(this).removeClass('ui-state-hover'); }
	);
	

	$('#container').width(docWidth*.955);	
	$('#player-control-panel').width(docWidth*.95);	
	$('#volume_slider').width(docWidth*.2);
	$('#playing-info-panel').width(docWidth*.95);	
	$('#play_position_slider').width(docWidth*.95);		
	$('#play_queue_list').jqGrid($.extend(
        jqGridOptions,
        { 
            url:'/get-xml-pl/', 
	        postData:{action:'get-xml-pl'},
	        width:docWidth*.95,
            pager: $('#play_queue_pager'),
	        ondblClickRow:playtrack
        }
    ));

	bind_handlers();
	get_playing();
});

function bind_handlers() {
    $('#volumeup').click(volume_up);
	$('#volumedown').click(volume_down);
    $('#playbtn').click(toggle_play);
    $('#prevbtn').click(play_prev);
    $('#nextbtn').click(play_next);
    $('#search-form').submit(search);
}

function search(e) {
    e.stopPropagation();

    var docWidth = $(document).width();
    $.post('/',{action:'search', term: $('#search').val()},function(data){
        console.log('recieved data');
        console.log(data);
        $('#play_queue_list')[0].addXmlData(data);
    });

    return false;
}


function make_volctrl(){
    $.post('/',{action:'get-vol'},function(data){
		var obj = eval('('+data+')');
		curVolume = obj.current_vol;
		$('#volume_slider').slider(
            {min:0,
			 max:1,
			 step:0.1,
			 value:obj.current_vol,
			 /*orientation: 'vertical',*/
			 slide:function(event, ui) { 
				 curVolume = ui.value;
				 setvolume(ui.value);
			 }
		    });
	});
}

function set_play_pos(pos){
    $.post('/',{action:'set-play-time',pos:pos},function(data){
		get_playing();
	});
}

function make_play_pos_ctrl(){
	$('#play_position_slider').slider(
        {min:0,
		 max:1,
		 step:1,
		 value:0,
		 change:function(event, ui) { 
			 set_play_pos(ui.value);
		 }
		});
}

function setvolume(volume){
    $.post('/',{action:'set-vol',vol:volume},function(data){
		
	});
}

function volume_up(){
	curVolume = $('#volume_slider').slider('option','value');
	if(curVolume+0.1<=1){		
	   	$('#volume_slider').slider('option','value',curVolume+0.1);
		setvolume(curVolume+0.1);
		
	}
}

function volume_down(){
	curVolume = $('#volume_slider').slider('option','value');
	if(curVolume-0.1>=0){		
        $('#volume_slider').slider('option','value',curVolume-0.1);
		setvolume(curVolume-0.1);
	}
}

function playtrack(rowid){
	row = $('#play_queue_list').getRowData(rowid);
    $.post('/',{action:'play-entry',location:row.trackid},function(data){
	    if(pltmOut != 0)
	  		clearTimeout(pltmOut);
		pltmOut  = setTimeout('get_playing()',1500);
	});
}
function play_next(){
    $.post('/',{action:'next'},function(data){
	    if(pltmOut != 0)
	  		clearTimeout(pltmOut);
		pltmOut  = setTimeout('get_playing()',1500);
	});
}
function play_prev(){
    $.post('/',{action:'prev'},function(data){
	    if(pltmOut != 0)
	  		clearTimeout(pltmOut);
		pltmOut  = setTimeout('get_playing()',1500);
	});
}

function toggle_play(){
    $.post('/',{action:'play',location:1},function(data){
		var obj = eval('('+data+')');
		if(obj.pause){
		    $('#playbtn span').removeClass('ui-icon-play');
		    $('#playbtn span').addClass('ui-icon-pause');

	     	if(pltmUpdt != 0)
	  		    clearInterval(pltmUpdt);
	     	if(pltmOut != 0)
	  		    clearTimeout(pltmOut);
		}
		else{ 
		    $('#playbtn span').removeClass('ui-icon-pause');
		    $('#playbtn span').addClass('ui-icon-play');
	     	if(pltmUpdt != 0)
	  		    clearInterval(pltmUpdt);
	     	if(pltmOut != 0)
	  		    clearTimeout(pltmOut);

		    pltmOut  = setTimeout('get_playing()',1500);
		}
	});
}

function get_playing(){
	if(pltmOut != 0)
	    clearTimeout(pltmOut);

	if(pltmUpdt != 0)
	    clearInterval(pltmUpdt);

    $.post('/',{action:'get-playing'},function(data){		
		$('#playing-info').html(data);
		if($('#elp-sec-count') != null){
			playsecelp = $('#elp-sec-count').html();
			playsecdur = $('#dur-sec-count').html();
			curTrackTime = Math.floor(playsecdur/60)+":"+((playsecdur%60)<10?'0'+(playsecdur%60):(playsecdur%60));

			$('#play_position_slider').slider('option','max',playsecdur).slider('option','value',playsecelp);


			tmout = (playsecdur-playsecelp)+2;
			pltmOut  = setTimeout('get_playing()',tmout*1000);
			pltmUpdt = setInterval("show_play_time()",1000);	
			
		}
	});
}

function show_play_time(){
	++playsecelp;
	if(playsecelp>=playsecdur)
		clearInterval(pltmUpdt);
	else{
		$('#current-play-time').
		    html(Math.floor(playsecelp/60)+":"+((playsecelp%60)<10?'0'+(playsecelp%60):(playsecelp%60))+' of '+curTrackTime);
		$('#play_position_slider').slider('option','value',playsecelp);
	}
}