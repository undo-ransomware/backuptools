#!/usr/bin/python3
import requests
from urllib.parse import urljoin

REMOTE = '/remote.php/webdav/'
CHUNK_SIZE = 1024*1024

class WebDav:
	def __init__(self, baseurl, user, password):
		self.base = baseurl + REMOTE
		self.session = requests.Session()
		self.session.auth = (user, password)
		self.session.stream = True
		self.session.verify = True
	
	def get(self, path):
		return self.session.get(urljoin(self.base, path))

	def close(self):
		self.session.close()
