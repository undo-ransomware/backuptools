# format of options passed to remote `rsync`

call is like `rsync --server --sender -re.iLsfxC --list-only . debian`. for
this, `--server` has to be first and `--sender` is used when receivung from
remote (ie. restore). the rest of the command line is mostly normal except
for the "magic" options after `-e` (a hack to have arguments that aren't
parsed as actual arguments):

possibly a version number (format `30.0`) (apparently "never") or "always"
just `.`. then:

i	allowed		`--inc-recursive` supported and enabled
L	allowed		symlink time-setting support (presumably: setting mtime of symlinks)
s	allowed		symlink iconv translation support (presumably: charset-translation of symlink targets)
f	allowed		flist I/O-error safety support???
x	allowed		xattr hardlink optimization not desired???
C	allowed		support checksum seed order fix???
I	allowed		support inplace_partial behavior???
v	allowed		use varint for flist & compat flags; negotiate checksum???
u	allowed		include name of uid 0 & gid 0 in the id map???

the stuff after `-e` probably doesn't have to be sanitized. the code
(`server_options()` in `options.c`) says:

```c
		/* We make use of the -e option to let the server know about
		 * any pre-release protocol version && some behavior flags. */
```

ie. it should be safe to always pass that string as it is.

# todo

- can --link-dest be "stealthily" set on the server? --remote-option allows
  it to be set, and just blindly sets it remotely. the manpage actually
  warns that it's possible to break the protocol that way. the client does
  however just send --link-dest to the server when sending.
  if sneaking it in breaks the protocol: just --link-dest=latest and have
  that as a symlink ;)

# all options (omg)

key:
denied = option is hard refused
discouraged = warning if present, unless quiet mode
avoid = warning if present and verbose mode (only in verbose mode because these need to be actually specified)
allowed = no warning, ever
optional = warning if absent and verbose mode
recommended = warning if absent
required = command is hard refused if option missing
impossible = like denied but because it cannot happen
parsed = allowed and backup.py actually also obeys it

