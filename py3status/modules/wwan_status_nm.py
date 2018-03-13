# -*- coding: utf-8 -*-
"""
Display wwan network operator, signal and netgen properties,
based on ModemManager, NetworkManager and dbus.

Configuration parameters:
    cache_timeout: How often we refresh this module in seconds.
        (default 5)
    consider_3G_degraded: If set to True, only 4G-networks will be
        considered 'good'; 3G connections are shown
        as 'degraded', which is yellow by default. Mostly
        useful if you want to keep track of where there
        is a 4G connection.
        (default False)
    format_down: What to display when the modem is not plugged in.
        (default 'WWAN: {state} - {operator} {access_technologies} {netgen} ({signal}%)')
    format_error: What to display when modem can't be accessed.
        (default 'WWAN: {error}')
    format_up: What to display upon regular connection
        (default 'WWAN: {state} - {operator} {access_technologies} {netgen} ({signal}%)')
    modem: The modem device to use. If None
        will use first find modem or
        use 'busctl introspect org.freedesktop.ModemManager1 \
            /org/freedesktop/ModemManager1/Modem/0'
        and read '.EquipmentIdentifier')
        (default None)

Color options:
    color_bad: Error or no connection
    color_degraded: Low generation connection eg 2G
    color_good: Good connection

Requires:
    ModemManager
    NetworkManager
    pydbus

@author Cyril Levis <levis.cyril@gmail.com>

SAMPLE OUTPUT
{'color': '#00FF00', 'full_text': u'WWAN: Connected - Bouygues Telecom 4G (19%)'}

off
{'color': '#FF0000', 'full_text': u'WWAN: Disconnected - Bouygues Telecom 4G (12%)'}
"""

from enum import Enum

from pydbus import SystemBus

STRING_WRONG_MODEM = "wrong or any modem"
STRING_UNKNOW_OPERATOR = "unknow operator"


class Py3status:
    """
    """
    # available configuration parameters
    cache_timeout = 5
    consider_3G_degraded = False
    format_down = 'WWAN: {state} - {operator} {access_technologies} {netgen} ({signal}%)'
    format_error = 'WWAN: {error'
    format_up = 'WWAN: {state} - {operator} {access_technologies} {netgen} ({signal}%)'
    modem = None

    def wwan_status_nm(self):
        response = {}
        response['cached_until'] = self.py3.time_in(self.cache_timeout)

        states = {10: "Connecting", 11: "Connected"}

        # https://www.freedesktop.org/software/ModemManager/api/1.0.0/ModemManager-Flags-and-Enumerations.html#MMModemAccessTechnology
        speed = {
            16384: 'LTE',
            8192: 'EVDOB',
            4096: 'EVDOA',
            2048: 'EVDO0',
            1024: '1XRTT',
            512: 'HSPA+',
            256: 'HSPA',
            128: 'HSUPA',
            64: 'HSDPA',
            32: 'UMTS',
            16: 'EDGE',
            8: 'GPRS',
            4: 'GSM_COMPACT',
            2: 'GSM',
            0: 'POTS'
        }

        bus = SystemBus()
        for id in range(0, 20):

            # find the modem
            device = 'Modem/' + str(id)

            try:
                proxy = bus.get('.ModemManager1', device)

                # we can maybe choose another selector
                eqid = str(proxy.EquipmentIdentifier)

                if (self.modem is not None
                        and eqid == self.modem) or (self.modem is None):

                    # get status informations
                    status = proxy.GetStatus()

                    # start to build return data dict
                    data = {
                        'state': 'Disconnected',
                        'signal': status['signal-quality'][0],
                        'access_technologies': status['access-technologies'],
                        'netgen': speed[status['access-technologies']],
                        'bands': status['current-bands']
                    }

                    # if registred on network, get operator name
                    if status['m3gpp-registration-state'] == 1:
                        data['operator'] = status['m3gpp-operator-name']
                    else:
                        data['operator'] = STRING_UNKNOW_OPERATOR
                        """
                        break to be able to manage no/unplugged device
                        we break here and not later to be able 
                        to keep information will disconnected
                        """
                        break

                    # if connected or connecting
                    if status['state'] == 11 or status['state'] == 10:
                        data['state'] = states[status['state']]
                        response['full_text'] = self.py3.safe_format(
                            self.format_up, data)
                        response['color'] = self.py3.COLOR_GOOD
                    # else disconnected
                    else:
                        response['full_text'] = self.py3.safe_format(
                            self.format_down, data)
                        response['color'] = self.py3.COLOR_BAD

                    return response

                else:
                    self.py3.error(STRING_WRONG_MODEM)

            except:
                pass

        # if there is no modem
        response['full_text'] = ''
        return response


if __name__ == "__main__":
    """
    Run module in test mode.
    """
    from py3status.module_test import module_test
    module_test(Py3status)
