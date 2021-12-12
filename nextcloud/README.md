# purpose

misc utilities to handle backing up from and to nextcloud.

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
