pyhole is a wormhole connection mapping tool for [EVE online](http://www.youtube.com/watch?v=XrYe_4vHzgE&t=11m55s).

[![screenshot](http://i.imgur.com/4uWJUhfl.png)](http://i.imgur.com/4uWJUhf.png)

alternatives include

- http://whmap.de/ (nice, but slow)
- http://eveeye.com/ (confusing, slow, not built for mapping, buggy, not-free)
- https://github.com/marbindrakon/eve-wspace

it uses [websockets](http://caniuse.com/#search=websockets) when available and falls back onto AJAX for the in-game browser (but loses pushed updates because long-polling is stupid). drawing is done in [canvas](http://caniuse.com/#search=canvas) to make sure IE users can't use it (and the in-game browser has no dashed line support, so that's good too).

setup
--

1. download the latest original.sql.bz2 file from http://evedump.icyone.net/

1. install `mysql-server` (or `mariadb-server`)

        mysql -u root -p
            create database eve;
            grant all on eve.* to eve@localhost identified by 'eve';
        bunzip2 -c original.sql.bz2 | mysql -u eve -peve eve


1. you will need oursql but this is neither packaged nor will pip/easy_install find the right version  
download and extract the zip at https://launchpad.net/oursql/py3k  
on debian, install `libmysqlclient-dev` (even if you're running mariadb)  
on fedora, install `mysql-devel` (or `MariaDB-devel`)  
on both, install `python3-pip`  
`cd` into the `oursql/` directory and then run  
debian: `pip-3.2 install .`  
fedora: `pip-python3 install .`

1. install these dependencies:  
debian: `python3-yaml`  
fedora: `python3-PyYAML`

1. 

        mysql -u root -p
            create database pyhole;
            grant all on pyhole.* to pyhole@localhost identified by 'pyhole';
        mysql -u pyhole -ppyhole pyhole < schema.sql
        mysql -u pyhole -ppyhole pyhole
            insert into maps values('[]');

1. copy `config.yaml.example` to `config.yaml`. edit.

1. 

        python3
            import db
            db.create_user('raylu', 'a')

1. 

        mysql -u pyhole -ppyhole pyhole
            update users set admin = 1;

1. `./server.py`

1. after confirming everything works, you'll probably want to set up `lighttpd` like so:

        $HTTP["host"] == "map.hellsinker.org" {
        	server.document-root = "/var/www/map.hellsinker.org/"
        	$HTTP["url"] !~ "^/static/" {
        		proxy.server = ("" => (("host" => "127.0.0.1", "port" => 8001)))
        	}
        }
