import binascii
import hashlib
import hmac
import json
import oursql
import os

conn = oursql.connect(db='pyhole', user='pyhole', passwd='pyhole', autoreconnect=True)
eve_conn = oursql.connect(db='eve', user='eve', passwd='eve', autoreconnect=True)

def query(cursor, sql, *args):
	cursor.execute(sql, args)
	while True:
		r = cursor.fetchone()
		if r is None:
			break
		attribs = DBRow()
		for i, f in enumerate(cursor.description):
			setattr(attribs, f[0], r[i])
		yield attribs

def query_one(cursor, sql, *args):
	results = query(cursor, sql, *args)
	try:
		r = next(results)
	except StopIteration:
		return
	try:
		next(results)
	except StopIteration:
		return r
	else:
		raise RuntimeError('multiple rows for query {}, {}'.format(sql, args))

def create_user(username, password):
	salt = os.urandom(16)
	h = hmac.new(salt, password.encode('utf-8'), hashlib.sha256)
	hashed = h.hexdigest()
	salt_hex = binascii.hexlify(salt)
	with conn.cursor() as c:
		c.execute('INSERT INTO users (username, password, salt) VALUES(?, ?, ?)',
				username, hashed, salt_hex)

def check_login(username, password):
	with conn.cursor() as c:
		r = query_one(c, 'SELECT id, password, salt FROM users WHERE username = ?', username)
	if r is None:
		return
	salt = binascii.unhexlify(bytes(r.salt, 'ascii'))
	h = hmac.new(salt, password.encode('utf-8'), hashlib.sha256)
	if h.hexdigest() == r.password:
		return r.id

class UpdateError(Exception):
	def __init__(self, message):
		self.message = message

def add_system(system):
	def add_node(node):
		if node['name'] == system['src']:
			node.setdefault('connections', [])
			o = {'name': system['dest']}
			if 'to' in system:
				o['to'] = system['to']
			if 'from' in system:
				o['from'] = system['from'],
			if 'eol' in system:
				o['eol'] = system['eol']
			node['connections'].append(o)
			return True
		if 'connections' in node:
			for c in node['connections']:
				if add_node(c):
					return True

	with conn.cursor() as c:
		r = query_one(c, 'SELECT json from maps')
		map_data = json.loads(r.json)
		if not add_node(map_data):
			raise UpdateError('src system not found')
		map_json = json.dumps(map_data)
		c.execute('UPDATE maps SET json = ?', (map_json,))
	return map_json

def delete_system(system_name):
	def delete_node(node):
		if 'connections' in node:
			for i, c in enumerate(node['connections']):
				if c['name'] == system_name:
					node['connections'].pop(i)
					return True
				if delete_node(c):
					return True

	with conn.cursor() as c:
		r = query_one(c, 'SELECT json from maps')
		map_data = json.loads(r.json)
		if map_data['name'] == system_name:
			raise UpdateError('cannot delete root node')
		if not delete_node(map_data): # this will not delete the root node (even if it passed previous check)
			raise UpdateError('system not found')
		map_json = json.dumps(map_data)
		c.execute('UPDATE maps SET json = ?', (map_json,))
	return map_json

class DBRow:
	def __str__(self):
		return '<DBRow>: ' + str(self.__dict__)
