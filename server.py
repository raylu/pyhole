#!/usr/bin/env python3

import http.cookies
import json
from lesscss import lessc
import tornado.ioloop
import tornado.web
import tornado.websocket
import operator
import os

import config
import db

class BaseHandler(tornado.web.RequestHandler):
	def render(self, *args, **kwargs):
		kwargs['host'] = config.web.host
		return super(BaseHandler, self).render(*args, **kwargs)

	def render_string(self, *args, **kwargs):
		s = super(BaseHandler, self).render_string(*args, **kwargs)
		return s.replace(b'\n', b'') # this is like Django's {% spaceless %}

	def get_current_user(self):
		user_id = self.get_secure_cookie('user_id')
		if user_id is not None:
			return int(user_id)

class MainHandler(BaseHandler):
	def get(self):
		self.render('home.html')

class LoginHandler(BaseHandler):
	def post(self):
		username = self.get_argument('username')
		password = self.get_argument('password')
		user_id = db.check_login(username, password)
		success = False
		if user_id is not None:
			self.set_secure_cookie('user_id', str(user_id), expires_days=90)
			success = True
		self.render('login.html', success=success)

class MapHandler(BaseHandler):
	@tornado.web.authenticated
	def get(self):
		self.render('map.html')

class MapWSHandler(tornado.websocket.WebSocketHandler):
	def on_message(self, message):
		split = message.split(' ', 1)
		if split[0] == 'HELO':
			self.helo(split[1])
		elif split[0] == 'ADD':
			self.add(split[1])
		elif split[0] == 'DELETE':
			self.delete(split[1])
		else:
			print('unhandled message', message)

	def __send_map(self, map_json):
		self.write_message('MAP ' + map_json)

	def __send_err(self, e):
		self.write_message('ERR ' + e.message)

	def helo(self, cookie):
		# check that the user has a valid user_id
		cookie = http.cookies.SimpleCookie(cookie)
		try:
			user_id_cookie = cookie["user_id"].value
			user_id = int(tornado.web.decode_signed_value(config.web.cookie_secret, "user_id", user_id_cookie))
		except KeyError:
			return
		with db.conn.cursor() as c:
			r = db.query_one(c, 'SELECT json from maps')
		map_json = r.json
		self.__send_map(map_json)

	def add(self, system_json):
		try:
			system = json.loads(system_json)
			map_json = db.add_system(system)
			self.__send_map(map_json)
		except db.UpdateError as e:
			self.__send_err(e)

	def delete(self, system_name):
		try:
			map_json = db.delete_system(system_name)
			self.__send_map(map_json)
		except db.UpdateError as e:
			self.__send_err(e)

class CSSHandler(tornado.web.RequestHandler):
	def get(self, css_path):
		css_path = os.path.join(os.path.dirname(__file__), 'static', css_path) + '.less'
		with open(css_path, 'r') as f:
			self.set_header('Content-Type', 'text/css')
			css = lessc.compile(f.read())
			self.write(css)

if __name__ == '__main__':
	tornado.web.Application(
		handlers=[
			(r'/', MainHandler),
			(r'/login', LoginHandler),
			(r'/map', MapHandler),
			(r'/map.ws', MapWSHandler),
			(r'/(css/.+)\.css', CSSHandler),
		],
		template_path=os.path.join(os.path.dirname(__file__), 'templates'),
		static_path=os.path.join(os.path.dirname(__file__), 'static'),
		cookie_secret=config.web.cookie_secret,
		xsrf_cookies=True,
		login_url='/login',
		debug=True,
	).listen(config.web.port)
	print('Listening on :%d' % config.web.port)
	tornado.ioloop.IOLoop.instance().start()
