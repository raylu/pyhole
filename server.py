#!/usr/bin/env python3

import cleancss
import http.cookies
import io
import json
import tornado.auth
import tornado.ioloop
import tornado.web
import tornado.websocket
import operator
import os

import config
import db

class BaseHandler(tornado.web.RequestHandler):
	def render(self, *args, **kwargs):
		kwargs['websocket_host'] = config.web.websocket_host
		kwargs['path'] = self.request.uri
		return super(BaseHandler, self).render(*args, **kwargs)

	def render_string(self, *args, **kwargs):
		s = super(BaseHandler, self).render_string(*args, **kwargs)
		return s.replace(b'\n', b'') # this is like Django's {% spaceless %}

	def get_current_user(self):
		user_id = self.get_secure_cookie('user_id')
		if user_id is not None:
			try:
				return int(user_id)
			except ValueError:
				return user_id # OI OAuth user

class MainHandler(BaseHandler):
	def get(self):
		self.render('home.html')

class LoginHandler(BaseHandler):
	def post(self):
		username = self.get_argument('username')
		password = self.get_argument('password')
		user_id = db.check_login(username, password)
		if user_id is not None:
			self.set_secure_cookie('user_id', str(user_id), expires_days=90)
			self.set_secure_cookie('username', username, expires_days=90)
			self.redirect('/map')
		else:
			self.redirect('/')

class OIHandler(BaseHandler, tornado.auth.OAuth2Mixin):
	_OAUTH_AUTHORIZE_URL = 'https://oauth.talkinlocal.org/authorize'
	_OAUTH_ACCESS_TOKEN_URL = 'https://oauth.talkinlocal.org/token'
	def get(self):
		code = self.get_argument('code', None)
		if not code:
			self.authorize_redirect(client_id=config.web.oi_client_id,
					redirect_uri=config.web.oi_redirect_uri, scope=['auth_info'])
			return
		rt_url = self._oauth_request_token_url(client_id=config.web.oi_client_id,
				client_secret=config.web.oi_client_secret, code=code,
				redirect_uri=config.web.oi_redirect_uri, extra_params={'grant_type': 'authorization_code'})
		data = self.fetch_json(rt_url)
		access_token = data['access_token']
		data = self.fetch_json('https://oauth.talkinlocal.org/api/v1/auth_user?access_token=' + access_token)
		user = data['user']
		if user['auth_status'] != 'Internal':
			self.write(user['auth_status'] + ' users are not allowed')
			return
		self.set_secure_cookie('user_id', user['user_id'], expires_days=90)
		self.set_secure_cookie('username', user['user_id'], expires_days=90)
		self.redirect('/map')

	def fetch_json(self, url):
		client = tornado.httpclient.HTTPClient()
		response = client.fetch(url)
		data = json.load(io.TextIOWrapper(response.buffer, 'utf-8'))
		client.close()
		return data

class LogoutHandler(BaseHandler):
	def get(self):
		self.clear_cookie('user_id')
		self.redirect('/')

class MapHandler(BaseHandler):
	@tornado.web.authenticated
	def get(self):
		igb = self.request.headers['User-Agent'].endswith('EVE-IGB')
		self.render('map.html', igb=igb)

class AccountHandler(BaseHandler):
	@tornado.web.authenticated
	def get(self):
		if isinstance(self.current_user, bytes):
			self.render('account.html', username=None)
			return
		username = self.get_secure_cookie('username')
		users = None
		with db.conn.cursor() as c:
			user_id = self.get_secure_cookie('user_id')
			r = db.query_one(c, 'SELECT admin FROM users WHERE id = ?', user_id)
			admin = bool(r.admin)
			if admin:
				users = db.query(c, 'SELECT username, admin FROM users')
				users = list(users)
		self.render('account.html', username=username, admin=admin, users=users)

class PasswordHandler(BaseHandler):
	@tornado.web.authenticated
	def post(self):
		user_id = self.get_current_user()
		password = self.get_argument('password')
		db.change_password(user_id, password)
		self.redirect('/account')

