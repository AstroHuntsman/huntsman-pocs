#!/bin/bash
sudo service ssh restart
sudo chmod a+rw /dev/fuse
sudo chown -R $PANUSER $PANDIR
cd $HUNTSMAN_POCS
byobu new-session -d -s TestDisplay
byobu select-pane -t 0
byobu send-keys "$@" Enter
byobu split-window -h
byobu select-pane -t 1
byobu send-keys "sleep 10 && grc tail -F -n 100 $PANDIR/logs/pytest-all.log" Enter
byobu select-pane -t 0
byobu
