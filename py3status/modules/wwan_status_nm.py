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
    format_down: What to display when the modem is down.
        (default 'WWAN: {status} - {operator} {netgen} ({signal}%)')
    format_error: What to display when the modem is not plugged in or on error.
        (default 'WWAN: {error}')
        available placeholder {error}
    format_up: What to display upon regular connection
    network available placeholders are {ip}, {ipv4_address}, {ipv4_dns1}, {ipv4_dns2},
        {ipv6_address}, {ipv6_dns1}, {ipv6_dns2}
    wwan available placeholders are {status}, {operator}, {netgen}, {signal}
    (default 'WWAN: {status} - {operator} {netgen} ({signal}%) -> {ip_address}')
    modem: The modem device to use. If None
        will use first find modem or
        'busctl introspect org.freedesktop.ModemManager1 /org/freedesktop/ModemManager1/Modem/0'
        and read '.EquipmentIdentifier')
        (default None)

Color options:
    color_bad: Error or no connection
    color_good: Good connection

Requires:
    ModemManager
    NetworkManager
    pydbus

@author Cyril Levis <levis.cyril@gmail.com>, girst (https://gir.st/)

SAMPLE OUTPUT
{'color': '#00FF00', 'full_text': u'WWAN: Connected - Bouygues Telecom 4G (19%) -> 10.10.0.94'}

off
{'color': '#FF0000', 'full_text': u'WWAN: Disconnected - Bouygues Telecom 4G (12%)'}
"""

from pydbus import SystemBus

STRING_MODEMMANAGER_DBUS = 'org.freedesktop.ModemManager1'
STRING_NO_MODEM = "no modem"
STRING_NO_IP = "no ip"
STRING_UNKNOWN = "n/a"


class Py3status:
    """
    """
    # available configuration parameters
    cache_timeout = 5
    consider_3G_degraded = False
    format_down = 'WWAN: {status} - {operator} {netgen} ({signal}%)'
    format_error = 'WWAN: {status} - {error}'
    format_up = 'WWAN: {status} - {operator} {netgen} ({signal}%) -> {ip}'
    format_no_service = 'WWAN: {operator} {netgen} ({signal}%)'
    modem = None

    def post_config_hook(self):
        # network states dict
        # https://www.freedesktop.org/software/ModemManager/api/1.0.0/ModemManager-Flags-and-Enumerations.html#MMModemState
        self.states = {
            -1: 'failed',
            0:  'unknown',
            1:  'initializing',
            2:  'locked',
            3:  'disabled',
            4:  'disabling',
            5:  'enabling',
            6:  'enabled',
            7:  'searching',
            8:  'registered',
            9:  'disconnecting',
            10: 'connecting',
            11: 'connected'
        }

        # network speed dict
        # https://www.freedesktop.org/software/ModemManager/api/1.0.0/ModemManager-Flags-and-Enumerations.html#MMModemAccessTechnology
        self.speed = {
            0:        STRING_UNKNOWN,
            1 << 0:  'POTS',
            1 << 1:  'GSM',
            1 << 2:  'GSM Compact',
            1 << 3:  'GPRS',
            1 << 4:  'EDGE',
            1 << 5:  'UMTS',
            1 << 6:  'HSDPA',
            1 << 7:  'HSUPA',
            1 << 8:  'HSPA',
            1 << 9:  'HSPA+',
            1 << 10: '1XRTT',
            1 << 11: 'EVDO0',
            1 << 12: 'EVDOA',
            1 << 13: 'EVDOB',
            1 << 14: 'LTE'
        }

        # network registration states
        # https://www.freedesktop.org/software/ModemManager/api/1.0.0/ModemManager-Flags-and-Enumerations.html#MMModem3gppRegistrationState
        self.rstates = {
            0: 'IDLE',
            1: 'HOME',
            2: 'SEARCHING',
            3: 'DENIED',
            4: 'UNKNOWN',
            5: 'ROAMING'
        }

    bus = SystemBus()

    def wwan_status_nm(self):
        response = {}
        data = {}
        response['cached_until'] = self.py3.time_in(self.cache_timeout)
        response['full_text'] = self.py3.safe_format(self.format_error,
            dict(error=STRING_NO_MODEM, status="Disconnected"))
        response['color'] = self.py3.COLOR_BAD

        try:
            modemmanager_proxy = self.bus.get(STRING_MODEMMANAGER_DBUS)
            modems = modemmanager_proxy.GetManagedObjects()
        except:
            pass

        # browse modems objects
        for objects in modems.items():
            modem_path = objects[0]
            modem_proxy = self.bus.get(STRING_MODEMMANAGER_DBUS, modem_path)

            # we can maybe choose another selector
            eqid = str(modem_proxy.EquipmentIdentifier)

            # use selected modem or first find
            if self.modem is None or self.modem == eqid:

                try:
                    # get status informations
                    status = modem_proxy.GetStatus()

                    # start to build return data dict
                    try:
                        data['signal'] = status['signal-quality'][0]
                    except:
                        data['signal'] = STRING_UNKNOWN

                    try:
                        highest_access_bit = 1<<(status['access-technologies'].bit_length()-1)
                        data['netgen'] = self.speed[highest_access_bit]
                    except:
                        data['netgen'] = STRING_UNKNOWN

                    # if registred on network, get operator name
                    try:
                        if self.rstates[status['m3gpp-registration-state']] in ('HOME', 'ROAMING'):
                            data['operator'] = status['m3gpp-operator-name']
                        else:
                            data['operator'] = STRING_UNKNOWN
                    except:
                        data['operator'] = STRING_UNKNOWN

                    # use human readable format
                    data['status'] = self.states[status['state']]

                    if status['state'] == 11:  # connected
                        # Get network config
                        bearer = modem_proxy.Bearers[0]
                        network_config = self._get_network_config(bearer)

                        # Add network config to data dict
                        data.update(network_config)

                        if data['ip']:
                            if self.consider_3G_degraded and data['netgen'] != 'LTE':
                                response['color'] = self.py2.COLOR_DEGRADED
                            else:
                                response['color'] = self.py3.COLOR_GOOD
                            response['full_text'] = self.py3.safe_format(
                                self.format_up, data)
                        else:
                            response['color'] = self.py3.COLOR_DEGRADED
                            response['full_text'] = self.py3.safe_format(
                                self.format_no_service, data)

                    else:  # disconnected
                        response['full_text'] = self.py3.safe_format(
                            self.format_down, data)
                        response['color'] = self.py3.COLOR_BAD

                except:
                    data['error'] = self.states[status['state']]
                    response['color'] = self.py3.COLOR_BAD
                    response['full_text'] = self.py3.safe_format(self.format_error, data)

        return response

    # get network config function
    def _get_network_config(self, bearer):
        try:
            bearer_proxy = self.bus.get(STRING_MODEMMANAGER_DBUS, bearer)

            network_config = {}

            # Get ipv4 config
            ipv4 = bearer_proxy.Ip4Config
            if ipv4['address']:
                network_config['ipv4_address'] = ipv4['address']
                network_config['ipv4_dns1'] = ipv4['dns1']
                network_config['ipv4_dns2'] = ipv4['dns2']
                network_config['ip'] = ipv4['address']
            else:
                network_config['ipv4_address'] = ''
                network_config['ipv4_dns1'] = ''
                network_config['ipv4_dns2'] = ''
                network_config['ip'] = STRING_NO_IP

            # Get ipv6 network config
            ipv6 = bearer_proxy.Ip6Config
            if ipv6['address']:
                network_config['ipv6_address'] = ipv6['address']
                network_config['ipv6_dns1'] = ipv6['dns1']
                network_config['ipv6_dns2'] = ipv6['dns2']
                network_config['ip6'] = ipv6['address']
            else:
                network_config['ipv6_address'] = ''
                network_config['ipv6_dns1'] = ''
                network_config['ipv6_dns2'] = ''
                network_config['ip6'] = STRING_NO_IP

        except:
            pass

        finally:
            return network_config


if __name__ == "__main__":
    """
    Run module in test mode.
    """
    from py3status.module_test import module_test
    module_test(Py3status)