class CreateUserHandler(BaseHandler):
	@tornado.web.authenticated
	def post(self):
		with db.conn.cursor() as c:
			r = db.query_one(c, 'SELECT admin FROM users WHERE id = ?', self.current_user)
			admin = bool(r.admin)
			if not admin:
				raise tornado.web.HTTPError(403)
		username = self.get_argument('username')
		password = self.get_argument('password')
		if not username or not password:
			raise tornado.web.HTTPError(400)
		db.create_user(self.get_secure_cookie('username'), username, password)
		self.redirect('/account')

class LogHandler(BaseHandler):
	@tornado.web.authenticated
	def get(self):
		with db.conn.cursor() as c:
			log_rows = db.query(c, 'SELECT time, username, log_message FROM logs ORDER BY time DESC LIMIT 50')
			log = map(operator.attrgetter('__dict__'), log_rows)
			self.render('log.html', log=log)

websockets = set()
class DataHandler:
	def __send_map(self, map_json):
		self.write_message('MAP ' + map_json)
		for ws in websockets:
			if ws is not self:
				ws.write_message('MAP ' + map_json)

	def __send_err(self, e):
		self.write_message('ERR ' + e.message)

	def helo(self):
		with db.conn.cursor() as c:
			r = db.query_one(c, 'SELECT json from maps')
		self.write_message('MAP ' + r.json)

	def add(self, system_json):
		try:
			system = json.loads(system_json)
			map_json = db.add_system(self.username, system)
			self.__send_map(map_json)
		except db.UpdateError as e:
			self.__send_err(e)

	def delete(self, system_name):
		try:
			map_json = db.delete_system(self.username, system_name)
			self.__send_map(map_json)
		except db.UpdateError as e:
			self.__send_err(e)

	def detach(self, system_name):
		try:
			map_json = db.detach_system(self.username, system_name)
			self.__send_map(map_json)
		except db.UpdateError as e:
			self.__send_err(e)

	def toggle_eol(self, system_names):
		try:
			src, dest = system_names.split(' ', 1)
			map_json = db.toggle_eol(self.username, src, dest)
			self.__send_map(map_json)
		except db.UpdateError as e:
			self.__send_err(e)

	def toggle_reduced(self, system_names):
		try:
			src, dest = system_names.split(' ', 1)
			map_json = db.toggle_reduced(self.username, src, dest)
			self.__send_map(map_json)
		except db.UpdateError as e:
			self.__send_err(e)

	def toggle_critical(self, system_names):
		try:
			src, dest = system_names.split(' ', 1)
			map_json = db.toggle_critical(self.username, src, dest)
			self.__send_map(map_json)
		except db.UpdateError as e:
			self.__send_err(e)

	def autocomplete(self, partial):
		with db.eve_conn.cursor() as c:
			r = db.query(c, '''
					SELECT solarSystemName FROM mapSolarSystems
					WHERE solarSystemName LIKE ? and security > 0.0
					''', partial + '%')
			systems = [row.solarSystemName for row in r]
		self.write_message('SYS ' + json.dumps(systems))

	def signatures(self, text):
		lines = text.split('\n')
		header = lines[0]
		index = header.rindex(' ')
		system_name = header[:index]
		action = header[index+1:]
		sigs = {}
		for l in lines[1:]:
			if len(l) == 0:
				break
			fields = l.split('\t')
			if len(fields) != 6: # ID, scan group, group, type, signal, distance
				break
			if not fields[1].startswith('Cosmic '):
				break
			fields[1] = fields[1][7:]
			fields[4] = float(fields[4][:-1]) # '100.0%' -> 100.0
			sigs[fields[0]] = fields[:5]
		if len(sigs):
			map_json = db.update_signatures(system_name, action, sigs)
			self.__send_map(map_json)

	def signature_note(self, text):
		system_name, sig_id, note = text.split('\n')
		map_json = db.set_signature_note(system_name, sig_id, note)
		self.__send_map(map_json)

	def delete_signature(self, args):
		split = args.split()
		system_name = split[0]
		if len(split) > 1:
			sig_id = split[1]
		else:
			sig_id = None
		map_json = db.delete_signature(system_name, sig_id)
		self.__send_map(map_json)

