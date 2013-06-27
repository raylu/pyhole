import binascii
import hashlib
import hmac
import io
import json
import oursql
import os
import tornado.httpclient

conn = oursql.connect(db='pyhole', user='pyhole', passwd='pyhole', autoreconnect=True)
eve_conn = oursql.connect(db='eve', user='eve', passwd='eve', autoreconnect=True)

def query(cursor, sql, *args):
	cursor.execute(sql, args)
	while True:
		r = cursor.fetchone()
		if r is None:
			break
		attribs = DBRow(r, cursor.description)
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

def __gen_hash(password):
	salt = os.urandom(16)
	h = hmac.new(salt, password.encode('utf-8'), hashlib.sha256)
	hashed = h.hexdigest()
	salt_hex = binascii.hexlify(salt)
	return hashed, salt_hex

def create_user(username, password):
	hashed, salt_hex = __gen_hash(password)
	with conn.cursor() as c:
		c.execute('INSERT INTO users (username, password, salt) VALUES(?, ?, ?)',
				[username, hashed, salt_hex])

def check_login(username, password):
	with conn.cursor() as c:
		r = query_one(c, 'SELECT id, password, salt FROM users WHERE username = ?', username)
	if r is None:
		return
	salt = binascii.unhexlify(bytes(r.salt, 'ascii'))
	h = hmac.new(salt, password.encode('utf-8'), hashlib.sha256)
	if h.hexdigest() == r.password:
		return r.id

def change_password(user_id, password):
	hashed, salt_hex = __gen_hash(password)
	with conn.cursor() as c:
		c.execute('UPDATE users SET password = ?, salt = ? WHERE id = ?',
				[hashed, salt_hex, user_id])
		if c.rowcount != 1:
			raise RuntimeError('expected to update 1 row, affected {}'.format(c.rowcount))

class UpdateError(Exception):
	def __init__(self, message):
		self.message = message

def add_system(system):
	def add_node(node):
		if node['name'] == system['src']:
			node.setdefault('connections', [])
			system['name'] = system['dest']
			del system['dest']
			node['connections'].append(system)
			return True
		if 'connections' in node:
			for c in node['connections']:
				if add_node(c):
					return True

	wspace_system = False
	if system['dest'][0] == 'J':
		try:
			int(system['dest'][1:])
			wspace_system = True
		except ValueError:
			pass
	if not wspace_system:
		with eve_conn.cursor() as c:
			r = query_one(c, '''
			SELECT solarSystemID, security FROM mapSolarSystems
			WHERE solarSystemName = ?
			''', system['dest'])
			if r is None:
				raise UpdateError('system does not exist')
			security = round(r.security, 1)
			if security >= 0.5:
				system['class'] = 'highsec'
			elif security >= 0.0:
				system['class'] = 'lowsec'
			else:
				system['class'] = 'nullsec'
			client = tornado.httpclient.HTTPClient()
			ec_api = 'http://api.eve-central.com/api/route/from/{}/to/{}'
			jumps = {
				'Jita': 30000142,
				'Amarr': 30002187,
				'Dodixie': 30002659,
				'Rens': 30002510,
				'Hek': 30002053,
			}
			for trade_hub in jumps.keys():
				system_id = jumps[trade_hub]
				response = client.fetch(ec_api.format(r.solarSystemID, system_id))
				route = json.load(io.TextIOWrapper(response.buffer, 'utf-8'))
				route = map(lambda j: (j['to']['name'], j['to']['security']), route)
				jumps[trade_hub] = list(route)
			client.close()
			system['jumps'] = jumps
	with conn.cursor() as c:
		if wspace_system:
			r = query_one(c, '''
			SELECT class, effect, w1.name, w1.dest, w2.name, w2.dest
			FROM wh_systems
			JOIN wh_types AS w1 ON static1 = w1.id
			LEFT JOIN wh_types AS w2 ON static2 = w2.id
			WHERE wh_systems.name = ?;
			''', system['dest'])
			system['class'] = getattr(r, 'class')
			system['effect'] = r.effect
			system['static1'] = {'name': r.raw[2], 'dest': r.raw[3]}
			if r.raw[4] is not None:
				system['static2'] = {'name': r.raw[4], 'dest': r.raw[5]}

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

def toggle_eol(src, dest):
	def toggle_node(node):
		if 'connections' in node:
			for i, c in enumerate(node['connections']):
				if node['name'] == src and c['name'] == dest:
					c['eol'] = not c['eol']
					return True
				if toggle_node(c):
					return True

	with conn.cursor() as c:
		r = query_one(c, 'SELECT json from maps')
		map_data = json.loads(r.json)
		if not toggle_node(map_data):
			raise UpdateError('system not found')
		map_json = json.dumps(map_data)
		c.execute('UPDATE maps SET json = ?', (map_json,))
	return map_json

class DBRow:
	def __init__(self, result, description):
		for i, f in enumerate(description):
			setattr(self, f[0], result[i])
		self.raw = result

	def __str__(self):
		return '<DBRow>: ' + str(self.__dict__)
