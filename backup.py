#!/usr/bin/python3
import os
import sys
import shlex
import subprocess
from glob import glob
from datetime import datetime
from argparse import ArgumentParser

parser = ArgumentParser(description='Simple rsync-based incremental backup ' +
		'utility, using hardlinks to save disk space.')
parser.add_argument('source',
	help='local source path or hostname.domain:/path for remote host')
parser.add_argument('backupdir',
	help='local path containing the date-named backup subdirectories')
parser.add_argument('-i', '--key',
	help='path to SSH key (default: hostname.key, without domain)')
parser.add_argument('-k', '--keep', metavar='DAYS', type=int, default=0,
	help='number of backups to keep (default: infinite)')
parser.add_argument('-c', '--check-only', '--validate', action='store_true',
	help='validate latest backup against filesystem using checksums ' +
			'instead of creating a new backup')
parser.add_argument('-e', '--exclude', action='append', default=[],
	help='exclude a pattern -- see INCLUDE/EXCLUDE PATTERN RULES in man ' +
			'rsync for the full syntax, but mostly either -e /var/tmp/ ' +
			'(leading & trailing slash) to exclude a subtree or ' +
			'-e /var/tmp/** to exclude its contents only. note that ' +
			'files inside mountpoints are always excluded anyways!')
parser.add_argument('-T', '--exclude-temp', action='store_true',
	help='exclude contents of /tmp, /var/tmp and /var/cache')
args = parser.parse_args()
if ':' in args.source and args.key is None:
	hostname = args.source.split(':')[0]
	if '.' in hostname:
		hostname = hostname.split('.')[0]
	args.key = '%s.key' % hostname
args.backupdir = os.path.abspath(args.backupdir)
if args.exclude_temp:
	args.exclude += ['/tmp/**', '/var/tmp/**', '/var/cache/**']

existing = sorted(glob(os.path.join(args.backupdir, '20??-??-??_??:??:??')))
if args.keep > 0 and not args.check_only and len(existing) > args.keep:
	subprocess.check_call(['rm', '-rf'] + existing[:-args.keep])
latest = existing[-1] if existing != [] else None
now = datetime.now()
current = os.path.join(args.backupdir, now.isoformat('_', timespec='seconds'))

rsync = ['rsync', '--archive', '--acls', '--xattrs', '--numeric-ids',
		'--one-file-system', '--8-bit-output']
if args.key is not None:
	rsync += ['--rsh=ssh -i %s' % shlex.quote(args.key)]
for exclude in args.exclude:
	rsync += ['--exclude=%s' % exclude]
if not args.check_only:
	tempdir = os.path.join(args.backupdir, 'temp')
	if not os.path.isdir(tempdir):
		os.mkdir(tempdir)

	if latest is not None:
		rsync += ['--link-dest=%s' % latest, '--delete-after',
				'--delete-excluded']
	rsync += ['--partial-dir=.partial', '--quiet', args.source, tempdir]
else:
	rsync += ['--checksum', '--itemize-changes', '--dry-run', args.source,
			latest]

retcode = subprocess.call(rsync)
# exit code 24 is vanished files, which are somewhat expected on an active system
if retcode not in [0, 24]:
	sys.exit(retcode)
if not args.check_only:
	os.rename(tempdir, current)
