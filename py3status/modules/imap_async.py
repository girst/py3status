# -*- coding: utf-8 -*-
"""
TODO: * fix all TODOs
      * MAIL_COUNT UPDATE IS NOT VISIBLE IN MAIN THREAD
      * no output to i3bar
      * instead of polling mail_{count,error}, use py3.update() -- From thread possible?
      * instead of mail-error try to use py3.log() from thread
Display number of unread messages from IMAP account.

Configuration parameters:
    allow_urgent: display urgency on unread messages (default False)
    cache_timeout: refresh interval for this module (default 60)
    criterion: status of emails to check for (default 'UNSEEN')
    format: display format for this module (default 'Mail: {unseen}')
    hide_if_zero: hide this module when no new mail (default False)
    mailbox: name of the mailbox to check (default 'INBOX')
    password: login password (default None)
    port: number to use (default '993')
    security: login authentication method: 'ssl' or 'starttls'
        (startssl needs python 3.2 or later) (default 'ssl')
    server: server to connect (default None)
    use_idle: use IMAP4rev1 IDLE instead of polling; requires compatible
        server; uses cache_timeout for IDLE's timeout; will auto detect
        when set to None (default None)
    user: login user (default None)

Format placeholders:
    {unseen} number of unread emails

Color options:
    color_new_mail: use color when new mail arrives, default to color_good

@author obb, girst

SAMPLE OUTPUT
{'full_text': 'Mail: 36', 'color': '#00FF00'}
"""
import imaplib
from threading import Thread
from time import sleep
from select import select
from socket import error as socket_error
from ssl import create_default_context
STRING_UNAVAILABLE = 'N/A'
import traceback

