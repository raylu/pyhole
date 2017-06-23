#!/usr/bin/env python3

import plyvel

db = plyvel.DB('./database', create_if_missing=False)
it = db.iterator()
for k, v in it:
	print(k, v)
