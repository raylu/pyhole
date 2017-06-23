import atexit
import json
from os import path
import struct

from passlib.apps import custom_app_context
import plyvel
import tornado.httpclient

pyhole_dir = path.dirname(path.abspath(__file__))
db_path = path.join(pyhole_dir, 'database')
db = users_db = systems_db = None

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

def init_db(create_if_missing):
	global db, users_db, systems_db
	db = plyvel.DB(db_path, create_if_missing=create_if_missing)
	users_db = db.prefixed_db(b'user-')
	systems_db = db.prefixed_db(b'systems-')

	atexit.register(db.close)

def create_user(username, password, admin):
	if users_db.get(username.encode('utf-8')) is not None:
		raise Exception('user already exists')
	hashed = custom_app_context.encrypt(password)
	user = User(username, hashed, int(admin))
	user.save()

def delete_user(username):
	users_db.delete(username.encode('utf-8'))

def check_login(username, password):
	user = User.get(username)
	if user is None:
		return None
	if custom_app_context.verify(password, user.hashed):
		return user
	else:
		return None

def change_password(username, old_password, new_password):
	user = check_login(username, old_password)
	if user is None:
		return False
	user.hashed = custom_app_context.encrypt(new_password)
	user.save()
	return True

def iter_users():
	with users_db.iterator(include_value=False) as it:
		for username in it:
			yield username.decode('utf-8')

class UpdateError(Exception):
	def __init__(self, message):
		self.message = message

def get_map_json():
	return db.get(b'map').decode('utf-8')

def _get_map():
	return json.loads(get_map_json())

def _set_map(map_data):
	map_json = json.dumps(map_data)
	db.put(b'map', map_json.encode('utf-8'))
	return map_json

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
	ss = SolarSystem.get(system['dest'])
	if ss is None:
		raise UpdateError('system does not exist')
	wspace_system = ss.id > 31000000

	system['region'] = ss.region

	if wspace_system:
		"""
		r = query_one(c, '''
		SELECT class, effect, w1.name, w1.dest, w1.lifetime, w1.jump_mass, w1.max_mass,
							  w2.name, w2.dest, w2.lifetime, w2.jump_mass, w2.max_mass
		FROM wh_systems
		LEFT JOIN wh_types AS w1 ON static1 = w1.id
		LEFT JOIN wh_types AS w2 ON static2 = w2.id
		WHERE wh_systems.name = ?;
		''', system['dest'])
		if r is None:
			raise UpdateError('system does not exist')
		system['class'] = getattr(r, 'class')
		system['effect'] = r.effect
		if r.raw[2] is not None:
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
		"""
	else:
		"""
		if 'src' in system:
			stargate = query_one(c, '''
			SELECT 1 from mapSolarSystemJumps
			JOIN mapSolarSystems ON toSolarSystemID = solarSystemID
			WHERE fromSolarSystemID = ? AND solarSystemName = ?;
			''', r.solarSystemID, system['src'])
			system['stargate'] = (stargate is not None)
		"""

		client = tornado.httpclient.HTTPClient()
		ec_api = 'http://api.eve-central.com/api/route/from/{}/to/{}'
		jumps = {
			'Jita': 30000142,
			'Amarr': 30002187,
			'Dodixie': 30002659,
			'Rens': 30002510,
		}
		for trade_hub in jumps.keys():
			system_id = jumps[trade_hub]
			response = client.fetch(ec_api.format(ss.id, system_id))
			route = tornado.escape.json_decode(response.body)
			route = map(lambda j: (j['to']['name'], j['to']['security']), route)
			jumps[trade_hub] = list(route)
		client.close()
		system['jumps'] = jumps

	system['mass'] = MASS.STABLE
	system['name'] = system.pop('dest')

	map_data = _get_map()
	found = False
	for node in map_data: # try to add to non-roots first (and check for duplicates)
		if add_node(node):
			found = True
	if not found:
		if root_system:
			map_data.append(system)
		else:
			raise UpdateError('src system not found')
	map_json = _set_map(map_data)

	log_action(username, ACTIONS.ADD_SYSTEM, system)
	return map_json

