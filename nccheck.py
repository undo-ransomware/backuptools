#!/usr/bin/python3
import os
import io
import sys
import yaml
from minidav import WebDav, CHUNK_SIZE
from fnmatch import fnmatch
from urllib.parse import quote
from argparse import ArgumentParser
from ncconfig import load_nc_accounts, load_nc_excludes

parser = ArgumentParser(description='Utility to check whether all files ' +
		'synced to Nextcloud can actually be retrieved from there, and ' +
		'identically so. Useful to check against bit rot or Nextcloud ' +
		'failing to properly write a file to disk.')
parser.add_argument('folder', nargs='*', help='paths to compare against ' +
		'Nextcloud (as defined in the sync client\'s config file)')
parser.add_argument('-l', '--log', metavar='FILE',
		help='append list of correctly retrieved files to the given file. ' +
		'if that file exists, also skips checking the files already ' +
		'listed in it (ie. allows resuming a check where it left off).')
parser.add_argument('-p', '--passwords-from', default='passwords.yaml',
		help='load app passwords from this file (default: passwords.yaml)',
		metavar='YAML')
parser.add_argument('-a', '--list-accounts', action='store_true',
		help='list all accounts and paths defined in the sync client\'s ' +
		'config file. default when no paths given.')
parser.add_argument('-e', '--excluded', action='store_true',
		help='list excluded files instead of silently skipping them')
parser.add_argument('-v', '--verbose', action='store_true',
		help='also list files that were correctly retrieved or excluded')
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
		return 'hidden'
	if any(fnmatch(file, x) for x in nc_excludes):
		return 'excluded'

def scan_files(basedir, qpath, ignore_hidden, path=''):
	for file in os.listdir(os.path.join(basedir, path)):
		urlpath = '%s/%s' % (qpath, quote(file))
		relpath = os.path.join(path, file)
		abspath = os.path.join(basedir, relpath)
		skip = is_excluded(file, ignore_hidden)
		if skip is not None:
			yield relpath, urlpath, skip
		elif os.path.islink(abspath):
			yield relpath, urlpath, 'symlink'
		elif os.path.isdir(abspath):
			for tup in scan_files(basedir, urlpath, ignore_hidden, relpath):
				yield tup
		elif os.path.isfile(abspath):
			yield relpath, urlpath, None
		else:
			yield relpath, urlpath, 'special'

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
				return '%s/%s' % (folder.targetpath, quote(os.path.relpath(
						path, folder.localpath))), acct, folder.ignore_hidden
	return None, None, None

known_good = set()
if args.log is not None:
	if os.path.isfile(args.log):
		with io.open(args.log, 'r') as log:
			known_good = set(file[:-1] for file in log)
	log = io.open(args.log, 'a')
else:
	log = None
with io.open(args.passwords_from, 'r') as file:
	passwords = yaml.load(file)
for localbase in args.folder:
	remotebase, acct, ignore_hidden = find_remote_base(localbase)
	if remotebase is None:
		sys.stdout.write('%s: not synced\n' % localbase)
		continue

	webdav = WebDav(acct.url, acct.user, passwords[acct.url][acct.user])
	for path, url, skip in scan_files(localbase, remotebase, ignore_hidden):
		local = os.path.join(localbase, path)
		if local in known_good:
			continue
		if skip is not None:
			if args.verbose or args.excluded:
				sys.stdout.write('%s: %s\n' % (local, skip))
			continue
		error = compare(webdav, local, url)
		if error is None:
			if args.verbose:
				sys.stdout.write('%s: ok\n' % local)
			if log is not None:
				log.write('%s\n' % local)
				log.flush()
		else:
			sys.stdout.write('%s: %s\n' % (local, error))
		sys.stdout.flush()
if log is not None:
	log.close()
