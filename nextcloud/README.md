# recommendations for running nextcloud

the following is *one* way of running a nextcloud instance in a way that is
secure against data theft, safe against data loss and minimum-effort to
maintain and back up. it is by far the only way of doing that, but it does
work really well for small-scale deployments which is why it is documented
here ;)

basic installation of nextcloud is convered elsewhere in sufficient detail as
to not repeat it here. it will be assumed that nextcloud's code is installed
in `/var/www/nextcloud/` and user data is kept in `/srv/cloud/` as per LSB.
the system is assumed to be Debian 10+ or similar (eg. Ubuntu). nextcloud does
work fine on RaspberryPi-like single board computers, though 2GB+ of ram is a
good idea.

## assumed requirements

- data should be secure against someone running away with the hardware running
  nextcloud, or its data storage device
- the user data must be safe against data loss, ie. the backup must be kept
  reasonably up to date (which lead to pushbackup.py)
- the backup must be secure against unauthorized disclosure, because it might
  be off-site to guard against disasters
- the backup server should not have to be trusted for confidentiality of the
  backup, only to spit the data back out when asked for it
- the encryption should be resilient against missing files or corrupt
  filesystems
- it is ok to manually mount the encrypted storage after server reboots

manually entering the apsswsord to mount the storage is annoying, but the
alternative of using a key file. which means that anyone who gets their hands
on the server also gets access to the key file and can thus access the data.
setting this up with secure boot is left as a (certainly not easy!) exercise
for the reader...

## encryption & backup

for secure storage of user data, the best option seems to be `ecryptfs` using
a straight (non-wrapped) passphrase, filename encryption and with metadata in
the file header (ie. without `ecryptfs_xattr`). because:

- it's encrypted (duh), providing data confidentiality if the storage is
  compromised but the nextcloud server isn't
- its underlying encrypted directories can be easily backed up with rsync or
  any other file-based backup, without need for separate backup encryption
- *each file is 100% self-sufficient.* as long as you have the file and know
  the passphrase, you can decrypt it. there is no magic piece of data which
  renders the entire storage useless if lost (well beyond the passphrase)
- files can be restored on a per-file level even though they're encrypted
  (corollary of files being self-sufficient). this means a partial backup can
  always be used to restore the files it contains. and it's also useful to
  selectively restore files that may have been oopsed.
- the system can boot normally without having to enter the passphrase

note that this has one big caveat: anyone who knows the passphrase and a copy
of the data can also decrypt the data. in particular, if the passphrase is
leaked then the entire data has to be reencrypted (copied over to a new
ecryptfs with a different passphrase) and the old backups disposed off. systems
with a magic control file can arrange it so that this file is backed up
separately. but that comes at the risk that if you lose this file (or if it
gets corrupted), then you lose the data.

obviously, as with any data encryption, *if you forget the passphrase, you
also lose the data.* if in doubt, use one that you use regularly. your local
account / unlock password is an obvious target because you regularly type that
one – and it usually grants access to the same data anyway, because with the
client unlocked, anyone can simply grab it from whatever folder it is synced
to on that client.

ecryptfs is set up by simply mounting it:

```sh
sudo mkdir /srv/encrypted /srv/cloud
sudo modprobe ecryptfs
sudo mount -t ecryptfs /srv/encrypted /srv/cloud
```

ecryptfs then asks for mount options:

- key type: passphrase, and enter the passphrase. no there is no verification,
  remember to verify it later!
- ciper: aes and key bytes: 16. AES is the algorithm most likely to have
  hardware acceleration and even 128 bits (= 16 bytes) is plenty secure
- plaintext passthrough: definitely no, it can be used to leak data to the
  underlying storage
- filename encryption: yes, unless you really don't care about your filenames
- allow it to cache the signatures and continue the mount

put some test data in the encrypted directory (`/srv/cloud/`), then umount it
again. create an enty in `/etc/fstab` for it (single line broken up with ⏎ for
readability):

