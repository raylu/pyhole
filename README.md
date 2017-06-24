pyhole is a wormhole connection mapping tool for [EVE online](http://www.youtube.com/watch?v=XrYe_4vHzgE&t=11m55s).

[![screenshot](http://i.imgur.com/BDXfn5w.png)](http://i.imgur.com/BDXfn5w.png)

alternatives include

- https://tripwire.eve-apps.com/
- https://github.com/marbindrakon/eve-wspace
- https://eveeye.com/

it uses [websockets](http://caniuse.com/#search=websockets) when available and falls back onto AJAX for the in-game browser (but loses pushed updates because long-polling is stupid). drawing is done in [canvas](http://caniuse.com/#search=canvas) to make sure IE users can't use it (and the in-game browser has no dashed line support, so that's good too).

setup
--

1. `apt install python3-dev libleveldb-dev`
1. `pip3 install -r requirements.txt`
1. `wget https://www.fuzzwork.co.uk/dump/sqlite-latest.sqlite.bz2`
1. `bunzip2 sqlite-latest.sqlite.bz2`
1. `./setup_db.py sqlite-latest.sqlite`
1. `./pyhole`
1. after confirming everything works, you'll probably want to set up `lighttpd` like so:

        $HTTP["host"] == "map.hellsinker.org" {
        	server.document-root = "/var/www/map.hellsinker.org/"
        	$HTTP["url"] !~ "^/static/" {
        		proxy.server = ("" => (("host" => "127.0.0.1", "port" => 8001)))
        	}
        }
