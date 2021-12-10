#!/usr/bin/python3
import os
import sys
import shlex
import subprocess
from glob import glob
from datetime import datetime

from collections import defaultdict
from argparse import ArgumentParser
from confparser import ConfigParser
from rsyncparser import RsyncParser

parser = ArgumentParser(description='Rsync backup server with hardlink-based, space-efficient versioning.')
parser.add_argument('-c', '--config', default='pushbackup.conf', help='path to configfile (default: ./pushbackup.conf)')
parser.add_argument('host', help='name of a remote host, as defined in config file')
args = parser.parse_args()

cmd = RsyncParser()
#### options needed for the various modes to behave correctly ####
# omitting --one-file-system might be useful in fringe situations but usually just ends up backing up /proc and/or /sys,
# which causes all sorts of mayhem. it doesn't actually do anything on the server because there are no mounts inside the
# backup directories, but it gets sent to the server if set on the client, and not setting it on the client was almost
# certainly a mistake.
# for restore, it must be allowed for restoring to eg. /var which wasn't a mountpoint during backup but is now. for list
# it's completely irrelevant.
cmd.add([('backup verify', 'require', 'avoids backing up /proc or /sys'), ('restore list', 'allow')],
		'-x --one-file-system')
# checksum mode is pointless when transferring to an empty backup or restore destination, but helps when verifying
cmd.add([('backup restore', 'discourage', 'slows down transfers'), ('list', 'allow'),
		('verify', 'recommend', 'more thorough verification')], '-c --checksum')
# --itemize-changes actually sets --log-format. verify does very little without --itemize-changes, and it can also be
# useful to monitor backup etc. progress.
cmd.add([('verify', 'recommend', 'to see the differences'), ('backup restore list', 'allow')], '-i --itemize-changes',
		'--log-format=', alias='-i --itemize-changes')

#### options that we actually use internally and thus don't want the client to set ####
# these are unsupported for backup because we want to set --list-dest ourselves. they are never even sent to the server
# in restore mode because there the destination is local.
cmd.deny('--compare-dest=', '--copy-dest=', '--link-dest=', hint='backups always use --link-dest')
# backup always runs with --partial-dir, and --max-alloc is configurable server-side. also we always pass either --super
# or --fake-super.
cmd.deny('--partial', '--partial-dir=', hint='this option is always set server-side')
cmd.deny('--fake-super', '--super', '--max-alloc=', hint='this option is configured server-side')

#### optined required for a complete backup / restore ####
# except for -r, these are all meaningless for listing. they are allowed because meaningless implies harmless, and
# having to remove options when listing is annoying
cmd.add([('backup restore verify', 'require'), ('list', 'allow')], '-r', '-l', '-p', '-t', '-g', '-o', '-D',
		alias='-a --archive')
cmd.add([('backup restore verify', 'require', 'local usernames are meaningless on the server'), ('list', 'allow')],
		'--numeric-ids')
# for backup, these are harmless when locally unsupported. allow disabling them for restore because if the local system
# doesn't support them, there is no point in restoring them, and in fact might break the restore
cmd.add([('backup verify', 'require', 'works even if locally unsupported'), ('list', 'allow'),
		('restore', 'recommend', 'if locally supported')], '-H --hard-links', '-A --acls', '-X --xattrs', alias='-HAX')
# --delete* is optional on restore and meaningless on list, but isn't sent to the server in those cases.
# for backup, --delete is required to get a backup without zombie files, and has to be specifically --delete-delay to
# support --fuzzy --inc-recursive without running out of memory.
cmd.deny('--delete', '--delete-after', '--delete-before', '--delete-during', '--delete-excluded',
		hint='use --delete-delay')
cmd.add([('restore list', 'deny', 'how did you even get your rsync to send that option?'),
		('backup verify', 'require', 'avoids zombie files')], '--delete-delay', '--delete-excluded')
# access and creation times technically make for a more complete backup, but are so obscure that nobody ever cares. also
# the options didn't even exist before rsync 3.2. --atimes basically requires --open-noatime, though it doesn't
# automatically imply it.
cmd.allow('-N --crtimes', '-U --atimes', '--open-noatime')

