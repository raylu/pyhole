#!/usr/bin/env python3

import json
from lesscss import lessc
import tornado.ioloop
import tornado.web
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

class MainHandler(BaseHandler):
	def get(self):
		self.render('home.html')

class LoginHandler(BaseHandler):
	def post(self):
		username = self.get_argument('username')
		password = self.get_argument('password')
		status = db.check_login(username, password)
		self.render('login.html', status=status)

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
			(r'/(css/.+)\.css', CSSHandler),
		],
		template_path=os.path.join(os.path.dirname(__file__), 'templates'),
		static_path=os.path.join(os.path.dirname(__file__), 'static'),
		cookie_secret=config.web.cookie_secret,
		debug=True,
	).listen(config.web.port)
	print('Listening on :%d' % config.web.port)
	tornado.ioloop.IOLoop.instance().start()
