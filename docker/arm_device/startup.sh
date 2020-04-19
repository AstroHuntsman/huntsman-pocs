echo $PANUSER | sudo -S chown -R /home/$PANUSER/.ssh $PANUSER
cd $HUNTSMAN_POCS
python $HUNTSMAN_POCS/scripts/run_device.py