```
/srv/encrypted /srv/cloud ecryptfs key=passphrase,ecryptfs_passthrough=n,⏎
ecryptfs_enable_filename_crypto=y,ecryptfs_cipher=aes,ecryptfs_key_bytes=16⏎
,ecryptfs_sig=1234567890abcdef,ecryptfs_fnek_sig=9876543210fedcba,⏎
ecryptfs_unlink_sigs,noauto 0 0
```

mount prints the options you selected, simply pick what it prints. then add
`noauto` to keep the system from hanging on boot while it unproductively waits
for you to type the password (on the console, presumably). note that the two
signatures will not be identical.

unmount the storage (`umount /srv/cloud`), then mount it again (simply
`mount /srv/cloud` this time). enter the passphrase and verify that the test
data is still there. if ecryptfs complains that it's the first time you're
mounting that directory (it isn't!) or if the test file is corrupt, you
mistyped the passphrase now or during setup. unmount the storage, delete
`/srv/encrypted/*` and start over. otherwise the encrypted storage is ready
to use.

NOTE: there seems to be a bug that after a reboot, you sometimes have to first
do an `ecryptfs-add-passphrase --fnek`, enter the passphrase, then execute the
`monut /srv/cloud` command and pointlessly enter the passphrase again. this
may be related to doing the mount with sudo rather than on a true root login,
though.

nextcloud handles a missing data directory somewhat gracefully – by aborting
early on for every request. while that doesn't give you a nice "out of service"
message, it does prevent the client from trying to re-upload all files. to be
on the safe side, configure apache's systemd job so that it doesn't start
unless the mount, and postgres, is available. this requires a systemd override
config which goes into `/etc/systemd/system/apache2.service.d/override.conf`
but is best created with `sudo systemctl edit apache2`:

```
[Unit]
RequiresMountsFor=/srv/cloud/
Requires=postgresql.service
After=postgresql.service
```

if you value the confidentiality of your filenames, repeat the same setup for
`/var/lib/postgresql` and `/var/lib/autopostgresqlbackup`. or just symlink
them somwehere, eg. somewhere in the main nextcloud data storage. postgres,
however, just completely fails to start when its data directory is missing.
its `/etc/systemd/system/postgresql.service.d/override.conf` override config
(`sudo systemctl edit postgresql`) could look like below, but if that path is
a symlink you probably have to specify the symlink destination:

```
[Unit]
RequiresMountsFor=/var/lib/postgresql/
```

# database

nextcloud supports SQLite, MySQL / MariaDB, Oracle and PostgreSQL. might as
well use a proper database and pick postgresql, which has excellent support
utilities on debian. in nextcloud 20, postgresql is well supported and the
docs do a good job explaining how to set it up: run `sudo -u postgres psql`
and execute

```sql
CREATE USER nextcloud CREATEDB PASSWORD 'something secret and random';
CREATE DATABASE nextcloud OWNER nextcloud;
```

then configure nextcloud's `config.php` as

```php
<?php
  "dbtype"        => "pgsql",
  "dbname"        => "nextcloud",
  "dbuser"        => "nextcloud",
  "dbpassword"    => "something secret and random",
  "dbhost"        => "localhost",
  "dbtableprefix" => "oc_",
```

peer authentication is also possible but has slightly less isolation against
other applications also running as user `www-data`. see the docs.

## redis for file locking

file locking prevents two clients from simultaneously uploading the same file,
leaving a corrupted mess on the server. it can use postgresql but using redis
is noticably faster and reduces the load on the postgresql server.

redis is normally used to coordinate locking between application servers, and
that's what the installation instructions describe. for a small installation
redis is most easily installed on the nextcloud host and can be configured in
a significantly simpler way.

in particular, if redis is only used for storing the locks of a local nextcloud
instance, it can be configured to listen on a UNIX socket and to simply never
save state at all. in `/etc/redis/redis.conf`, comment all the `save` options
and set

```
port 0
unixsocket /var/run/redis/redis.sock
```

the `config.php` snippet to use a local redis for file locking is

```php
  'filelocking.enabled' => true,
  'memcache.locking' => '\\OC\\Memcache\\Redis',
  'redis' => array (
    'host' => '/var/run/redis/redis.sock',
    'port' => 0,
    'timeout' => 0.0),
```

with a UNIX socket, redis uses peer authentication and therefore doesn't need a
password. however, the apache user `www-data` has to be member of the `redis`
group to get access: `sudo adduser www-data redis`.

redis recommends several system-wide (`sysctl`) settings but runs fine without
them, and in fact some of them are a really bad idea if other stuff is running
on the same machine. the recommended ones are:

- install `sysfsutils` and set `kernel/mm/transparent_hugepage/enabled = never`
  in `/etc/sysfs.conf`. this avoids a redis warning about 'latency and memory
  usage' and is mostly harmless to other applications
- set `net.core.somaxconn = 512` in `/etc/sysctl.d/local.conf` to avoid another
  warning. on a low-load local server it really doesn't make any difference but
  doesn't hurt.

redis also recommends these, but they are a *bad idea* in a simple local-only
setting:

- `vm.overcommit_memory = 1`, allowing arbitrary memory overcommit. this means
  applications can allocate as much memory as they want, but will then be
  OOM-killed when they try to actually use it. the JVM in general and Tomcat
  in particular eventually seem to get OOM-killed pretty reliably with
  unlimited overcommit. the only downside from running with the default
  `vm.overcommit_memory = 0` is the redis warning. and it may fail to perform
  its periodic state saving, but that's irrelevant when saving is disabled
  anyway.
- `net.ipv4.tcp_max_syn_backlog = 1024`, allowing the machine to handle more
  concurrent TCP connections. with redis listening on a UNIX socket, this
  literally only affects other services, and should thus be set according to
  other applications' needs. or not set, since the default works fine.

# backing up nextcloud

install `autopostgresqlbackup`. it can be somewhat configured in
`/etc/default/autopostgresqlbackup`, but the main point of using it is that
there isn't much to configure. unfortunately, this also means that it has
decided for you you don't want more than one backup per day. setting up a true
point-in-time-recovery with postgresql WAL archiving and `pg_basebackup` is
left as another rather hard exercise for the reader...

at that point, the backup consist simply of rsyncing ecryptfs's underlying
encrypted storage directory to the backup server. if it's a `pushbackup.py`
server, the cronjob could look like this (again, that's a single line split
with ⏎ for readability):

```
55 5 * * * root /usr/bin/rsync -axHAX --numeric-ids --delete-delay ⏎
/srv/encrypted/ backups@backuphost:nextcloud
```

restore, verify etc. are described in `pushbackup.py`'s README.

# misc utilities to handle backing up from and to nextcloud

## ncdownload.py

this script downloads a directory from nextclound and stores it locally.
unlike the sync client, it never writes to nextcloud, and also doesn't need
the Qt libraries. useful for backing up data from a hosted nextcloud where you
don't have access to the storage directories, particularly to guard against
the "your accout expired and was decommisioned" failure mode. also works for
federated shares where the data isn't in the server's data directory either
(well not in *your* data directory, that is).

## nccheck.py

utility to check whether all files synced to Nextcloud can actually be
retrieved from there. useful to guard against bit rot, or just to get extra
reassurance that the files are intact on the nextcloud instance. it reads the
sync client's config file and exclude rules for maximum ease of use.

note that the utility actually downloads every single file and compares its
contents with the local filesystem. that is, it's an incredibly slow and
resource-hungry operation. make sure to use `--log` so it can be aborted and
restarted where it left off.

originally written for a nextcloud instance that somehow managed to get a file
into a state where it couldn't be retrieved because it was empty on the
storage, but at the same time nextcloud thought the file did exist and thus
didn't re-upload it from the one machine that had it. (the solution to that
situation, by the way, is to `touch` the file, changing its modification time.
the sync client will the  upload it again.) the script was meant to check for
further zombie files, but never found any and the problem has never reappeared
since.

## ncupdate.py

a script to do unattended updates of nextcloud. isn't strictly backup related,
except it does prevent you from needing the backup because your nextcloud was
too old, has just been hacked and you now need to restore it...

the script doesn't actually do much: it runs `updater.phar` and if that
immediately says 'no update available' the scrpt swallows its output so you
don't get a useless (and daily!) email from cron.