def delete_system(user_id, system_name):
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
		log_action(user_id, ACTIONS.DELETE_SYSTEM, deleted_node)
	return map_json

def detach_system(user_id, system_name):
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
		log_action(user_id, ACTIONS.DETACH_SYSTEM, detached_node)
	return map_json

def autocomplete(partial):
	prefix = partial.title().encode('utf-8')
	iterator = systems_db.iterator(prefix=prefix, include_value=False)
	return list(map(lambda system: system.decode('utf-8'), iterator))

def __toggle(fn, src, dest, user_id, action):
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
		r = query_one(c, 'SELECT json FROM maps')
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
		log_action(user_id, action, changed_node)
	return map_json

def toggle_eol(user_id, src, dest):
	def toggle_connection(c):
		c['eol'] = not c['eol']

	return __toggle(toggle_connection, src, dest, user_id, ACTIONS.TOGGLE_EOL)

def toggle_reduced(user_id, src, dest):
	def toggle_connection(c):
		if c['mass'] == MASS.REDUCED:
			c['mass'] = MASS.STABLE
		else:
			c['mass'] = MASS.REDUCED

	return __toggle(toggle_connection, src, dest, user_id, ACTIONS.MASS_CHANGE)

def toggle_critical(user_id, src, dest):
	def toggle_connection(c):
		if c['mass'] == MASS.CRITICAL:
			c['mass'] = MASS.STABLE
		else:
			c['mass'] = MASS.CRITICAL

	return __toggle(toggle_connection, src, dest, user_id, ACTIONS.MASS_CHANGE)

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

def log_action(user_id, action, details):
	if action == ACTIONS.ADD_SYSTEM:
		if 'src' not in details:
			log_message = 'added new root system ' + details['name']
		else:
			log_message = 'added system {name} connected to {src}'.format(**details)
	elif action == ACTIONS.DELETE_SYSTEM:
		log_message = 'deleted system ' + details['name']
		if 'connections' in details:
			for system in details['connections']:
				log_action(user_id, ACTIONS.DELETE_SYSTEM, system)
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

	"""
	cursor.execute('''
	INSERT INTO logs (time, user_id, action_id, log_message)
	VALUES(UTC_TIMESTAMP(), ?, ?, ?)
	''', [user_id, action, log_message])
	"""

class User:
	def __init__(self, username, hashed, admin):
		self.username = username
		self.hashed = hashed
		self.admin = admin

	def save(self):
		data = struct.pack('I', self.admin) + self.hashed.encode('ascii')
		users_db.put(self.username.encode('utf-8'), data)

	@staticmethod
	def get(username):
		value = users_db.get(username.encode('utf-8'))
		if value is None:
			return None
		admin = struct.unpack('I', value[:4])[0]
		hashed = value[4:].decode('ascii')
		return User(username, hashed, admin)

class SolarSystem:
	def __init__(self, name, id, region, whclass, effect, static1, static2):
		self.name = name
		self.id = id
		self.region = region
		self.whclass = whclass
		self.effect = effect
		self.static1 = static1
		self.static2 = static2

	def save(self):
		data = struct.pack('I', self.id)
		values = [self.region.encode('utf-8'), self.whclass.encode('ascii')]
		for attr in ['effect', 'static1', 'static2']:
			value = getattr(self, attr)
			if value is None:
				values.append(b'')
			else:
				values.append(value.encode('utf-8'))
		data += b'\0'.join(values)
		systems_db.put(self.name.encode('utf-8'), data)

	@staticmethod
	def get(name):
		value = systems_db.get(name.encode('utf-8'))
		if value is None:
			return None
		id = struct.unpack('I', value[:4])[0]
		region, whclass, effect, static1, static2 = value[4:].split(b'\0')
		return SolarSystem(name, id, region.decode('utf-8'), whclass.decode('ascii'),
				effect.decode('utf-8') or None, static1.decode('utf-8') or None, static2.decode('utf-8') or None)
