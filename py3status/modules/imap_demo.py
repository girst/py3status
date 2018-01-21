#!/usr/bin/env python3

"""
IMAP IDLE exampe, using standard imaplib and implement IDLE ourselves
TODO:
 * create py3status module to replace main-while
 * check python2 compatibility
NOTES: 
 * the pullreq'd version can hang when the network drops out during
   IDLEing. when select() times out, it'll try to write and read 'DONE' and
   read 'OK' back, which it can't because the network's gone
   solution: wrap _every_ read(2) call in select(2)
"""

import imaplib
from threading import Thread
from ssl import create_default_context
from socket import error as socket_error
#further down: import select in _timeoutread(), import time in "main", (import sys in helper)

import sys
def readconfig(configfile):
    import configparser
    config = configparser.ConfigParser()
    config.read(configfile)
    retval = dict()
    retval['u'] = config['imap']['username']
    retval['p'] = config['imap']['password']
    retval['s'] = config['imap']['server']
    return retval

config = readconfig(sys.argv[1])

# CONFIG
criterion = 'UNSEEN'
mailbox = 'INBOX'
password = config['p']
port = '993'
security = 'ssl'
server = config['s']
user = config['u']
timeout=120 #60  # for stuff we expect after a long time
debug=False  # NOTE: enable for debug messages through eprint() and dbg()

# STATE
connection = None
mail_count = None
mail_error = None #for passing exceptions to the main thread; tuple of ('msg', severity); TODO
command_tag = 0
idle_thread = Thread() #target=_check_mail, daemon=True)

# HELPER
def log(*args, **kwargs):
    import sys
    print(*args, file=sys.stderr, **kwargs)
    sys.stderr.flush()

def eprint(*args, **kwargs):
    if not debug: return 
    import sys
    print(*args, file=sys.stderr, **kwargs)
    sys.stderr.flush()
import time
def dbg(msg):
    eprint (time.strftime("%Y-%m-%d %H:%M:%S") + ' DEBUG: ' + str(msg), end='')

# FUNS
def _supports_idle(connection):  # todo: has to be called from _connect(), otherwise a working connection cannot be guaranteed
    if connection is None: return False #temporary, see todo above
    supports_idle = 'IDLE' in connection.capabilities
    return supports_idle

def _connect():
    global connection
    if security == "ssl":
        connection = imaplib.IMAP4_SSL(server, port)
    elif security == "starttls":
        connection = imaplib.IMAP4(server, port)
        connection.starttls(create_default_context())

def _disconnect():
    global connection
    try:
        if connection is not None:
            if connection.state is 'SELECTED':
                connection.close()
            connection.logout()
    except:
        pass
    finally:
        connection = None

def _get_mail_count():
    global connection
    try:
        if connection is None:
            _connect()
        if connection.state is 'NONAUTH':
            connection.login(user, password)

        tmp_mail_count = 0
        directories = mailbox.split(',')

        for directory in directories:
            connection.select(directory)
            criterion_response = connection.search(None, criterion)
            mails = criterion_response[1][0].split()
            tmp_mail_count += len(mails)

        return tmp_mail_count
    except (socket_error, imaplib.IMAP4.abort, imaplib.IMAP4.readonly) as e:
        log(time.strftime("%Y-%m-%d %H:%M") + " WARNING: Recoverable error - " + str(e))
        _disconnect()
    except (imaplib.IMAP4.error, Exception) as e:
        log (time.strftime("%Y-%m-%d %H:%M") + " ERROR: Fatal error - " + str(e))
        _disconnect()
        #mail_count = None

def _timeoutread(socket, count, timeout):
    """
    a wrapper around select(2) and read(2), so we don't have to worry about
    dropping network connections returns the data read or None on timeout
    """
    import select

    socket.settimeout(timeout)
    socket.setblocking(0)  # so we can timeout

    eprint('select:', end="")
    if timeout > 0:
        ready = select.select([socket], [], [], timeout)
    else:
        ready = select.select([socket], [], [])

    socket.setblocking(1)

    if ready[0]:
        eprint('OK; ', end="")
        response = socket.read(count)
        eprint(str(response))
        return response
    else:
        eprint('TIMEOUT')
        return None

def _idle():
    """
    since imaplib doesn't support IMAP4r1 IDLE, we'll do it by hand
    will return on updates on the mailbox[0], or when a timeout is reached.
    """
    global connection
    global command_tag
    global timeout
    short_timeout = 5  # to be used when reading stuff we expect immediately

    socket = None

    try:
        if connection is None:
            dbg('connect(): '); _connect(); eprint('OK')
        if connection.state is 'NONAUTH':
            dbg('login(): '); connection.login(user, password); eprint('OK')

        command_tag = (command_tag + 1) % 1000
        command_tag_full = b'X'+bytes(str(command_tag).zfill(3), 'ascii')
        directories = mailbox.split(',')
        # make sure we have selected something before idling:
        dbg('select(mailbox): '); connection.select(directories[0]); eprint('OK')
        socket = connection.socket()

        dbg('write(IDLE): '); socket.write(command_tag_full + b' IDLE\r\n'); eprint('OK')
        dbg('read(+idling): ')
        response = _timeoutread(socket, 4096, short_timeout)
        if response is None:
            #raise imaplib.IMAP4.error("While initializing IDLE: server didn't respond with '+ idling' in time")
            dbg("server didn't respond with '+ idling' in time\n")
        else:
         response = response.decode('ascii')
         if not response.lower().startswith('+ idling'):
             raise imaplib.IMAP4.error("While initializing IDLE: " + str(e))

        # wait for IDLE to return
        while True:
            dbg('read(changes): '); 
            response = _timeoutread(socket,4096, timeout)
            if response is None:
                log ("INFO: timed out")
                break
            else:
                response = response.decode('ascii')
                if response.lower().startswith('* OK'.lower()):  # '* OK Still here' shouldn't terminate
                    continue
                else:
                    break

    finally:
        if socket is None: return
        dbg('write(DONE): '); socket.write(b'DONE\r\n'); eprint('OK')  # important!
        dbg('read(Axxx OK): '); 
        response = _timeoutread(socket, 4096, short_timeout)
        if response is None:
            raise imaplib.IMAP4.abort("While terminating IDLE: server didn't respond with 'DONE' in time")
        response = response.decode('ascii')
        expected_response = (command_tag_full + b' OK').decode('ascii')
        if response.lower().startswith('* '.lower()):  # '* OK Still here', mostly
            # sometimes, more messages come in between reading and DONEing; so read them again
            response = socket.read(4096).decode('ascii')
        if not response.lower().startswith(expected_response.lower()):
            raise imaplib.IMAP4.abort("While terminating IDLE: " + response)

# main:
def _check_mail():
    # TODO: try/catch
    global mail_count
    while True:
        mail_count = _get_mail_count()

        if _supports_idle(connection):
            _idle()
            time.sleep(5)  # sleep a little if _idle() returns immediately (auth error, no network, etc)
        else:
            time.sleep(30)


idle_thread = Thread(target=_check_mail, daemon=True)
idle_thread.start()


while True:
    time.sleep(5)
    print(mail_count)
