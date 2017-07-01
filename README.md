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

		HTTP["host"] == "map.hellsinker.org" {
			server.document-root = "/var/www/map.hellsinker.org/"
			$HTTP["url"] !~ "^/static/" {
				proxy.server = ("" => (("host" => "127.0.0.1", "port" => 8001)))
			}
		}

	or nginx like so:

		server {
			server_name map.hellsinker.org;

			add_header X-Frame-Options DENY;
			add_header X-Content-Type-Options nosniff;
			add_header Content-Security-Policy "default-src none; style-src 'self' 'unsafe-inline'; img-src https: 'self';  script-src 'self' 'sha256-MDElaJcvNFhyCNF8YWlT8NsWoyXNd4Mwoz75JPz17Ok=' https://ajax.googleapis.com https://cdnjs.  cloudflare.com; connect-src wss://map.hellsinker.org";
			add_header X-Xss-Protection "1; mode=block";

			location /static {
				root /var/www/map.hellsinker.org;
			}

			location / {
				include proxy_params;
				proxy_pass http://127.0.0.1:8003;
			}

			location /map.ws {
				include proxy_params;
				proxy_http_version 1.1;
				proxy_read_timeout 30m;
				proxy_set_header Upgrade $http_upgrade;
				proxy_set_header Connection "upgrade";
				proxy_pass http://127.0.0.1:8003;
			}
		}
