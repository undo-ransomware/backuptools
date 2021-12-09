# purpose

a simple rsync-based remote backup over SSH. includes cleanup of obsolete
backups if configured.

# pull backup

this is the original one. it is much simpler and somewhat easier to schedule
the backup jobs, but has a few major drawbacks. the primary reason for
making it a pull backup was that it's easier to control rsync when you're
the one invoking it, and that one of the original hosts needing backup
wouldn't have been able to connect to the backup host due to an asymmetric
firewall.

## advantages

- easier to schedule for IO and memory resources on the backup server
- somewhat easier to monitor all backups in one place (the backup server)
- client cannot maliciously flush out old backups by creating hundreds of
  new backups
- small & simple

## disadvantages

- backup server can read *anything* on all clients – including SSH keys,
  certificates etc. that are excluded from backup because recreating them is
  better than having them leaked
- client needs a fixed hostname (can be dyndns though), and has to be up
  when the backup is scheduled
- if the backup server isn't separately monitored, you don't notice that it
  has been failing for the last week
- "I want a backup now" has to be initiated from the server

## setup & usage

on the server:

- create an SSH key for connection to this client (optional, can also use a
  single key)
- save that key in `/root` as `<hostname>.key` and `<hostname>.key.pub`
- place `pullbackup.py` in `/usr/local/bin` and make sure it is `chmod +x`
- create a cronjob like `18 1 * * * root pullbackup.py -T -k 90 blackhole.tyqz.org:/ /srv/backups/blackhole-root`

on the client:

- place `backup.sh` in `/usr/local/bin` and make sure it is `chmod +x`
- configure root's `.ssh/authorized_keys` with a forced command:
```
no-pty,no-port-forwarding,no-X11-forwarding,no-agent-forwarding,command="/usr/local/bin/backups.sh" ssh-ed25519 AAAA…M remote-backup@supernova
```
- manually start the backup once and adjust the commands in `backup.sh` as
  necessary (it differs slightly, depending on the rsync versions involved)
