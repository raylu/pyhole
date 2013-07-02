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

	var send = null;
	if (window.WebSocket) {
		var ws = new WebSocket(window.config.wsurl);
		ws.onopen = function(e) {
			console.debug('connected to', e.target.url);
			ws.send('HELO ' + document.cookie);
		};
		ws.onmessage = function (e) {
			parseData(e.data);
		}
		ws.onerror = ws.onclose = function(e) {
			console.error('ws closed', e);
			modal('ruh roh!');
			ws.close();
		}

		send = function(command, args) {
			var message = command + ' ' + args;
			console.debug(message);
			ws.send(message);
		}
	} else {
		send = function(command, args) {
			console.debug(command, args);
			new Request.JSON({
				url: '/map.json/' + command,
				onSuccess: parseData,
				onFailure: function(xhr) {
					console.error('xhr failed', xhr);
					modal('ruh roh: ' + xhr.responseText);
				},
			}).get({'args': args});
		}
		send('HELO');
	}

	function parseData(data) {
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
					dest_ac.getElement('div').addClass('selected');
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

	var class_color = {
		'home': '#404',
		'highsec': '#040',
		'lowsec': '#440',
		'nullsec': '#400',
		1: '#135',
		2: '#124',
		3: '#122',
		4: '#114',
		5: '#113',
		6: '#112',
	}
	function drawSystem(system, x, y) {
		var ellipse = new Kinetic.Circle({
			'x': x,
			'y': y,
			'radius': ovalWidth / 2 / 1.75, // radius is half the width, and scaleX = 1.75
			'fill': class_color[system.class],
			'stroke': '#ccc',
			'strokeWidth': 2,
			'scaleX': 1.75,
		});
		layer.add(ellipse);
		// draw text
		var sysNameText = new Kinetic.Text({
			'text': system.name,
			'x': x,
			'y': y-16,
			'fontSize': 14,
			'fontFamily': 'sans-serif',
			'fill': '#ccc',
		});
		var textWidth = sysNameText.getTextWidth();
		sysNameText.setX(x - textWidth / 2);
		layer.add(sysNameText);


		var sys_class;
		if (system.class && !system.class.length) // not a string, so w-space
			sys_class = 'C' + system.class;
		else
			sys_class = system.class || '';
		var sysClassText = new Kinetic.Text({
			'text': sys_class,
			'x': x,
			'y': y+2,
			'fontSize': 14,
			'fontFamily': 'sans-serif',
			'fill': '#ccc',
		})
		textWidth = sysClassText.getTextWidth();
		sysClassText.setX(x - textWidth / 2);
		layer.add(sysClassText);

		function _handleClick(e) {
			handleClick(system);
		}
		sysNameText.on('click', _handleClick);
		sysClassText.on('click', _handleClick);
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

	function is_wspace(system_name) {
		if (system_name[0].toUpperCase() == 'J') {
			var num = parseInt(system_name.substr(1), 10);
			return (num === num); // otherwise, it's NaN
		}
		return false;
	}

	var bottom_divs = $$('.add, .info');
	var system_name = $('system_name');
	var effect = $('effect');
	var statics = $('statics');
	var connections = $('connections');
	var trade_hubs = $('trade_hubs');
	var src = $('src');
	function handleClick(system) {
		if (is_wspace(system.name))
			var url = 'http://wormhol.es/' + system.name;
		else
			var url = 'http://eveeye.com/?system=' + system.name;
		system_name.empty();
		system_name.grab(new Element('a', {
			'html': system.name,
			'href': url,
			'target': '_blank',
		}));

		effect.set('text', system.effect || 'no effect');

		var static_str = '';
		if (system.static1)
			static_str += system.static1.name + ' to ' + system.static1.dest;
		if (system.static2)
			static_str += '<br>' + system.static2.name + ' to ' + system.static2.dest;
		statics.set('html', static_str);

		connections.empty();
		if (system.connections) {
			var conns = system.connections.each(function(conn) {
				var toggle = new Element('a', {'html': '(toggle EoL)', 'href': ''});
				toggle.addEvent('click', function(e) {
					e.preventDefault();
					send('EOL', system.name + ' ' + conn.name);
				});
				connections.appendText(conn.name + ' ');
				connections.adopt(toggle, new Element('br'));
			});
		}
		trade_hubs.empty();
		if (system.jumps) {
			Object.each(system.jumps, function(route, trade_hub) {
				trade_hubs.grab(new Element('div', {
					'text': trade_hub + ' (' + route.length + '):',
					'class': 'trade_hub',
				}));
				Object.each(route, function(j) {
					var sec;
					if (j[1] >= 0.5)
						sec = 'highsec';
					else if (j[1] > 0.0)
						sec = 'lowsec';
					else
						sec = 'nullsec';
					var j = new Element('div', {'class': 'jump ' + sec, 'title': j[0]});
					trade_hubs.grab(j);
				});
				trade_hubs.grab(new Element('br'));
			});
		}

		src.set('value', system.name);

		bottom_divs.setStyle('display', 'inline-block');
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
		dest_ac.setStyle('display', 'none');
		var val = dest.get('value');
		if (val.length < 2)
			return;
		if (is_wspace(val))
			return;
		send('SYS', val);
	});
	// hides the auto complete div when loses focus
	dest.addEvent('blur', function() {
		dest_ac.setStyle('display', 'none');
	});

	function select_direction(dir) {
		var comps = dest_ac.getElements('div');
		comps.some(function(d, i) {
			if (d.hasClass('selected')) {
				if (comps[i+dir]) {
					d.removeClass('selected');
					comps[i+dir].addClass('selected');
				}
				return true;
			}
		});
	}
	dest.addEvent('keydown', function(e) {
		switch (e.key) {
		case 'enter':
			if (dest_ac.getStyle('display') === 'block') {
				e.preventDefault();
				dest.set('value', dest_ac.getElement('.selected').get('text'));
				dest_ac.setStyle('display', 'none');
			}
			break;
		case 'down':
			e.preventDefault();
			select_direction(+1);
			break;
		case 'up':
			e.preventDefault();
			select_direction(-1);
			break;
		}
	});

	function modal(text) {
		$('modal').empty().appendText(text);
		var mbg = $('modal_bg').setStyle('display', 'block');
		mbg.focus();
		mbg.addEvent('click', function() {
			mbg.setStyle('display', 'none');
			mbg.removeEvents('click');
		});
	}
});
