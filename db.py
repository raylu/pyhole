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

class ACTIONS:
	CREATE_USER = 1
	ADD_SYSTEM = 2
	DELETE_SYSTEM = 3
	TOGGLE_EOL = 4
	DETACH_SYSTEM = 5
	MASS_CHANGE = 6
	TOGGLE_FRIGATE = 7

class MASS:
	STABLE = 'stable'
	REDUCED = 'reduced'
	CRITICAL = 'critical'

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

def create_user(creator, username, password):
	hashed, salt_hex = __gen_hash(password)
	with conn.cursor() as c:
		c.execute('INSERT INTO users (username, password, salt, admin) VALUES(?, ?, ?, 0)',
				[username, hashed, salt_hex])
		log_action(c, creator, ACTIONS.CREATE_USER, {'username': username})

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

def add_system(username, system):
	def add_node(node):
		found = False
		if node['name'] == system['name']:
			raise UpdateError('src system already exists!')
		if 'connections' in node:
			for c in node['connections']:
				if add_node(c):
					found = True
		# no src when root node; just run above code to dupes
		if 'src' in system and node['name'] == system['src']:
			node.setdefault('connections', [])
			node['connections'].append(system)
			found = True
		return found

	root_system = 'src' not in system
	wspace_system = False
	if system['dest'][0].upper() == 'J':
		try:
			int(system['dest'][1:4])
			wspace_system = True
		except ValueError:
			pass
	if not wspace_system:
		with eve_conn.cursor() as c:
			r = query_one(c, '''
			SELECT solarSystemName, solarSystemID, security, regionID FROM mapSolarSystems
			WHERE solarSystemName = ?
			''', system['dest'])
			if r is None:
				raise UpdateError('system does not exist')
			system['dest'] = r.solarSystemName
			if r.security >= 0.45:
				system['class'] = 'highsec'
			elif r.security > 0.0:
				system['class'] = 'lowsec'
			else:
				system['class'] = 'nullsec'
			s = query_one(c, '''
			SELECT regionName FROM mapRegions
			WHERE regionID = ?
			''', r.regionID)
			system['region'] = s.regionName
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

			if 'src' in system:
				stargate = query_one(c, '''
				SELECT 1 from mapSolarSystemJumps
				JOIN mapSolarSystems ON toSolarSystemID = solarSystemID
				WHERE fromSolarSystemID = ? AND solarSystemName = ?;
				''', r.solarSystemID, system['src'])
				system['stargate'] = (stargate is not None)
	with conn.cursor() as c:
		if wspace_system:
			system['dest'] = system['dest'].upper()
			r = query_one(c, '''
			SELECT class, effect, w1.name, w1.dest, w1.lifetime, w1.jump_mass, w1.max_mass,
			                      w2.name, w2.dest, w2.lifetime, w2.jump_mass, w2.max_mass
			FROM wh_systems
			JOIN wh_types AS w1 ON static1 = w1.id
			LEFT JOIN wh_types AS w2 ON static2 = w2.id
			WHERE wh_systems.name = ?;
			''', system['dest'])
			if r is None:
				raise UpdateError('system does not exist')
			system['class'] = getattr(r, 'class')
			system['effect'] = r.effect
			system['static1'] = {
				'name': r.raw[2],
				'dest': r.raw[3],
				'lifetime': r.raw[4],
				'jump_mass': r.raw[5],
				'max_mass': r.raw[6],
			}
			if r.raw[7] is not None:
				system['static2'] = {
					'name': r.raw[7],
					'dest': r.raw[8],
					'lifetime': r.raw[9],
					'jump_mass': r.raw[10],
					'max_mass': r.raw[11],
				}

		system['mass'] = MASS.STABLE
		system['name'] = system['dest']
		del system['dest']
		r = query_one(c, 'SELECT json from maps')
		map_data = json.loads(r.json)
		found = False
		for node in map_data: # try to add to non-roots first (and check for duplicates)
			if add_node(node):
				found = True
		if not found:
			if root_system:
				map_data.append(system)
			else:
				raise UpdateError('src system not found')
		map_json = json.dumps(map_data)
		c.execute('UPDATE maps SET json = ?', (map_json,))
		log_action(c, username, ACTIONS.ADD_SYSTEM, system)
	return map_json