class Py3status:
    """
    """
    # available configuration parameters
    allow_urgent = False
    cache_timeout = 60
    criterion = 'UNSEEN'
    format = 'Mail: {unseen}'
    hide_if_zero = False
    mailbox = 'INBOX'
    password = None
    port = '993'
    security = 'ssl'
    server = None
    use_idle = None
    user = None

    class Meta:
        deprecated = {
            'rename': [
                {
                    'param': 'new_mail_color',
                    'new': 'color_new_mail',
                    'msg': 'obsolete parameter use `color_new_mail`',
                },
                {
                    'param': 'imap_server',
                    'new': 'server',
                    'msg': 'obsolete parameter use `server`',
                },
            ],
        }

    def post_config_hook(self):
        # class variables:
        self.connection = None
        self.mail_count = None #TODO: this is updated, reset to None on fatal, kept as-is on abort
        self.command_tag = 0  # IMAPcommands are tagged, so responses can be matched up to requests
        self.idle_thread = Thread()

        if self.security not in ["ssl", "starttls"]:
            raise ValueError("Unknown security protocol")

    def check_mail(self):
        self.py3.log('checking mail')
        #if self.use_idle is not False:
        if not self.idle_thread.is_alive():
            self.idle_thread = Thread(target=self._check_mail_thread, daemon=True)
            self.idle_thread.start()

        response = {'cached_until': self.py3.time_in(self.cache_timeout)}

        if self.mail_count is None: #TODO: this should hide it, as there is no data (yet)
            response['color'] = self.py3.COLOR_BAD,
            response['full_text'] = self.py3.safe_format(
                self.format, {'unseen': STRING_UNAVAILABLE})
        elif self.mail_count > 0:
            response['color'] = self.py3.COLOR_NEW_MAIL or self.py3.COLOR_GOOD
            if self.allow_urgent:
                response['urgent'] = True

        if self.mail_count == 0 and self.hide_if_zero:
            response['full_text'] = ''
        else:
            response['full_text'] = self.py3.safe_format(self.format, {'unseen': self.mail_count})

        return response

    def _connect(self):
        if self.security == "ssl":
            self.connection = imaplib.IMAP4_SSL(self.server, self.port)
        elif self.security == "starttls":
            self.connection = imaplib.IMAP4(self.server, self.port)
            self.connection.starttls(create_default_context())

    def _disconnect(self):
        try:
            if self.connection is not None:
                if self.connection.state is 'SELECTED':
                    self.connection.close()
                self.connection.logout()
        except:
            pass
        finally:
            connection = None

    def _login(self):
        if self.connection is None:
            self._connect()
        if self.connection.state is 'NONAUTH':
            self.connection.login(self.user, self.password)

    def _check_mail_thread(self):
        while True:
            try:
                self._get_mail_count()  # populates self.mail_count
                self.py3.log('set mail to '+str(self.mail_count))
                #self.py3.update()

                #if _supports_idle(connection):#TODO: this has to be done in self._connect()!!!
                if 'IDLE' in self.connection.capabilities:
                    self._idle()
                    sleep(5)  # sleep a little if _idle() returns immediately (auth error, no network, etc)
                else:
                    sleep(30)
            except (socket_error, imaplib.IMAP4.abort, imaplib.IMAP4.readonly) as e:
                self.py3.log("Recoverable error - " + str(e), level=self.py3.LOG_WARNING)
                _disconnect()
            except (imaplib.IMAP4.error, Exception) as e:
                self.py3.log(traceback.format_exc())
                self.py3.log("Fatal error - " + str(e), level=self.py3.LOG_ERROR)
                self.mail_count = None
                _disconnect()

    def _get_mail_count(self):
        try:
            self._login()

            mail_count = 0
            directories = self.mailbox.split(',')

            for directory in directories:
                self.connection.select(directory)
                criterion_response = self.connection.search(None, self.criterion)
                mails = criterion_response[1][0].split()
                mail_count += len(mails)

            self.mail_count = mail_count
        except (imaplib.IMAP4.error, Exception) as e:
            self.mail_count = None
            raise e

    # IMAP4rev1 IDLE {{{
    def _timeoutread(self, socket, count, timeout):
        """
        a wrapper around select(2) and read(2), so we don't have to worry about
        dropping network connections; returns the data read or None on timeout
        """
        from select import select

        socket.settimeout(timeout)
        socket.setblocking(0)

        if timeout > 0:
            ready = select([socket], [], [], timeout)
        else:
            ready = select([socket], [], [])

        socket.setblocking(1)

        if ready[0]:
            response = socket.read(count)
            return response
        else:
            return None

    def _idle(self):
        """
        since imaplib doesn't support IMAP4rev1 IDLE, we'll do it by hand
        will return on updates in the mailbox[0], or when a timeout is reached.
        """
        socket = None

        try:
            self._login()

            self.command_tag = (self.command_tag + 1) % 1000
            command_tag = b'X'+bytes(str(self.command_tag).zfill(3), 'ascii')
            directories = self.mailbox.split(',')
            # make sure we have selected something before idling:
            self.connection.select(directories[0])
            socket = self.connection.socket()

            socket.write(command_tag + b' IDLE\r\n')
            response = self._timeoutread(socket, 4096, 5)
            if response is None:
                self.py3.log(
                    "While initializing IDLE: server didn't respond with '+ idling' in time",
                    level=self.py3.LOG_ERROR)
            else:
                response = response.decode('ascii')
                if not response.lower().startswith('+ idling'):
                    self.py3.log("While initializing IDLE: " + str(e), level=self.py3.LOG_ERROR)

            # wait for IDLE to return with mailbox updates:
            while True:
                response = self._timeoutread(socket, 4096, self.cache_timeout)
                if response is None:
                    self.py3.log("IDLE timed out")
                    break
                else:
                    response = response.decode('ascii')
                    if response.lower().startswith('* OK'.lower()):
                        continue  # don't terminate on continuation message
                    else:
                        break

        finally:
            if socket is None: return
            socket.write(b'DONE\r\n')  # important!
            response = self._timeoutread(socket, 4096, 5)
            if response is None:
                self.py3.log("While terminating IDLE: server didn't respond with 'DONE' in time",
                    level=self.py3.LOG_WARNING)
            else:
                response = response.decode('ascii')
                expected_response = (command_tag + b' OK').decode('ascii')
                if response.lower().startswith('* '.lower()):  # '* OK Still here', mostly
                    # sometimes, more messages come in between reading and DONEing; so read them again
                    response = socket.read(4096).decode('ascii')
                if not response.lower().startswith(expected_response.lower()):
                    self.py3.log("While terminating IDLE: " + response, level=self.py3.LOG_WARNING)
        # }}}


if __name__ == "__main__":
    """
    Run module in test mode.
    """
    from py3status.module_test import module_test
    module_test(Py3status)
