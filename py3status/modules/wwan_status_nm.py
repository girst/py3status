# -*- coding: utf-8 -*-
"""
Display wwan network operator, signal and netgen properties,
based on ModemManager, NetworkManager and dbus.

Configuration parameters:
    cache_timeout: How often we refresh this module in seconds.
        (default 5)
    format_down: What to display when the modem is down.
        (default 'WWAN: {status} - {operator} {netgen} ({signal}%)')
    format_error: What to display when the modem is not plugged in or on error.
        (default 'WWAN: {status}')
        available placeholders {status}, {error}
    format_up: What to display upon regular connection
    network available placeholders are {ip}, {ipv4_address}, {ipv4_dns1}, {ipv4_dns2},
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

STRING_MODEMMANAGER_DBUS = 'org.freedesktop.ModemManager1'
STRING_NO_MODEM = "no modem"
STRING_NO_IP = "no ip"
STRING_UNKNOW_OPERATOR = "unknow operator"


class Py3status:
    """
    """
    # available configuration parameters
    cache_timeout = 5
    format_down = 'WWAN: {status} - {operator} {netgen} ({signal}%)'
    format_error = 'WWAN: {status} - {error}'
    format_up = 'WWAN: {status} - {operator} {netgen} ({signal}%) -> {ip}'
    format_no_service = 'WWAN: {operator} {netgen} ({signal}%)'
    modem = None

    def post_config_hook(self):
        # network states dict
        self.states = {
            0: "Connecting",  # not sure
            1: "Connecting",  # not sure
            2: "Connecting",  # not sure
            3: "Disabled",
            4: "Disabling",
            5: "Home",
            6: "Connecting",
            7: "Searching",
            8: "Registred",
            9: "Connecting",
            10: "Connecting",
            11: "Connected"
        }

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
            192: 'HSUPA',  # not sure
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

    def wwan_status_nm(self):
        response = {}
        data = {}
        response['cached_until'] = self.py3.time_in(self.cache_timeout)

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
                    if status['signal-quality']:
                        data['signal'] = status['signal-quality'][0]

                    if status['access-technologies']:
                        data['netgen'] = self.speed[status[
                            'access-technologies']]

                    # if registred on network, get operator name
                    if status['m3gpp-registration-state'] == 1:
                        data['operator'] = status['m3gpp-operator-name']
                    else:
                        data['operator'] = STRING_UNKNOW_OPERATOR

                    # use human readable format
                    data['status'] = self.states[status['state']]

                    if status['state'] == 11:

                        # Get network config
                        bearer = modem_proxy.Bearers[0]
                        network_config = self._get_network_config(bearer)

                        # Add network config to data dict
                        data.update(network_config)

                        if data['ip']:
                            color = self.py3.COLOR_GOOD
                            full_text = self.py3.safe_format(
                                self.format_up, data)
                        else:
                            color = self.py3.COLOR_DEGRADED
                            full_text = self.py3.safe_format(
                                self.format_no_service, data)

                    # else disconnected
                    else:
                        full_text = self.py3.safe_format(
                            self.format_down, data)
                        color = self.py3.COLOR_BAD

                except:
                    data['error'] = STRING_NO_MODEM
                    data['status'] = self.states[status['state']]
                    color = self.py3.COLOR_BAD
                    full_text = self.py3.safe_format(self.format_error, data)

                finally:
                    return {'full_text': full_text, 'color': color}

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
