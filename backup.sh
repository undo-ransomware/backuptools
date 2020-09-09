#!/bin/sh
# this is referenced in /root/.ssh/authorized_keys like this:
# no-pty,no-port-forwarding,no-X11-forwarding,no-agent-forwarding,command="/usr/local/bin/backups.sh" ssh-ed25519 AAAA… remote-backup@supernova

# adjust the paths, obviously!
for path in / /home/cuckoo/sandbox/storage/ /home/matthias/malware/; do
	# these occasionally need adjusting, just set them according to the "denied" error
	# eg. Ubuntu has a newer rsync and sends the H; Debian doesn't
	for flags in -logDtpAXrxe.LsfxC -nlogDtpAXrcxe.iLsfxC -lHogDtpAXrxe.LsfxC -nlHogDtpAXrcxe.iLsfxC; do
		if [ "$SSH_ORIGINAL_COMMAND" = "rsync --server --sender $flags --numeric-ids . $path" ]; then
			exec ionice -c3 nice -20 $SSH_ORIGINAL_COMMAND
		fi
	done
done

echo "$SSH_ORIGINAL_COMMAND:" denied >&2
exit 1
