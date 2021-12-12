#!/usr/bin/python3
import os
import io
import sys
import yaml
import urllib
from shutil import rmtree
from minidav import WebDav
from email.utils import parsedate
from argparse import ArgumentParser
from xml.etree import ElementTree as ET
from ncconfig import load_nc_accounts

parser = ArgumentParser(description='Utility to download a directory tree ' +
		'from Nextcloud. Essentially a download-only, non-interactive, ' +
		'non-GUI version of the sync client, without the background sync ' +
		'part. Very useful to pull data from Nextcloud for backup purposes, ' +
		'without needing direct access to the underlying storage. Also ' +
		'downloads data from local and federated shares, which isn\'t ' +
		'present in the user\'s data directory on the server.')
parser.add_argument('server', help='base URL of nextcloud server')
parser.add_argument('remote_path', help='remote source directory (note ' +
		'that it needs to be a directory. downloading files doesn\'t work.)')
parser.add_argument('local_path', help='local destination path')
parser.add_argument('-u', '--user',
		help='remote username (default: from sync client config)')
parser.add_argument('-p', '--passwords-from', default='passwords.yaml',
		help='load app passwords from this file (default: passwords.yaml)',
		metavar='YAML')
parser.add_argument('-d', '--delete', action='store_true',
		help='delete local files not found on the server (default: keep ' +
		'those files, demonstrating that Remote Wipe cannot be relied upon)')
parser.add_argument('-f', '--force', action='store_true',
		help='re-download every file, even if modification time and size ' +
		'indicate that the local version is up to date. this effectively ' +
		'treats every file as changed')
parser.add_argument('-l', '--list-changes', action='store_true',
		help='list changes to files and directories')
parser.add_argument('-v', '--verbose', action='store_true',
		help='list all files and directories, even unchanged ones')
args = parser.parse_args()

with io.open(args.passwords_from, 'r') as file:
	passwords = yaml.safe_load(file)
if args.user is None:
	args.user = next((acct.user
			for acct in load_nc_accounts().values()
			if args.server == acct.url), None)
	if args.user is None:
		raise Exception('no matching account in sync client config')
password = passwords[args.server][args.user]
if not args.remote_path.endswith('/'):
	args.remote_path += '/'
if args.remote_path.startswith('/'):
	args.remote_path = args.remote_path[1:]

def nuke(path):
	if os.path.isdir(path):
		rmtree(path)
	else:
		os.unlink(path)

dav = WebDav(args.server, args.user, password)
def download(remote_base, local_base):
	changed = False
	if not os.path.isdir(local_base):
		os.mkdir(local_base)

	remote = set()
	for file in dav.list(remote_base):
		if file.name == '.':
			continue
		local_path = os.path.join(local_base, file.name)
		remote.add(file.name)

		if not file.isdir:
			modified = False
			if os.path.exists(local_path) and not os.path.isfile(local_path):
				if not args.delete:
					raise Exception('not a file: %s' % local_path)
				nuke(local_path)
				modified = True
				op = 'replaced'
			elif os.path.isfile(local_path):
				mtime = os.path.getmtime(local_path)
				size = os.path.getsize(local_path)
				modified = mtime < file.mtime or size != file.size or args.force
				op = 'changed'
			else:
				modified = True
				op = 'created'
			if modified:
				dav.download(file.href, local_path)
				os.utime(local_path, (file.mtime, file.mtime))
		else:
			if os.path.exists(local_path) and not os.path.isdir(local_path):
				if not args.delete:
					raise Exception('not a directory: %s' % local_path)
				os.unlink(local_path)
				op = 'replaced'
			elif os.path.isdir(local_path):
				op = 'changed'
			else:
				op = 'created'
			modified = download(file.href, local_path)

		if (args.list_changes and modified) or args.verbose:
			sys.stdout.write('%s: %s\n' %
					(local_path, op if modified else 'unchanged'))
			sys.stdout.flush()
		changed |= modified

	if args.delete:
		for file in os.listdir(local_base):
			if file not in remote:
				local_path = os.path.join(local_base, file)
				nuke(local_path)
				if args.list_changes or args.verbose:
					sys.stdout.write('%s: deleted\n' % local_path)
					sys.stdout.flush()
				changed = True
	return changed

mod = download(args.remote_path, args.local_path)
if (args.list_changes and mod) or args.verbose:
	sys.stdout.write('%s: %schanged\n' % (args.local_path, '' if mod else 'un'))
	sys.stdout.flush()