#### forbidden options to keep the user from accidentally making an incomplete backup ####
# --dirs is set when listing non-recursively, and non-recursive listing can be really helpful. in all other cases, it
# skips almost all of the backup.
# the other options are similar in that they unnecessarily exclude stuff from the backup. they can be useful on restore
# if a partial restore is actually desired, but the user needs to know that the restore may be partial.
cmd.add([('backup verify', 'deny', 'backup will be incomplete'), ('restore', 'discourage', 'restore may be incomplete'),
		('list', 'allow')], '-d --dirs', '-m --prune-empty-dirs', '-J --omit-link-times', '-O --omit-dir-times',
		'--ignore-existing', '--max-delete=', '--max-size=', '--min-size=')
# symlinks can be backed up and restored as symlinks. dereferencing them is a really easy way of breaking any UNIX
# system setup so we disable everything that can dereference symlinks.
cmd.deny('-L --copy-links', '-k --copy-dirlinks', '--copy-unsafe-links', '--safe-links', hint='destroys symlinks')
# --cvs-exclude might be useful but it has fairly complex implicit semantics. using manual --exclude's is safer.
cmd.discourage('-C --cvs-exclude', hint='backup / restore might be incomplete')
# --iconv charset-converts filenames. that used to be necessary before universal UTF-8 filenames, but these days is more
# likely to corrupt them instead.
cmd.deny('--iconv=', hint='will likely mangle your filenames')

#### options that aren't supported or that make no sense for a backup ####
cmd.deny('--ignore-errors', hint='when has that ever been a good idea?')
cmd.deny('-W --whole-file', hint='slows down transfers')
# --protect-args would be very useful but would also require parsing the stream, and that isn't going to happen.
# -@ and -B take options and we don't want to parse them. fortunately they aren't very useful anyway, especially in the
# the backup setting here.
cmd.deny('-s --protect-args', '-@ --modify-window=', '-B --block-size=', hint='not supported by backup system')
# these options either make absolutely no sense in a backup (--backup --suffix etc) or are pointless (--append) or make
# sense only for restore but then aren't sent to the server (--existing).
cmd.deny('-R --relative', '-b --backup', '-u --update', '--append', '--backup-dir', '--delay-updates', '--existing',
		'--inplace', '--remove-source-files', '--groupmap=', '--usermap=', '--mkpath', '--preallocate', '--suffix=',
		'--size-only', 
		hint='does not make sense for backup storage')
# seriously dangerous options. most of them can be used for at least arbitrary file read, some even arbitrary file write
cmd.deny('-K --keep-dirlinks', '--daemon', '--files-from=', '--write-devices', '--log-file=', '--only-write-batch=',
		'--temp-dir=', hint='please do not hack the server')
# options that the rsync client should never set
cmd.deny('-E --executability', '-I --ignore-times', '--force', '--from0', '--no-implied-dirs',
		hint='rsync should never have sent that option for a proper invocation')
# if source arguments are missing, the user should get a warning about that
cmd.deny('--delete-missing-args', '--ignore-missing-args', hint='fix your commandline instead')
cmd.discourage('--timeout=', hint='use the SSH timeout instead')

#### configuration options that we simply don't care about ####
# these make no functional difference but can be very useful for optimizing performance or bandwidth
cmd.allow('-z --compress', '-y --fuzzy', '-S --sparse', '--bwlimit', '--checksum-choice=', '--checksum-seed=',
		'--compress-choice=', '--compress-level=', '--old-compress', '--new-compress', '--skip-compress=',
		hint='client-controlled trade-off')
# allow debug output (doen#t hurt) and mixing errors with messages (only hurts the user)
cmd.allow('--stats', '--debug=', '--info=', '--no-msgs2stderr', '--msgs2stderr', hint='informational outputs')

if 'SSH_ORIGINAL_COMMAND' not in os.environ:
	sys.stderr.write('SSH_ORIGINAL_COMMAND not set, is SSH configured correctly?\n')
	sys.exit(1)
cmd.parse(os.environ['SSH_ORIGINAL_COMMAND'])
for msg in cmd.get_messages():
	sys.stderr.write('%s\n' % msg)
path = cmd.get_path()
if path is None:
	sys.exit(1)

while path.startswith('/'):
	path = path[1:]
if '/' in path:
	pos = path.index('/')
	space = path[0:pos]
	path = path[pos+1:] if pos < len(path) else None
elif path == '.':
	space = 'default'
	path = None
else:
	space = path
	path = None

if '@' in space:
	pos = space.index('@')
	time = space[pos+1:]
	space = space[0:pos]
else:
	time = None
