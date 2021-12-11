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
cmd.deny('--partial', '--partial-dir=', '--delete-excluded', hint='this option is always set server-side')
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
cmd.deny('--delete', '--delete-after', '--delete-before', '--delete-during', hint='use --delete-delay')
cmd.add([('restore list', 'deny', 'how did you even get your rsync to send that option?'),
		('backup verify', 'require', 'avoids zombie files')], '--delete-delay')
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

# parse command and bail out if inacceptable
if 'SSH_ORIGINAL_COMMAND' not in os.environ:
	sys.stderr.write('SSH_ORIGINAL_COMMAND not set, is SSH configured correctly?\n')
	sys.exit(1)
cmd.parse(os.environ['SSH_ORIGINAL_COMMAND'])
for msg in cmd.get_messages():
	sys.stderr.write('%s\n' % msg)
path = cmd.get_path()
if path is None:
	sys.exit(1)
mode = cmd.get_mode()

# parse backup space, subdirectory and time specification. this whole thing is formatted as space@time/path/ and all
# components of that are optional.
# trailing slashes for the source argument are significant for rsync. (for destination, it doesn't make a difference.)
# - for backup and verify, it's important to give things with a trailing slash: /var/ sends all the files inside /var,
#   while /var sends the directory itself. but the source isn't sent to the server so we have no way of checking that.
# - for restore, we need to allow no trailing spaces to restore single files. but we must guarantee a slash after the
#   @time directory so the client doesn't annoyingly get that. and we can warn if a directory is fetched without the
#   trailing slash.
# - for listing, @ behaves special where the path isn't actually passed to rsync, we need to ensure a slash after the source directory.
# all of that boils down to ensuring that the path always starts with a slash, handling that correctly for listing, and
# issuing the warning if restoring a directory without the trailing slash
if '/' in path:
	pos = path.index('/')
	space = path[0:pos]
	path = path[pos:] if pos < len(path) else '/'
else:
	space = path
	path = '/'
if '@' in space:
	pos = space.index('@')
	time = space[pos:]
	space = space[:pos]
else:
	time = None
if time == '@latest':
	time = None
if space == '.' or space == '':
	space = 'default'
if mode == 'backup' and (time is not None or path != '/'):
	sys.stderr.write('ERROR cannot specify a path or time for backup mode\n')
	sys.exit(1)

# read config and apply the usual business logic of weird defaults
config = ConfigParser(args.host, space)
config.add_str('target')
config.add_int('keep-count')
config.add_timedelta('keep-duration')
config.add_timedelta('backup-cooldown')
with open(args.config, 'r') as fd:
	config.parse(fd)
if config['target'] is None:
	sys.stderr.write('ERROR no backup directory specified for host %s and backup space %s\n' % (args.host, space))
	sys.exit(1)
if config['keep-count'] is None and config['keep-duration'] is None:
	config['keep-count'] = 1000000 # keep "infinity" backups = never delete any backups
elif config['keep-count'] is None:
	config['keep-count'] = 1 # controlled by keep-duration only
elif config['keep-duration'] is None:
	config['keep-duration'] = timedelta(seconds=0) # controlled by keep-count only
if config['keep-count'] <= 0:
	sys.stderr.write('WARNING adjusting keep-count=%d to keep-count=1\n' % config['keep-count'])
	config['keep-count'] = 1
now = datetime.now()
def format_date(date):
	return date.strftime('@%Y-%m-%d_%H-%M-%S')
min_date = format_date(now - config['keep-duration'])

# instead of configuring every single host + space combination, we do allow simply creating the corresponding backup
# directory instead. the config has defaults and can easily configure backup directories for all hosts at once. the host
# is actually trustworthy because it has to be configured in authorized_keys anyway. but we don't allow any random space
# name here.
# this boils down to just using whatever exists, and creating it if it doesn't exist but is configured.
target = config['target'].replace('{HOST}', args.host).replace('{SPACE}', space)
if not os.path.isdir(target):
	if (args.host, space) not in config.sections():
		sys.stderr.write('ERROR backup space %s neither configured nor present for host %s\n' % (space, args.host))
		sys.exit(1)
	os.makedirs(target, exist_ok=True)
target = os.path.abspath(target)

# before backing up (and only then), remove obsolete backups. note that keep-count ≥ 1 because we clamped it above
existing = sorted(glob(os.path.join(target, '@20??-??-??_??-??-??')))
if mode == 'backup':
	while len(existing) > config['keep-count'] and os.path.basename(existing[0]) <= min_date:
		if cmd.is_verbose():
			sys.stderr.write('INFO removing obsolete backup %s\n' % os.path.basename(existing[0]))
		subprocess.check_call(['rm', '-rf', existing[0]])
		del existing[0]
latest = existing[-1] if existing != [] else None
# note that every string starts with an empty string, so "space@" selects everything for listing ;)
# for verify or restore it selects the oldest backup, which is much less useful but acceptable
if time is not None:
	selected = [dir for dir in existing if os.path.basename(dir).startswith(time)]

# assemble the actual rsync command
rsync = cmd.get_command()
if mode == 'backup':
	# backup to temp subdirectory first. that gets moved into place once the backup has finished successfully.
	# TODO should probably use some sort of lockfile to prevent concurrent backups!
	current = os.path.join(target, format_date(now))
	tempdir = os.path.join(target, 'temp')
	os.makedirs(tempdir, exist_ok=True)
	if latest is not None:
		rsync += ['--link-dest=%s' % latest]
	rsync += ['--partial-dir=.rsync-partial', '--delete-excluded', '.', tempdir]
elif mode == 'list':
	if time is not None:
		if len(selected) == 0:
			sys.stderr.write('WARNING no backups matching %s for backup space %s on host %s\n' % (time, space,
					args.host))
		elif path != '/':
			# with both time specification and path, simply list that path in that backup. that obviously only works if
			# precisely one backup is selected.
			if len(selected) > 1:
				sys.stderr.write('ERROR time must be unique when combined with a path in list mode\n')
				sys.exit(1)
			else:
				selected = [selected[0] + path]
		# else, with time specification but no path, list the selected backups including their time directories.
		# this relies on two things:
		# - the directories don't end with a slash so rsync actually sends their name
		# - the remote rsync doesn't actually notice we're turning 1 argument into several arguments
	else:
		# no time specification, so we simply list the latest backup
		selected = [latest + path]

	rsync += ['.'] + selected
else:
	if time is not None:
		if len(selected) == 0:
			sys.stderr.write('ERROR no backups matching %s for backup space %s on host %s\n' % (time, space,
					args.host))
			sys.exit(1)
		if (len(selected) > 1 and not cmd.is_quiet()) or cmd.is_verbose():
			sys.stderr.write('INFO selecting backup %s\n' % os.path.basename(min(selected)))
		base = min(selected)
	elif latest is None:
		sys.stderr.write('ERROR no backups found for backup space %s on host %s\n' % (space, args.host))
		sys.exit(1)
	else:
		base = latest
	base += path
	
	if mode == 'restore' and os.path.isdir(base) and not base.endswith('/') and not cmd.is_quiet():
		sys.stderr.write('WARNING restoring directory %s without trailing slash, restored paths will start with %s/\n' \
				% (path, os.path.basename(base)))
	rsync += ['.', base]

if cmd.is_verbose():
	sys.stderr.write('INFO invoking %s\n' % ' '.join(rsync))
sys.stderr.flush()
retcode = subprocess.call(rsync)
# exit code 24 is vanished files, which are somewhat expected on an active system
if retcode not in [0, 24]:
	sys.exit(retcode)
if mode == 'backup':
	os.rename(tempdir, current)