option					allowed		because								meaning
-A						recommended	desirable but possibly unsupported	preserve ACLs
-C						discouraged	undesirable for complete backup		ignored CVS-ignored files
-D --specials --devices	recommended	desirable but possibly unsupported	preserve devices & special files
-E						impossible	superseded by -p					preserve execute bit
-H --hard-links			required	prevent infinite backup expansion	preserve hardlinks
-I --ignore-times		impossible	needed without -c; unused with -c	don't skip files that match size and time
-J						avoid		undesirable but possibly needed		don't preserve mtime on symlinks
-K						denied		insecure: arbitrary overwrite		makes the server follow symlinks, possibly overwriting arbitrary files or directories
-L						denied		undesirable for complete backup		dereference symlinks
-N						optional	desirable but possibly unsupported	preserve create times
-O						avoid		undesirable for complete backup		don't preserve mtime on directories
-R						denied		confuses the backup logic			this allows sending /boot into /boot in the boot space – why?
-S						optional?	trade-off deferred to client		efficiently handle sparse files (can help massively but only if there are sparse files. TBD this is "recommended" if its overhead is basically zero)
-U						optional	usually unnecesary					preserve atime
-W						avoid		inefficient in most cases			disable delta-transfer algorithm (usually a slowdown)
-X						recommended	desirable but possibly unsupported	preserve xattrs
-b						denied		ruins the backup, unnecessary		add a backup extension to existing files (but the backup has versioning for that)
-c						avoid		unnecessarily slow for backup		use checksums instead of time & size
-c						recommended	assures correctness for check		use checksums instead of time & size
-d						denied		undesirable for complete backup		don't recurse into directories
-g --group				required	needed for complete backup			preserve group
-k						denied		undesirable for complete backup		dereference symlink to directory locally
-l --links				required	needed for complete backup			preserve symlinks
-m						denied		undesirable for complete backup		removes empty directories?
-n						parsed		enables check mode					dry run
-o --owner				required	needed for complete backup			preserve owner
-p --perms				required	needed for complete backup			preserve permissions
-q						parsed		enables quiet also for backup.py	quiet mode
-r --recursive			required	needed for complete backup			recurse into directories
-s						denied		breaks the backup logic				sends paths over stdio (but backup logic needs to process them)
-t --times				required	needed for complete backup			preserve mtimes
-u						denied		breaks the backup logic				skip newer files on receiver (for a backup, there shouldn't be any)
-v						parsed		enables verbose also for backup.py	verbose mode
-x --one-file-system	recommended	harmless, annoying to disable		don't cross filesystem boundaries (basically necessary on client for /, does nothing on server)
-y --fuzzy				allowed		trade-off deferred to client		try to find a good base file if destination missing (can be a speedup, and reduce backup size, but computationally expensive)
-z						allowed		trade-off deferred to client		compress file data during the transfer (effectiveness depends on network vs. compression speed vs. compressability)
-@ --modify-window		denied		avoids short-opt arg parsing		set the accuracy for mtime comparisons (unnecessary because they are copied)
-B --block-size			denied		avoids short-opt arg parsing		select transfer block size (default autoselects, even the manpage doesn't fully describe that one!)

--append				denied		undesirable for valid backup		append data onto shorter files (and breaks if the existing data differs; pointlessly dangerous)
--backup-dir			denied		ruins the backup, unnecessary		creates backups in a directory (but the backup has versioning for that)
--bwlimit				allowed		trade-off deferred to client		limit socket I/O bandwidth (can be useful to not swamp the network)
--checksum-choice		allowed		harmless							choose the checksum algorithms (which doesn't really make any difference)
--checksum-seed			allowed		harmless							choose the checksum seed (which doesn't really make any difference)
--compare-dest			denied		conflicts with --link-dest			skip if present in given directory
--compress-choice		allowed		trade-off deferred to client		compression algorithm (lz4 may be very interesting there!)
--compress-level		allowed		trade-off deferred to client		zlib compression level
--copy-dest				denied		conflicts with --link-dest			copy from that directory if present (but ruins any space savings)
--copy-unsafe-links		denied		ruins the backup, like -k			"unsafe" symlinks are transformed
--daemon				denied		insecure							enable daemon mode
--debug					allowed		harmless							set debug level
--delay-updates			denied		useless and requires memory			move stuff into place in the end (but backup logic has `temp` for that)
--delete				denied		unpredictable behavior				pick one of the --delete-X at random (well not quite)
--delete-after			denied		breaks --inc-recursive				delete after transfer (but needs an additional directory scan, and breaks --inc-recursive)
--delete-before			denied		breaks --fuzzy, --inc-recursive		delete before transfer (why would anyone do that?)
--delete-delay			required	required for consistent backup		deletes files in backup (important if a file is deleted an the backup then restarted)
--delete-during			denied		breaks --fuzzy						delete files in a directory before transferring it
--delete-excluded		required	required for consistent backup		delete excluded files in backup
--delete-missing-args	denied		like --ignore-missing-args			deletes nonexistent source files given on command line
--existing				denied		ruins the backup					skip nonexisting files
--fake-super			denied		set by backup server config			store root-only stuff in xattrs
--files-from			denied		insecure: reads remote files		read file list from that REMOTE file
--force					impossible	conflicts with --delete-*			overwrite directories with files (which is always possible with --delete-*)
--from0					impossible	affects denied --*-from options		use NUL separators in file lists (if anything, we want to sneak that one in)
--groupmap				denied		like --usermap						remaps gids or groups
--iconv					denied		might break on unconvertable chars	convert filename character set
--ignore-errors			denied		might accidentally delete data		delete even if there are I/O errors
--ignore-existing		denied		ruins the backup					skip existing files (possibly leaving a truncated version on resume)
--ignore-missing-args	denied		way too error prone					ignores nonexistent source files given on command line (preventing the user form fixing that)
--info					allowed		harmless							set info level
--inplace				denied		breaks when dest file is hardlinked	update inplace
--link-dest				***			internal use by backup logic		link from directory if present there (TBD required as --link-dest=latest if it needs to match, denied if we can sneak it in)
--list-only				parsed		enables list mode					list files instead of copying them
--log-file				denied		WRITES a remote file				log operations to a REMOTE file
--log-format			allowed		used by check						this is what -i generates (used by verification)
--max-alloc				allowed		can be used to save memory			sets memory allocation limit (TBD it may be better to force that server-side)
--max-delete			denied		useless with versioning				limit number of deleted files (possibly giving an inconsistent backup)
--max-size				denied		can ruin the backup					ignore files larger than X
--min-size				denied		can ruin the backup					ignore files smaller than X
--mkpath				impossible	dest dir already exists, always		create dest dir hierarchy
--msgs2stderr			denied		mixes errors and info messages		equivalent to --stderr=all: all info & error messages go to stderr
--new-compress			allowed		like --compress-choice				uses data-matchign compression (probably zlibx)
--no-implied-dirs		impossible	affects disabled --relative			don't send implied dirs with --relative
--no-msgs2stderr		allowed		this is the (sensible) default		split streams for errors and info messages
--no-*					denied		could disable required options		disables an(y) option
--numeric-ids			required	names meaningless on backup server	use numeric user/group IDs
--old-compress			allowed		like --compress-choice				uses plain zlib (probably zlib)
--only-write-batch		denied		WRITES a remote file				write change script to a REMOTE file
--open-noatime			allowed		implied by --atime but harmless		use O_NOATIME or silently don't
--partial				parsed		leaves truncated files				keep partial files (TBD probably safe though, because the dest is `temp` until transfer complete)
--partial-dir			parsed		messes with exclude paths			keep partial files in that directory
--preallocate			denied		no benefit beyond contiguous files	allocates file before writing
--remove-sent-files		denied		probably like --remove-source-files	undocumented!
--remove-source-files	denied		would delete backup on restore		delete files after sending them
--safe-links			denied		conflicts with -l					ignore out-of-tree symlinks (ruining the backup)
--sender				parsed		also affects what "latest" means	sets transfer direction
--server				required	and must be first arg				server / slave mode
--size-only				denied		unnecessary when not writing to FAT	disable matching by mtime
--skip-compress			allowed		trade-off deferred to client		skip extensions that don't compress well
--stats					allowed		harmless, possibly useful			give some transfer stats
--suffix				impossible	controls deiabled --backup			set backup suffix
--super					denied		set by backup server config			don't silently drop most of -a (actually forced on if root mode configured)
--temp-dir				denied		insecure: writes to remote dir		set REMOTE temp directory
--timeout				discouraged	probably breaks most transfers		disconnect if no data for some time (which SSH already does anyway)
--use-qsort				denied?		probably harmless though			undocumented!
--usermap				denied		complicated to restore				remaps user IDs (which is better done with --fake-super or just being root)
--write-devices			denied		insecure: writes to REMOTE DEVICES	writes to remote devices

this list can be create using `cull_options`, which outputs it in the format
required for the rsync daemon's own perl-syntax option filter rules.

it isn't terribly useful though. it does give a list of options but in a
backup role, most of them are simply never used. doesn't really matter
whether they are pointless or dangerous. also newer versions could add
dangerous options, so anything unknown needs to be denied anyway.