def delete_system(username, system_name):
	def delete_node(node):
		if 'connections' in node:
			for i, c in enumerate(node['connections']):
				if c['name'] == system_name:
					node['connections'].pop(i)
					return c
				deleted_node = delete_node(c)
				if deleted_node:
					return deleted_node

	with conn.cursor() as c:
		r = query_one(c, 'SELECT json from maps')
		map_data = json.loads(r.json)
		for i, root_node in enumerate(map_data):
			if root_node['name'] == system_name:
				deleted_node = map_data.pop(i)
				break
		else:
			for node in map_data:
				deleted_node = delete_node(node)
				if deleted_node is not None:
					break
		if deleted_node is None:
			raise UpdateError('system not found')
		map_json = json.dumps(map_data)
		c.execute('UPDATE maps SET json = ?', (map_json,))
		log_action(c, username, ACTIONS.DELETE_SYSTEM, deleted_node)
	return map_json

def detach_system(username, system_name):
	def detach_node(node):
		if 'connections' in node:
			for i, c in enumerate(node['connections']):
				if c['name'] == system_name:
					node['connections'].pop(i)
					return c
				detached_node = detach_node(c)
				if detached_node:
					return detached_node

	with conn.cursor() as c:
		r = query_one(c, 'SELECT json from maps')
		map_data = json.loads(r.json)
		for node in map_data:
			detached_node = detach_node(node)
			if detached_node is not None:
				break
		if detached_node is None:
			raise UpdateError('system not found')
		map_data.append(detached_node)
		map_json = json.dumps(map_data)
		c.execute('UPDATE maps SET json = ?', (map_json,))
		log_action(c, username, ACTIONS.DETACH_SYSTEM, detached_node)
	return map_json

def __toggle(fn, src, dest, username, action):
	def toggle_node(node):
		if 'connections' in node:
			for i, c in enumerate(node['connections']):
				if node['name'] == src and c['name'] == dest:
					fn(c)
					return c
				toggled_node = toggle_node(c)
				if toggled_node:
					return toggled_node

	with conn.cursor() as c:
		r = query_one(c, 'SELECT json from maps')
		map_data = json.loads(r.json)
		changed_node = None
		for node in map_data:
			changed_node = toggle_node(node)
			if changed_node is not None:
				break
		if changed_node is None:
			raise UpdateError('system not found')
		map_json = json.dumps(map_data)
		c.execute('UPDATE maps SET json = ?', (map_json,))
		log_action(c, username, action, changed_node)
	return map_json

def toggle_eol(username, src, dest):
	def toggle_connection(c):
		c['eol'] = not c['eol']

	return __toggle(toggle_connection, src, dest, username, ACTIONS.TOGGLE_EOL)

def toggle_reduced(username, src, dest):
	def toggle_connection(c):
		if c['mass'] == MASS.REDUCED:
			c['mass'] = MASS.STABLE
		else:
			c['mass'] = MASS.REDUCED

	return __toggle(toggle_connection, src, dest, username, ACTIONS.MASS_CHANGE)

def toggle_critical(username, src, dest):
	def toggle_connection(c):
		if c['mass'] == MASS.CRITICAL:
			c['mass'] = MASS.STABLE
		else:
			c['mass'] = MASS.CRITICAL

	return __toggle(toggle_connection, src, dest, username, ACTIONS.MASS_CHANGE)

def toggle_frigate(username, src, dest):
	def toggle_connection(c):
		c['frigate'] = not c['frigate']

	return __toggle(toggle_connection, src, dest, username, ACTIONS.TOGGLE_FRIGATE)

