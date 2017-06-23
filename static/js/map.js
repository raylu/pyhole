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
			var maps = JSON.parse(message);
			if (layer !== null)
				layer.destroy();
			layer = new Kinetic.Layer();
			var y = 75;
			var cols = 0;
			maps.each(function(map) {
				var stats = drawNode(map, 80, y);
				y += stats[0] * rowHeight;
				cols = Math.max(stats[1], cols);
			});
			stage.setHeight(y);
			stage.setWidth(cols * 150);
			stage.add(layer);
			if (!maps.length)
				$$('.add').setStyle('display', 'inline-block');
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
		var newLines = 0;
		var newCols = 0;
		if (node.connections) {
			for (var i = 0; i < node.connections.length; i++) {
				var child = node.connections[i];
				drawLink(x, y, x + 150, y + newLines * rowHeight, child.eol, child.mass, child.stargate, child.frigate);
				var stats = drawNode(child, x + 150, y + newLines * rowHeight);
				newLines += stats[0];
				newCols = Math.max(stats[1], newCols);
			}
		}
		if (current_system && node.name == current_system.name) {
			handleClick(node);
		}
		return [newLines || 1, newCols + 1];
	}

	var class_color = {
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
	function drawLink(x1, y1, x2, y2, eol, mass, stargate, frigate) {
		var color;
		if (stargate)
			color = '#040';
		else if (mass == 'reduced')
			color = '#c52';
		else if (mass == 'critical')
			color = '#b12';
		else if (mass == 'stable')
			color = '#ccc';
		var line = new Kinetic.Line({
			'x': 0,
			'y': 0,
			'points': [x1+ovalWidth/2, y1, x2-ovalWidth/2, y2],
			'stroke': color,
			'strokeWidth': !window.WebSocket && eol ? 1 : 2, // the IGB doesn't support dashArray
			'opacity': frigate ? .3 : 1,
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
	var sigsTable = new HtmlTable($('signatures'), {'sortable': true});
	var src = $('src');
	var current_system = null;
	function handleClick(system) {
		if (is_wspace(system.name))
			var url = 'http://wh.pasta.gg/' + system.name;
		else
			var url = 'http://evemaps.dotlan.net/system/' + system.name;
		system_name.empty();
		system_name.grab(new Element('a', {
			'html': system.name,
			'href': url,
			'target': '_blank',
		}));

		if (is_wspace(system.name))
			effect.set('text', system.effect || 'no effect');
		else
			effect.set('html', '');

		var static_str = '';
		if (system.static1)
			static_str += formatStatic(system.static1);
		if (system.static2)
			static_str += '<br>' + formatStatic(system.static2);
		statics.set('html', static_str);

		connections.empty();
		if (system.connections) {
			var conns = system.connections.each(function(conn) {
				connections.appendText(conn.name + ' ');
				if (conn.stargate) {
					var note = new Element('span', {'html': '(stargate)'});
					connections.adopt(note);
				} else {
					['EoL', 'reduced', 'critical', 'frigate'].each(function(state) {
						var toggle = new Element('a', {'html': state + ' ', 'href': ''});
						toggle.addEvent('click', function(e) {
							e.preventDefault();
							send(state.toUpperCase(), system.name + ' ' + conn.name);
						});
						if (state == 'EoL' && conn['eol'] || conn['mass'] == state || state == 'frigate' && conn['frigate'])
							connections.adopt(new Element('b').adopt(toggle));
						else
							connections.adopt(toggle);
					});
				}
				connections.adopt(new Element('br'));
			});
		}

		trade_hubs.empty();
		if (system.jumps) {
			Object.each(system.jumps, function(route, trade_hub) {
				var row = new Element('tr');
				var nameColumn = new Element('td',{
					'text': trade_hub + ' (' + route.length + '):',
					'class': 'trade_hub',
				});
				row.grab(nameColumn);
				var routeColumn = new Element('td');
				Object.each(route, function(j) {
					var sec;
					if (j[1] >= 0.5)
						sec = 'highsec';
					else if (j[1] > 0.0)
						sec = 'lowsec';
					else
						sec = 'nullsec';
					var j = new Element('div', {'class': 'jump ' + sec, 'title': j[0]});
					routeColumn.grab(j);
				});
				row.grab(routeColumn);
				trade_hubs.grab(row);
			});
		}

		var sortState = sigsTable.serialize();
		sigsTable.empty();
		if (system.signatures) {
			var del_all = new Element('a', {'href': '', 'html': '&#x2715;'});
			del_all.addEvent('click', function(e) {
				e.preventDefault();
				send('DELSIG', system.name);
			});
			var row = new Element('tr');
			['ID', 'scan group', 'group', 'type', 'note'].each(function(header) {
				row.grab(new Element('th', {'html': header}));
			});
			row.grab(new Element('th').grab(del_all));
			sigsTable.set('headers', row);
			system.signatures.each(function(sig) {
				row = new Element('tr');
				for (var i = 0; i < 4; i++)
					row.grab(new Element('td', {'text': sig[i]}));

				var note = new Element('td', {'text': sig[5], 'class': 'note'});
				note.addEvent('click', function(e) {
					e.preventDefault();
					var input = new Element('input', {'type': 'text', 'value': sig[5]});
					input.addEvent('keypress', function(e) {
						if (e.key == 'enter')
							send('SIGNOTE', system.name + '\n' + sig[0] + '\n' + input.get('value'));
					});
					input.addEvent('blur', function(e) {
						note.set('html', sig[5]);
					});
					note.empty().grab(input);
					input.focus();
				});
				row.grab(note);

				var delSig = new Element('a', {'href': '', 'html': '&#x2715;'});
				row.grab(new Element('td').grab(delSig));
				delSig.addEvent('click', function(e) {
					e.preventDefault();
					send('DELSIG', system.name + ' ' + sig[0]);
				});

				sigsTable.push(row);
			});
			sigsTable.enableSort();
			sigsTable.restore(sortState);
			sigsTable.reSort();
		} else {
			sigsTable.set('headers', []);
			sigsTable.restore(sortState);
		}

		src.set('value', system.name);

		bottom_divs.setStyle('display', 'inline-block');
		current_system = system;
	}
	function formatStatic(st) {
		var format = '{name} to {dest} ({lifetime}h, {jump_mass}Kt/j, {max_mass}Kt)';
		var static_str = format.replace(/{(\w+)}/g, function(match, arg) {
			return st[arg];
		});
		return static_str;
	}
	$('delete').addEvent('click', function(e) {
		send('DELETE', system_name.get('text'));
		bottom_divs.setStyle('display', 'none');
		dest_ac.setStyle('display', 'none');
	});
	$('detach').addEvent('click', function(e) {
		send('DETACH', system_name.get('text'));
	});
	$('paste_sigs').addEvent('click', function(e) {
		var psDiv = new Element('div', {'class': 'paste_sigs'});
		var textarea = new Element('textarea', {'class': 'paste_sigs'});
		var addButton = new Element('input', {'type': 'button', 'value': 'add'});
		var replaceCheckbox = new Element('input', {'type': 'checkbox', 'id': 'replace'});
		var replaceLabel = new Element('label', {'type': 'checkbox', 'for': 'replace', 'html': 'replace'});
		psDiv.adopt(textarea, addButton, replaceCheckbox, replaceLabel);
		addButton.addEvent('click', function(e) {
			var action = 'add';
			if (replaceCheckbox.get('checked'))
				action = 'replace';
			send('SIGS', current_system.name + ' ' + action + '\n' + textarea.get('value'));
			$('modal_bg').fireEvent('click');
		});
		modal(psDiv);
		textarea.focus();
	});

	var add_form = $('add');
	add_form.addEvent('submit', function(e) {
		e.preventDefault();
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
		$('frigate').set('checked', false);
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

	function modal(el) {
		var modal_div = $('modal');
		modal_div.empty();
		if (el instanceof Element)
			modal_div.grab(el);
		else
			modal_div.appendText(el);
		var mbg = $('modal_bg').setStyle('display', 'block');
		mbg.focus();
		modal_div.addEvent('click', function(e) {
			e.stopPropagation();
		});
		mbg.addEvent('click', function(e) {
			mbg.setStyle('display', 'none');
			mbg.removeEvents('click');
		});
	}
});
