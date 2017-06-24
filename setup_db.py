#!/usr/bin/env python3

import csv
from getpass import getpass
from os import path
import sqlite3
import sys

import db

def main(sqlite_path):
	if path.exists(db.db_path):
		print(db.db_path, 'already exists')
		return 1

	db.init_db(True)

	csv.register_dialect('wormholes',
			lineterminator='\n', quoting=csv.QUOTE_MINIMAL, skipinitialspace=True, strict=True)
	wormholes = get_wormholes('setup_data/wormholes.csv')

	conn = sqlite3.connect(sqlite_path)
	conn.row_factory = sqlite3.Row
	rows = conn.execute('''
		SELECT solarSystemID, solarSystemName, security, regionName, wormholeClassId FROM mapSolarSystems
		JOIN mapRegions ON mapRegions.regionID = mapSolarSystems.regionID
		JOIN mapLocationWormholeClasses ON mapRegions.regionId = mapLocationWormholeClasses.locationId
	''')
	for row in rows:
		id = int(row['solarSystemID'])
		name = row['solarSystemName']
		security = row['security']
		region = row['regionName']
		wormhole = wormholes.get(id)
		if wormhole:
			assert name == wormhole['name']
			whclass = wormhole['class']
			effect = wormhole['effect']
			static1 = wormhole['static1']
			static2 = wormhole['static2']
		else:
			if security >= 0.45:
				whclass = 'highsec'
			elif security > 0.0:
				whclass = 'lowsec'
			else:
				whclass = 'nullsec'
			effect = static1 = static2 = None
		db.SolarSystem(name, id, region, whclass, effect, static1, static2).save()

	for wh_type in get_wh_types('setup_data/wh_types.csv'):
		"""
		id = wh_type['id']
		name = wh_type['name']
		src = wh_type['src']
		dest = wh_type['dest']
		lifetime = wh_type['lifetime']
		jump_mass = wh_type['jump_mass']
		max_mass = wh_type['max_mass']
		"""
		db.WHType(**wh_type).save()

	username = input('username: ')
	password = getpass('password: ')
	db.create_user(None, username, password, True)

	db.db.put(b'map', b'[]')
	return 0

def get_wormholes(csv_path):
	wormholes = {}
	with open(csv_path, 'r') as f:
		reader = csv.DictReader(f, dialect='wormholes')
		for row in reader:
			if row['effect'] == 'NULL':
				row['effect'] = None
			for field in ['static1', 'static2']:
				if row[field] == 'NULL':
					row[field] = None
				else:
					row[field] = int(row[field])
			wormholes[int(row['id'])] = {
				'name': row['name'],
				'class': row['class'],
				'effect': row['effect'],
				'static1': row['static1'],
				'static2': row['static2'],
			}
	return wormholes

def get_wh_types(csv_path):
	with open(csv_path, 'r') as f:
		reader = csv.DictReader(f, dialect='wormholes')
		for row in reader:
			for key in ['id', 'lifetime', 'jump_mass', 'max_mass']:
				row[key] = int(row[key])
			yield row

if __name__ == '__main__':
	sys.exit(main(*sys.argv[1:])) # pylint: disable=no-value-for-parameter
