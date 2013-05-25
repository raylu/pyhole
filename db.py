import binascii
import hashlib
import hmac
import oursql
import os

conn = oursql.connect(db='pyhole', user='pyhole', passwd='pyhole', autoreconnect=True)

def query(sql, *args):
	with conn.cursor() as c:
		c.execute(sql, args)
		while True:
			r = c.fetchone()
			if r is None:
				break
			attribs = DBRow()
			for i, f in enumerate(c.description):
				setattr(attribs, f[0], r[i])
			yield attribs

def query_one(sql, *args):
	results = query(sql, *args)
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

def execute(sql, *args):
	with conn.cursor() as c:
		c.execute(sql, args)
		return c.lastrowid

def create_user(username, password):
	salt = os.urandom(16)
	h = hmac.new(salt, password.encode('utf-8'), hashlib.sha256)
	hashed = h.hexdigest()
	salt_hex = binascii.hexlify(salt)
	execute('INSERT INTO users (username, password, salt) VALUES(?, ?, ?)',
	        username, hashed, salt_hex)

def check_login(username, password):
	r = query_one('SELECT id, password, salt FROM users WHERE username = ?', username)
	if r is None:
		return
	salt = binascii.unhexlify(bytes(r.salt, 'ascii'))
	h = hmac.new(salt, password.encode('utf-8'), hashlib.sha256)
	if h.hexdigest() == r.password:
		return r.id

class DBRow:
	def __str__(self):
		return '<DBRow>: ' + str(self.__dict__)