def update_signatures(system_name, action, new_sigs):
	def update_sigs_node(node):
		if node['name'] == system_name:
			if action == 'replace':
				replace = True
			elif action == 'add':
				replace = False
			else:
				raise UpdateError('invalid signature update action')
			old_sigs = node.get('signatures', [])
			write_sigs = []
			for sig in old_sigs:
				sig_id = sig[0]
				if sig_id in new_sigs:
					new_sig = new_sigs[sig_id]
					if new_sig[4] >= sig[4]: # compare signal strength
						new_sig.append(sig[5]) # keep old note
						write_sigs.append(new_sig)
					else:
						write_sigs.append(sig)
					del new_sigs[sig_id]
				elif not replace:
					write_sigs.append(sig)
			for sig in new_sigs.values():
				sig.append('') # add blank note
				write_sigs.append(sig)
			node['signatures'] = write_sigs
			return True
		if 'connections' in node:
			for c in node['connections']:
				if update_sigs_node(c):
					return True

	with conn.cursor() as c:
		r = query_one(c, 'SELECT json from maps')
		map_data = json.loads(r.json)
		if not any(map(update_sigs_node, map_data)):
			raise UpdateError('system not found')
		map_json = json.dumps(map_data)
		c.execute('UPDATE maps SET json = ?', (map_json,))
	return map_json

def delete_signature(system_name, sig_id):
	def del_sig_node(node):
		if node['name'] == system_name:
			if sig_id is None: # delete all the sigs
				del node['signatures']
			else: # find and delete the sig in this system
				index = None
				for i, sig in enumerate(node['signatures']):
					if sig[0] == sig_id:
						index = i
						break
				if index is None:
					raise UpdateError('sig id not found')
				node['signatures'].pop(index)
			return True
		if 'connections' in node:
			for c in node['connections']:
				if del_sig_node(c):
					return True

	with conn.cursor() as c:
		r = query_one(c, 'SELECT json from maps')
		map_data = json.loads(r.json)
		if not any(map(del_sig_node, map_data)):
			raise UpdateError('system not found')
		map_json = json.dumps(map_data)
		c.execute('UPDATE maps SET json = ?', (map_json,))
	return map_json

def set_signature_note(system_name, sig_id, note):
	def set_note_node(node):
		if node['name'] == system_name:
			for sig in node['signatures']:
				if sig[0] == sig_id:
					sig[5] = note
					break
			return True
		if 'connections' in node:
			for c in node['connections']:
				if set_note_node(c):
					return True

	with conn.cursor() as c:
		r = query_one(c, 'SELECT json from maps')
		map_data = json.loads(r.json)
		if not any(map(set_note_node, map_data)):
			raise UpdateError('system not found')
		map_json = json.dumps(map_data)
		c.execute('UPDATE maps SET json = ?', (map_json,))
	return map_json

def log_action(cursor, username, action, details):
	if action == ACTIONS.ADD_SYSTEM:
		if 'src' not in details:
			log_message = 'added new root system ' + details['name']
		else:
			log_message = 'added system {name} connected to {src}'.format(**details)
	elif action == ACTIONS.DELETE_SYSTEM:
		log_message = 'deleted system ' + details['name']
		if 'connections' in details:
			for system in details['connections']:
				log_action(cursor, username, ACTIONS.DELETE_SYSTEM, system)
	elif action == ACTIONS.DETACH_SYSTEM:
		log_message = 'detached system ' + details['name']
	elif action == ACTIONS.TOGGLE_EOL:
		if details['eol']:
			log_message = 'set {name} to EoL'.format(**details)
		else:
			log_message = 'reverted {name} to not EoL'.format(**details)
	elif action == ACTIONS.MASS_CHANGE:
		if details['mass'] == MASS.STABLE:
			log_message = 'reverted {name} to {mass}'.format(**details)
		else:
			log_message = 'set {name} to {mass}'.format(**details)
	elif action == ACTIONS.CREATE_USER:
		log_message = 'created user ' + details['username']
	elif action == ACTIONS.TOGGLE_FRIGATE:
		if details['frigate']:
			log_message = 'set {name} as frigate only'.format(**details)
		else:
			log_message = 'set {name} as not frigate only'.format(**details)
	else:
		raise RuntimeError('unhandled log_action')

	cursor.execute('''
	INSERT INTO logs (time, username, action_id, log_message)
	VALUES(UTC_TIMESTAMP(), ?, ?, ?)
	''', [username, action, log_message])

class DBRow:
	def __init__(self, result, description):
		for i, f in enumerate(description):
			setattr(self, f[0], result[i])
		self.raw = result

	def __str__(self):
		return '<DBRow>: ' + str(self.__dict__)
