#!/usr/bin/python3
import io
import requests
from time import mktime
from urllib.parse import urljoin, unquote
from email.utils import parsedate
from xml.etree import ElementTree as ET

REMOTE = '/remote.php/webdav/'
CHUNK_SIZE = 1024*1024

# technically <resourcetype/><getlastmodified/><getcontenttype/> but
# nextcloud returns allprop anyway.
PROPFIND = '<?xml version="1.0"?><propfind xmlns="DAV:"><allprop/></propfind>'

class Resource:
	def __init__(self, base, node):
		self.href = urljoin(base, node.find('{DAV:}href').text)
		if not self.href.startswith(base):
			raise Exception('child %s not within parent %s'
					% (self.href, base))
		name = unquote(self.href[len(base):])
		if name.endswith('/'):
			name = name[:-1]
		if '/' in name:
			raise Exception('child %s not direct descendent of parent %s'
					% (self.href, base))

		ok = next(ps.find('{DAV:}prop')
				for ps in node.findall('{DAV:}propstat')
				if ps.find('{DAV:}status').text.endswith(' 200 OK'))
		self.isdir = len(ok.findall('{DAV:}resourcetype/{DAV:}collection')) > 0
		self.mtime = mktime(parsedate(ok.findall(
				'{DAV:}getlastmodified')[0].text))
		self.size = int(ok.findall('{DAV:}getcontentlength')[0].text) \
			if not self.isdir else 0
		self.name = name if name != '' else '.'

class WebDav:
	def __init__(self, baseurl, user, password):
		self.base = baseurl + REMOTE
		self.session = requests.Session()
		self.session.auth = (user, password)
		self.session.stream = True
		self.session.verify = True

	def get(self, path):
		return self.session.get(urljoin(self.base, path))

	def download(self, url, local_path):
		off = 0
		with io.open(local_path, 'wb') as file, self.get(url) as res:
			if res.status_code != 200:
				raise Exception('unexpected status %d' % res.status_code)
			for chunk in res.iter_content(CHUNK_SIZE):
				file.write(chunk)

	def list(self, path):
		if not path.endswith('/') and path != '':
			path += '/'
		req = requests.Request('PROPFIND', urljoin(self.base, path),
				data=PROPFIND, headers={'Depth': '1'})
		res = self.session.send(self.session.prepare_request(req))
		if res.status_code != 207:
			print(res.url)
			raise Exception('unexpected status %d' % res.status_code)
		return [Resource(res.url, node)
				for node in ET.fromstring(res.text).findall('{DAV:}response')]

	def close(self):
		self.session.close()
