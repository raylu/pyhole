window.addEvent('domready', function() {
	var stage = new Kinetic.Stage({
		container: 'map',
		width: 900,
		height: 300
	});
	var layer = new Kinetic.Layer();

	var req = new Request.JSON({
		'url': '/map.json',
		'onSuccess': drawMap,
	});
	req.get();
	function drawMap(map, raw) {
		drawSystem(map, 100, 75);
		drawSystem(map.connections[0], 250, 75);
		stage.add(layer);
	}

	function drawSystem(system, x, y) {
		var width = 100;
		var ellipse = new Kinetic.Circle({
			'x': x,
			'y': y,
			'radius': width / 4,
			'fill': '#705',
			'stroke': '#ccc',
			'strokeWidth': 2,
			'scaleX': 2,
		});
		ellipse.on('click', handleClick);
		layer.add(ellipse);
		// draw text
		var text = new Kinetic.Text({
			'text': system.name,
			'x': x,
			'y': y-7,
			'fontSize': 14,
			'fill': '#ccc',
		});
		var textWidth = text.getTextWidth();
		text.setX(x - textWidth / 2);
		text.on('click', handleClick);
		layer.add(text);

	}
	function handleClick() {
		console.log(arguments);
	}
});
