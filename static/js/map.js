window.addEvent('domready', function() {
	'use strict';
	var stage = new Kinetic.Stage({
		container: 'map',
		width: 900,
		height: 0,
	});
	var layer = null;
	var rowHeight = 75;
	var ovalWidth = 100;

	var ws = new WebSocket(window.config.wsurl);
	ws.onopen = function(e) {
		console.debug('connected to', e.target.url);
		ws.send('HELO ' + document.cookie);
	};
	ws.onmessage = function (e) {
		var data = e.data;
		var space = data.indexOf(' ');
		var command = data.substr(0, space);
		var message = data.substr(space + 1);
		switch(command) {
		case 'MAP':
			var map = JSON.parse(message);
			if (layer !== null)
				layer.destroy();
			layer = new Kinetic.Layer();
			var rows = drawNode(map, 100, 75);
			stage.setHeight((rows + 1) * rowHeight);
			stage.add(layer);
			break;
		case 'SYS':
			var systems = JSON.parse(message);
			if (systems.length > 0) {
				var val = dest.get('value');
				// handle race where we receive a message for a different SYS request
				if (val.toLowerCase() == systems[0].substr(0, val.length).toLowerCase()) {
					dest_ac.empty();
					systems.each(function(s) {
						dest_ac.adopt(new Element('div', {'html': s}));
					});
					dest_ac.setStyle('display', 'block');
				}
			}
			break;
		case 'ERR':
			modal(message);
			break;
		default:
			console.warn('unhandled message', data);
		}
	}
	ws.onerror = ws.onclose = function(e) {
		console.error('ws closed', e);
		modal('ruh roh!');
		ws.close();
	}
	function send(command, args) {
		var message = command + ' ' + args;
		console.debug(message);
		ws.send(message);
	}

	function drawNode(node, x, y) {
		drawSystem(node, x, y);
		var new_lines = 0;
		if (node.connections) {
			for (var i = 0; i < node.connections.length; i++) {
				var child = node.connections[i];
				drawLink(x, y, x + 150, y + new_lines * rowHeight, child.eol);
				new_lines += drawNode(child, x + 150, y + new_lines * rowHeight);
			}
		}
		return new_lines || 1;
	}

	function drawSystem(system, x, y) {
		var ellipse = new Kinetic.Circle({
			'x': x,
			'y': y,
			'radius': ovalWidth / 4,
			'fill': '#705',
			'stroke': '#ccc',
			'strokeWidth': 2,
			'scaleX': 2,
		});
		layer.add(ellipse);
		// draw text
		var text = new Kinetic.Text({
			'text': system.name,
			'x': x,
			'y': y-7,
			'fontSize': 14,
			'fontFamily': 'sans-serif',
			'fill': '#ccc',
		});
		var textWidth = text.getTextWidth();
		text.setX(x - textWidth / 2);
		layer.add(text);

		function _handleClick(e) {
			handleClick(system);
		}
		text.on('click', _handleClick);
		ellipse.on('click', _handleClick);
	}
	function drawLink(x1, y1, x2, y2, eol) {
		var line = new Kinetic.Line({
			'x': 0,
			'y': 0,
			'points': [x1+ovalWidth/2, y1, x2-ovalWidth/2, y2],
			'stroke': '#ccc',
			'dashArray': [6, 3],
			'dashArrayEnabled': Boolean(eol), // undefined behaves like true when dashArray is set
		});
		layer.add(line);
	}

	var bottom_divs = $$('.add, .info');
	var system_name = $('system_name'), src = $('src');
	function handleClick(system) {
		system_name.set('text', system.name);
		src.set('value', system.name);
		bottom_divs.setStyle('display', 'block');
	}
	$('delete').addEvent('click', function(e) {
		send('DELETE', system_name.get('text'));
		bottom_divs.setStyle('display', 'none');
		dest_ac.setStyle('display', 'none');
	});
	var add_form = $('add');
	add_form.addEvent('submit', function(e) {
		e.preventDefault()
		var o = {};
		add_form.getElements('input').each(function(el) {
			if (el.type === 'submit')
				return;
			else if (el.type === 'checkbox') {
				var checked = el.get('checked');
				if (checked)
					o[el.get('id')] = checked;
			} else if (el.type === 'text') {
				var val = el.get('value');
				if (val.length > 0)
					o[el.get('id')] = val;
			}
		});
		if (o.dest === undefined) {
			modal("you didn't specify a system name");
			return;
		}
		send('ADD', JSON.stringify(o));

		['dest', 'to', 'from'].each(function(id) {
			$(id).set('value', '');
		});
		$('eol').set('checked', false);
		dest_ac.setStyle('display', 'none');
	});
	var dest = $('dest'), dest_ac = $('dest_ac');
	dest.addEvent('input', function() {
		var val = dest.get('value');
		if (val.length < 2)
			return;
		if (val[0].toUpperCase() == 'J') {
			var num = parseInt(val.substr(1), 10);
			if (num === num) // otherwise, it's NaN
				return; // don't bother completing w-space systems
		}
		dest_ac.empty();
		send('SYS', val);
	});

	function modal(text) {
		$('modal').empty().appendText(text);
		var mbg = $('modal_bg').setStyle('display', 'block');
		mbg.addEvent('click', function() {
			mbg.setStyle('display', 'none');
			mbg.removeEvents('click');
		});
	}
});
