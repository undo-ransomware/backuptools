#!/usr/bin/python3
import os
import io
import sys
import yaml
import urllib
import requests
from fnmatch import fnmatch
from argparse import ArgumentParser
from ncconfig import load_nc_accounts, load_nc_excludes

REMOTE = '/remote.php/webdav'
CHUNK_SIZE = 1024*1024

nc_config = load_nc_accounts()
nc_excludes = load_nc_excludes()

parser = ArgumentParser(description='Utility to check whether all files ' +
		'synced to Nextcloud can actually be retrieved from there, and ' +
		'identically so. Necessary because Nextcloud sometimes fails to ' +
		'properly write a file to disk.')
parser.add_argument('account', nargs='?', help='index of account in ' +
		'nextcloud.cfg (run without arguments to list all accounts)')
parser.add_argument('folder', nargs='*',
	help='indexes of folders to check for this account (default is all)')
parser.add_argument('-v', '--verbose', action='store_true',
	help='list all files as they are being checked, not just errors')
args = parser.parse_args()
if args.account is not None and args.account not in nc_config:
	sys.stderr.write('%s: no such account!\n' % args.account)
	args.account=None
if args.account is None:
	sys.stderr.write('accounts defined in config:\n')
	for index, account in nc_config.items():
		sys.stderr.write('%s: %s\n' % (index, account))
		for jndex, folder in account.folders.items():
			sys.stderr.write('\t%s: %s\n' % (jndex, folder))
	sys.exit(0)
if args.folder == []:
	args.folder = nc_config[args.account].folders.keys()

def is_excluded(file, ignore_hidden):
	if ignore_hidden and file.startswith('.'):
		return True
	return any(fnmatch(file, x) for x in nc_excludes)

def scan_files(basedir, qpath, ignore_hidden, path=''):
	for file in os.listdir(os.path.join(basedir, path)):
		urlpath = '%s/%s' % (qpath, urllib.parse.quote(file))
		relpath = os.path.join(path, file)
		abspath = os.path.join(basedir, relpath)
		if is_excluded(file, ignore_hidden):
			yield relpath, urlpath, 'excluded'
		elif os.path.isdir(abspath):
			for tup in scan_files(basedir, urlpath, ignore_hidden, relpath):
				yield tup
		elif os.path.isfile(abspath):
			yield relpath, urlpath, None
		else:
			yield relpath, urlpath, 'special'

class WebDav:
	def __init__(self, baseurl, user, password):
		self.base = baseurl + REMOTE
		self.session = requests.Session()
		self.session.auth = (user, password)
		self.session.stream = True
		self.session.verify = True
	
	def get(self, path):
		return self.session.get(self.base + path)
	
	def close(self):
		self.session.close()

def compare(webdav, local_path, remote_path):
	off = 0
	with io.open(local_path, 'rb') as file, webdav.get(remote_path) as res:
		if res.status_code != 200:
			return 'status %d' % res.status_code
		for chunk in res.iter_content(CHUNK_SIZE):
			ref = file.read(len(chunk))
			if len(ref) < len(chunk):
				return 'local eof at %d' % (off + len(ref))
			elif len(ref) > len(chunk):
				return 'remote eof at %d' % (off + len(chunk))
			elif ref != chunk:
				for i in range(len(chunk)):
					if ref[i] != chunk[i]:
						return 'difference at offset %d' % (off + i)
				assert False
			off += len(chunk)
		if len(file.read(1)) > 0:
			return 'remote eof at %d' % off

acct = nc_config[args.account]
with io.open('passwords.yaml', 'r') as file:
	passwords = yaml.load(file)
webdav = WebDav(acct.url, acct.user, passwords[acct.url][acct.user])
for folder in [acct.folders[k] for k in args.folder]:
	if args.verbose:
		sys.stderr.write('checking %s\n' % folder)
	for path, url, type in scan_files(folder.localpath,
			folder.targetpath, folder.ignore_hidden):
		local = os.path.join(folder.localpath, path)
		if type is not None:
			if args.verbose:
				sys.stdout.write('%s: %s\n' % (local, type))
			continue
		error = compare(webdav, local, url)
		if error is not None:
			sys.stdout.write('%s: %s\n' % (local, error))
		elif args.verbose:
			sys.stdout.write('%s: ok\n' % local)
		sys.stdout.flush()
