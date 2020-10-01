#!/usr/bin/python3
import os
import io
import configparser

NCCFG = os.path.expanduser('~/.config/Nextcloud')

def subkeys(config, prefix):
	indices = set(k[len(prefix):].split('\\')[0]
			for k in config.keys()
			if k.startswith(prefix) and '\\' in k[len(prefix):])
	keys = dict()
	for i in sorted(indices):
		pfx = '%s%s\\' % (prefix, i)
		keys[i] = { key[len(pfx):]: value
				for key, value in config.items()
				if key.startswith(pfx) }
	return keys.items()

class Folder:
	def __init__(self, keys):
		self.localpath = keys['localpath']
		self.targetpath = keys['targetpath'][1:] # relative
		self.ignore_hidden = keys['ignorehiddenfiles'] == 'true'
	
	def __repr__(self):
		return '%s → %s' % (self.localpath, self.targetpath)

class Account:
	def __init__(self, keys):
		assert keys['version'] == '1'
		self.url = keys['url']
		auth = keys['authtype']
		self.user = keys['%s_user' % auth]
		self.folders = { i: Folder(k) for i, k in subkeys(keys, 'folders\\') }
	
	def __repr__(self):
		return '%s as %s' % (self.url, self.user)

def load_nc_accounts():
	config = configparser.ConfigParser()
	config.read(os.path.join(NCCFG, 'nextcloud.cfg'))
	assert config['Accounts']['version'] == '2'
	return { i: Account(k) for i, k in subkeys(config['Accounts'], '') }

def load_nc_excludes():
	# TODO excludes can have escapes, so we should replace them
	with io.open(os.path.join(NCCFG, 'sync-exclude.lst'), 'r') as excludes:
		return [ (line[1:] if line.startswith(']') else line).rstrip()
				for line in excludes
				if not line.startswith('#') and len(line.rstrip()) ]
