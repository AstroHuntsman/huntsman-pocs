import socket
import time
import datetime
import pytz
try:
    from setproctitle import setproctitle
    setproctitle('sqmdaq_sdf')
except ImportError:
    pass

# Data acquisition routine for single stationary SQM-LE

def getdata(sqmcommand): # Procedure for sending rx, cx and ix requests
    if sqmcommand == 'rx':    strlen = 55
    elif sqmcommand == 'ix': strlen = 37
    elif sqmcommand == 'cx':    strlen = 56 # Expected lengths of SQM commands
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect((sqmurl,sqmport))
    s.send(sqmcommand)
    msg = ''
    while len(msg) < strlen: # Receives response from SQM
        chunk = s.recv(strlen-len(msg))
        if chunk == '':    raise RuntimeError("Cannot connect to SQM!")
        msg = msg + chunk
    if sqmcommand == 'rx':    timenow = datetime.datetime.utcnow().replace(tzinfo=pytz.utc) # If rx sent and SQM responded, get current time
    s.close
    if sqmcommand == 'rx':    return msg, timenow
    else:    return msg # Returns SQM response and for rx command, also the current time in UTC

def datalinestr(): # Data line formatting
    rxstr, timenow = getdata('rx')
    utimestr = timenow.strftime("%Y-%m-%dT%H:%M:%S.")+(('{0:06d}').format(timenow.microsecond))[:3]+';'

    tempstr = str(int(rxstr[48:52]))+'.'+rxstr[53:54]+';'
    cyclestr = str(int(rxstr[23:33]))+';'
    freqstr = str(int(rxstr[10:20]))+';'
    magstr = str(int(rxstr[2:5]))+'.'+rxstr[6:8]
    return utimestr+ltimestr+tempstr+cyclestr+freqstr+magstr+'\r\n'