class MapWSHandler(DataHandler, tornado.websocket.WebSocketHandler):
	def __init__(self, *args, **kwargs):
		super(MapWSHandler, self).__init__(*args, **kwargs)
		self.username = None

	def on_message(self, message):
		split = message.split(' ', 1)
		if self.username is None and split[0] != 'HELO':
			return
		if split[0] == 'HELO':
			cookies = http.cookies.SimpleCookie(split[1])
			username_cookie = cookies['username'].value
			self.username = tornado.web.decode_signed_value(config.web.cookie_secret, 'username', username_cookie)
			self.helo()
			websockets.add(self)
		elif split[0] == 'ADD':
			self.add(split[1])
		elif split[0] == 'DELETE':
			self.delete(split[1])
		elif split[0] == 'DETACH':
			self.detach(split[1])
		elif split[0] == 'EOL':
			self.toggle_eol(split[1])
		elif split[0] == 'REDUCED':
			self.toggle_reduced(split[1])
		elif split[0] == 'CRITICAL':
			self.toggle_critical(split[1])
		elif split[0] == 'SYS':
			self.autocomplete(split[1])
		elif split[0] == 'SIGS':
			self.signatures(split[1])
		elif split[0] == 'SIGNOTE':
			self.signature_note(split[1])
		elif split[0] == 'DELSIG':
			self.delete_signature(split[1])
		else:
			print('unhandled message', message)

	def on_close(self):
		try:
			websockets.remove(self)
		except KeyError:
			pass

class MapAJAXHandler(DataHandler, tornado.web.RequestHandler):
	def get(self, command):
		self.username = self.get_secure_cookie('username') # auth check
		args = self.get_argument('args', None)
		if command == 'HELO':
			self.helo()
		elif command == 'ADD':
			self.add(args)
		elif command == 'DELETE':
			self.delete(args)
		elif command == 'DETACH':
			self.detach(args)
		elif command == 'EOL':
			self.toggle_eol(args)
		elif command == 'REDUCED':
			self.toggle_reduced(args)
		elif command == 'CRITICAL':
			self.toggle_critical(args)
		elif command == 'SYS':
			self.autocomplete(args)
		elif command == 'SIGS':
			self.signatures(args)
		elif command == 'SIGNOTE':
			self.signature_note(args)
		elif command == 'DELSIG':
			self.delete_signature(args)
		else:
			print('unhandled message', command)

	def write_message(self, message):
		self.set_header('Content-Type', 'application/json')
		self.finish(json.dumps(message))

class CSSHandler(tornado.web.RequestHandler):
	def get(self, css_path):
		css_path = os.path.join(os.path.dirname(__file__), 'static', css_path) + '.ccss'
		with open(css_path, 'r') as f:
			self.set_header('Content-Type', 'text/css')
			self.write(cleancss.convert(f))

if __name__ == '__main__':
	tornado.web.Application(
		handlers=[
			(r'/', MainHandler),
			(r'/login', LoginHandler),
			(r'/oi', OIHandler),
			(r'/logout', LogoutHandler),
			(r'/map', MapHandler),
			(r'/map.ws', MapWSHandler),
			(r'/map.json/(.+)', MapAJAXHandler),
			(r'/account', AccountHandler),
			(r'/password', PasswordHandler),
			(r'/create_user', CreateUserHandler),
			(r'/(css/.+)\.css', CSSHandler),
			(r'/log', LogHandler),
		],
		template_path=os.path.join(os.path.dirname(__file__), 'templates'),
		static_path=os.path.join(os.path.dirname(__file__), 'static'),
		cookie_secret=config.web.cookie_secret,
		xsrf_cookies=True,
		login_url='/',
		debug=True,
	).listen(config.web.port)
	print('Listening on :%d' % config.web.port)
	tornado.ioloop.IOLoop.instance().start()
