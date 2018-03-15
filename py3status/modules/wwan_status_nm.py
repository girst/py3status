# -*- coding: utf-8 -*-
"""
Display wwan network operator, signal and netgen properties,
based on ModemManager, NetworkManager and dbus.

Configuration parameters:
    cache_timeout: How often we refresh this module in seconds.
        (default 5)
    format_absent: What to display when the modem is not plugged in.
        (default '')
    format_down: What to display when the modem is down.
        (default 'WWAN: {status} - {operator} {netgen} ({signal}%)')
    format_up: What to display upon regular connection
    network available placeholders are {ip_address}, {ipv4_address}, {ipv4_dns1}, {ipv4_dns2},
        {ipv6_address}, {ipv6_dns1}, {ipv6_dns2}
    wwan available placeholders are {status}, {operator}, {netgen}, {signal}
    (default 'WWAN: {status} - {operator} {netgen} ({signal}%) -> {ip_address}')
    modem: The modem device to use. If None
        will use first find modem or
        use 'busctl introspect org.freedesktop.ModemManager1 \
            /org/freedesktop/ModemManager1/Modem/0'
        and read '.EquipmentIdentifier')
        (default None)

Color options:
    color_bad: Error or no connection
    color_good: Good connection

Requires:
    ModemManager
    NetworkManager
    pydbus

@author Cyril Levis <levis.cyril@gmail.com>

SAMPLE OUTPUT
{'color': '#00FF00', 'full_text': u'WWAN: Connected - Bouygues Telecom 4G (19%) -> 10.10.0.94'}

off
{'color': '#FF0000', 'full_text': u'WWAN: Disconnected - Bouygues Telecom 4G (12%)'}
"""

from pydbus import SystemBus

STRING_WRONG_MODEM = "wrong or any modem"
STRING_UNKNOW_OPERATOR = "unknow operator"
DBUS_MODEM_PATH = 'Modem/'
DBUS_BEARER_PATH = 'Bearer/'


class Py3status:
    """
    """
    # available configuration parameters
    cache_timeout = 5
    format_absent = ''
    format_down = 'WWAN: {status} - {operator} {netgen} ({signal}%)'
    format_up = 'WWAN: {status} - {operator} {netgen} ({signal}%) -> {ip_address}'
    modem = None

    def post_config_hook(self):
        # network states dict
        self.states = {10: "Connecting", 11: "Connected"}

        # network speed dict
        # https://www.freedesktop.org/software/ModemManager/api/1.0.0/ModemManager-Flags-and-Enumerations.html#MMModemAccessTechnology
        self.speed = {
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

    def wwan_status_nm(self):
        response = {}
        response['cached_until'] = self.py3.time_in(self.cache_timeout)

        bus = SystemBus()
        try:
            modemmanager_proxy = bus.get('.ModemManager1')
            modems = modemmanager_proxy.GetManagedObjects()
        except:
            pass

        for objects in modems.items():

            modem_path = objects[0]

            try:
                modem_proxy = bus.get('.ModemManager1', modem_path)

                # we can maybe choose another selector
                eqid = str(modem_proxy.EquipmentIdentifier)

                if self.modem is None or self.modem == eqid:

                    # get status informations
                    status = modem_proxy.GetStatus()

                    # start to build return data dict
                    data = {
                        'status': 'Disconnected',
                        'signal': status['signal-quality'][0],
                        'netgen': self.speed[status['access-technologies']]
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
                    if status['state'] == 10 or status['state'] == 11:
                        # Get status in human readable
                        data['status'] = self.states[status['state']]

                        # Get ipv4 network config
                        try:
                            bearer = modem_proxy.Bearers[0]
                            bearer_proxy = bus.get('.ModemManager1', bearer)
                            ipv4 = bearer_proxy.Ip4Config
                            data['ipv4_address'] = ipv4['address']
                            data['ipv4_dns1'] = ipv4['dns1']
                            data['ipv4_dns2'] = ipv4['dns2']

                        except:
                            data['ipv6_address'] = ''
                            data['ipv6_dns1'] = ''
                            data['ipv6_dns2'] = ''

                        # Get ipv6 network config
                        try:
                            bearer = modem_proxy.Bearers[0]
                            bearer_proxy = bus.get('.ModemManager1', bearer)
                            ipv6 = bearer_proxy.Ip6Config
                            data['ipv6_address'] = ipv6['address']
                            data['ipv6_dns1'] = ipv6['dns1']
                            data['ipv6_dns2'] = ipv6['dns2']

                        except:
                            data['ipv6_address'] = ''
                            data['ipv6_dns1'] = ''
                            data['ipv6_dns2'] = ''

                        if data['ipv6_address'] != '':
                            color = self.py3.COLOR_GOOD
                            data['ip_address'] = data['ipv6_address']
                        elif data['ipv4_address'] != '':
                            color = self.py3.COLOR_GOOD
                            data['ip_address'] = data['ipv4_address']
                        else:
                            color = self.py3.COLOR_BAD
                            data['ip_address'] = 'no network config'

                        full_text = self.py3.safe_format(self.format_up, data)

                    # else disconnected
                    else:
                        full_text = self.py3.safe_format(
                            self.format_down, data)
                        color = self.py3.COLOR_BAD

                    return {'full_text': full_text, 'color': color}

            except:
                pass

        # if there is no modem
        full_text = self.py3.safe_format(self.format_absent, '')
        color = self.py3.COLOR_BAD
        return {'full_text': full_text, 'color': color}


if __name__ == "__main__":
    """
    Run module in test mode.
    """
    from py3status.module_test import module_test
    module_test(Py3status)
