#!/usr/bin/python3
import os
import re
import sys

os.chdir('/var/www/nextcloud')
active = False
lines = []
with os.popen('sudo -u www-data -H php updater/updater.phar -vv -n --no-ansi', 'r') as slave, \
		open('/var/log/nextcloud/autoupdate.log', 'a') as log:
	for line in slave:
		log.write(line)
		log.flush()

		if not active:
			lines.append(line)
			if len(lines) > 10 or re.match('^Update to .* available.*', line):
				active = True
				for l in lines:
					sys.stdout.write(l)
				lines = None
		else:
			sys.stdout.write(line)
		sys.stdout.flush()
