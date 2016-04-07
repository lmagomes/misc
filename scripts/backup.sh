#!/bin/bash
PATH=$PATH:/usr/local/bin/

# get postgres password from home config
export PGPASSWORD=`cat /home/lgomes/.config/postgrespw`

# some other variables
export BACKUPFOLDER=/mnt/data/raspbackup
export BACKUPID=0B6jHaMqrb3iYdlF4QTNId0luRkE

export BANANABACKUPFOLDER=/mnt/data/bananabackup
export BANANABACKUPID=0B6jHaMqrb3iYal9BRHBUdHZNNkk

# backup files
crontab -l >  $BACKUPFOLDER/crontab
cat /etc/fstab > $BACKUPFOLDER/fstab
cat /home/lgomes/.config/me.ini | gpg --batch --yes -r lgomes -e -o $BACKUPFOLDER/me.ini.gpg
cat /home/lgomes/.config/postgrespw | gpg --batch --yes -r lgomes -e -o $BACKUPFOLDER/postgrespw.gpg
/home/lgomes/projects/python/penv/bin/pip freeze > $BACKUPFOLDER/requirements.txt

# dump database
pg_dump -C -h neko | gpg --batch --yes -r lgomes -e -o $BACKUPFOLDER/database.sql.gpg



# sync data with google drive
gdrive sync upload --no-progress $BACKUPFOLDER $BACKUPID
gdrive sync upload --no-progress $BANANABACKUPFOLDER $BANANABACKUPID


tar czf /mnt/data/notebooks.tar.gz /home/lgomes/projects/python/notebooks
tar czf /mnt/data/misc.tar.gz /home/lgomes/projects/misc
