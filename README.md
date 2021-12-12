# purpose

scripts for making an rsync server that can be transparently rsync'd to as if
it was just a plain directory, but which actually creates a hardlink-based
snapshot each time it is written to. includes cleanup of obsolete backups if
configured, with some flexibility as to what "obsolete" means.

this whole thing is a giant hack because it rewrites the `rsync --server`
command that rsync send to the remote machine. it isn't a bad as it sounds
though: `--server` mode isn't fully documented but cannot change that much
without breaking backwards compatibility. also, rsync actually has an option
`--remote-option` precisely to run the `rsync --server` process with different
options than the local rsync, so it is supported to some extent.

the repo also contains scripts for a [pull-type backup](pullbackup/README.md),
and [auxiliary scripts for backup to and from nextcloud](nextcloud/README.md).

## advantages of push-type backup

- client can backup from wherever it is and whenever it wants (and is up)
- client is in control of excludes and therefore can prevent leaking secrets
- client cannot maliciously flush out old backups by creating hundreds of
  new backups
- no client-side setup required beyond creating a cronjob that calls rsync
  (though with a rather long command line if excludes are involved)
- backups can be easily listed and restored from client-side
- "I want a backup now" is easily done from client-side

## disadvantages / limitations

- server needs a fixed hostname, and has to actually be reachable by all
  backup clients (beware asymmetrical firewalls)
- clients are hard to schedule on the server: if they all connect at the same
  time, the server may run out of memory, and IO will definitely not be
  particularly fast
- monitoring missed backups on the server is somewhat harder than for the
  pull backup
- backups cannot be triggered by the server at all

# client-side usage

client-side usage is generally simply 'like rsync', though there are minor
differences:

- different connecting hosts see different storage spaces. this is analogous to
  connecting with different users, but here is actually determined by the ssh
  key the client uses for login.
- the 'directory' after the backup hostname isn't actually a directory, but a
  backup space as configured on the server (see below). for restores, you can
  target a particular backup by its timestamp.
- the server will reject or force some options. some of these are required for
  proper operation, others keep you from creating a corrput backup.
- you cannot back up only part of the source directory. the script internally
  uses `rsync --link-dest` which doesn't support partial updates.
- restore and list don't support multiple source arguments. when rung from SSH
  with a forced command, these cannot be distingushed from arguments containg
  spaces.

## backup

backup can be as simple as
`rsync -avxHAX --delete-delay --numeric-ids / backups@supernova:root`
though you probably want to add some excludes. make sure the source path
always ends with a slash so that rsync sends the directory contentes rather
than the directory itself. that is, the correct command for `/var` is
`rsync -avxHAX --delete-delay --numeric-ids /var/ backups@supernova:var`.
removing `-v` (verbose) and adding `-q` (quiet mode) can be useful to reduce
the amount of logging, especially for cronjobs.

excludes are specified as described INCLUDE/EXCLUDE PATTERN RULES in the rsync
manpage. essentially, it's usually either `-e /var/tmp/` (leading & trailing
slash) to exclude a directory and all its contents, or `-e /var/tmp/**` to
backup the directory itself but exclude its contents. the latter is correct
for /tmp, /var/tmp and similar directories where the directory needs to exist
and with a particular set of permissions, but its contents are temporary cruft.

## verify

backup verification is done by doing a dry-run transfer in checksum mode,
that is, by adding `-nic` to the backup command:
`rsync -avxHAXnic --delete-delay --numeric-ids / backups@supernova:root`.
checksum mode (`-c`) isn't strictly necessary but the verification doesn't
verify much without it. either `-v` or `-i` is required to get output.
normally you'd want to use the same excludes as for the backup, but omitting
them explicitly can be useful to get a list of excluded files as well.

unlike backup, verify mode can target a particular backup to compare against,
see restore mode below.

## restore

restoring essentially involves swapping source and destination operands as in
`rsync -avxHAX --delete-delay --numeric-ids backups@supernova:root /` though
you'd never want to restore to '/'. this can restore individual directories or
single files the way you'd usually do with rsync:
`rsync -avxH --numeric-ids backups@supernova:root/etc/default/ /etc/default`.
don't forget the trailing slash, though, or the restored data will end up in
`/etc/default/default`.

restore mode is much more flexible with respect to the options it accepts.
essentially, it accepts anything that only affects the client or that may not
be supported by the client. in particular `-AX` (ACLs and extended attributes)
are optional. so is `-H` (hardlinks), though you almost always want to preserve
those for a system backup. obviously you can restore to a different path than
the one you originally backed it up from: rsync just doesn't care. symlinks may
break in the same way they do when you move them, but for system backup that's
usually better than messing them up.

a particular backup can be targeted for restore by attaching its timestamp to
the name of the backup space: `backups@supernova:root@2020-01-01_00-00-00`
targets the `root` space as it was on that date. this timestamp can be
shortened as long as it stays unique – if there was no other backup on that
day, `backups@supernova:root@2020-01-01` also selects that backup. this can be
combined with paths as in `backups@supernova:root@2020-01-01/etc/default/`.

## list mode

backup data can be listed using `rsync --list-only`, either with or without
recursive mode (`-r`): `rsync --list-only backups@supernova:root` lists the
files in the root, `rsync -r --list-only backups@supernova:root` lists the
entire tree, and `rsync -r --list-only backups@supernova:root/etc/` lists a
subdirectory tree.

timestamp specifications are similar to restore mode, but behave differently:
- if no path is given (`backups@supernova:root@2020-01`), it lists all
  backups matching that specification (and their contents if `-r` is given).
  in particular, a timestamp of `@` matches all backups (it's a simple prefix
  match), so that `rsync --list-only backups@supernova:root@` can be used to
  list all backups for a backup space.
- if a path is given, it behaves identically to restore, and lists the contents
  of the backup space at that point in time, which must be unique. note that
  you can give the path as `/.` to force this behavior:
  `rsync --list-only backups@supernova:root@2020-01-01/.` lists that particular
  backup if it's unique.
