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
		var map = JSON.parse(e.data);
		if (layer !== null)
			layer.destroy();
		layer = new Kinetic.Layer();
		var rows = drawNode(map, 100, 75);
		stage.setHeight((rows + 1) * rowHeight);
		stage.add(layer);
	}
	ws.onerror = ws.onclose = function(e) {
		console.error(e);
		modal('ruh roh!');
		ws.close();
	}

	function drawNode(node, x, y) {
		drawSystem(node, x, y);
		var new_lines = 0;
		if (node.connections) {
			for (var i = 0; i < node.connections.length; i++) {
				var child = node.connections[i];
				drawLink(x, y, x + 150, y + new_lines * rowHeight);
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
	function drawLink(x1, y1, x2, y2) {
		var line = new Kinetic.Line({
			'x': 0,
			'y': 0,
			'points': [x1+ovalWidth/2, y1, x2-ovalWidth/2, y2],
			'stroke': '#ccc',
		});
		layer.add(line);
	}

	var add_div = $$('.add')[0];
	var src = $('src');
	function handleClick(system) {
		src.set('value', system.name);
		add_div.setStyle('display', 'block');
	}
	var add_form = $('add');
	add_form.addEvent('submit', function(e) {
		e.preventDefault()
		var o = {};
		add_form.getChildren('input').each(function(el) {
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
		console.debug('ADD', o);
		ws.send('ADD ' + JSON.stringify(o));

		['dest', 'to', 'from'].each(function(id) {
			$(id).set('value', '');
		});
		$('eol').set('checked', false);
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
