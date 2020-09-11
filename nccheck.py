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

parser = ArgumentParser(description='Utility to check whether all files ' +
		'synced to Nextcloud can actually be retrieved from there, and ' +
		'identically so. Useful to check against bit rot or Nextcloud ' +
		'failing to properly write a file to disk.')
parser.add_argument('folder', nargs='*', help='paths to compare against ' +
		'Nextcloud (as defined in the sync client\'s config file)')
parser.add_argument('-p', '--passwords-from', default='passwords.yaml', 
		help='load app passwords from this file (default: passwords.yaml)',
		metavar='YAML')
parser.add_argument('-a', '--list-accounts', action='store_true',
		help='list all accounts and paths defined in the sync client\'s ' +
		'config file. default when no paths given.')
parser.add_argument('-v', '--verbose', action='store_true',
		help='list all files as they are being checked, not just errors')
args = parser.parse_args()

nc_config = load_nc_accounts()
nc_excludes = load_nc_excludes()
if args.list_accounts or args.folder == []:
	sys.stderr.write('accounts defined in nextcloud.cfg:\n')
	for index, account in nc_config.items():
		sys.stderr.write('%s: %s\n' % (index, account))
		for jndex, folder in account.folders.items():
			sys.stderr.write('\t%s: %s\n' % (jndex, folder))
	sys.exit(0)

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
		elif os.path.islink(abspath):
			yield relpath, urlpath, 'symlink'
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

def find_remote_base(path):
	for acct in nc_config.values():
		for folder in acct.folders.values():
			if path.startswith(folder.localpath):
				return '%s/%s' % (folder.targetpath, urllib.parse.quote(
						os.path.relpath(path, folder.localpath))), acct, \
						folder.ignore_hidden
	return None, None, None

with io.open(args.passwords_from, 'r') as file:
	passwords = yaml.load(file)
for localbase in args.folder:
	remotebase, acct, ignore_hidden = find_remote_base(localbase)
	if remotebase is None:
		sys.stdout.write('%s: not synced\n' % localbase)
		continue

	webdav = WebDav(acct.url, acct.user, passwords[acct.url][acct.user])
	for path, url, type in scan_files(localbase, remotebase, ignore_hidden):
		local = os.path.join(localbase, path)
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
