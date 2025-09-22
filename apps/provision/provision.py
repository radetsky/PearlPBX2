#!/usr/bin/env python3
import struct
import urllib.parse
import xml.etree.ElementTree as ET

from abc import ABC, abstractmethod
import re
import socket


def is_valid_ip(address):
    try:
        socket.inet_aton(address)
        return True
    except OSError:
        return False


def is_valid_fqdn(name):
    if len(name) > 253:
        return False
    fqdn_regex = re.compile(
        r'^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.?$'
    )
    return fqdn_regex.match(name) is not None

class PhoneConfigGenerator(ABC):
    """Абстрактний базовий клас для генераторів конфігурацій телефонів"""

    @abstractmethod
    def generate_config(self, **kwargs) -> bytes:
        """Генерує конфігураційний файл у потрібному форматі"""
        pass

    @abstractmethod
    def get_supported_models(self) -> list:
        """Повертає список підтримуваних моделей"""
        pass


class GrandstreamGXPGenerator(PhoneConfigGenerator):
    """Генератор конфігурацій для телефонів Grandstream GXP"""

    def get_supported_models(self) -> list:
        return ['GXP1610', 'GXP1620', 'GXP1625', 'GXP2130', 'GXP2135', 'GXP2160', 'GXP2170']

    def _generate_config_text(self, name: str, secret: str, sipserver: str, **kwargs) -> str:
        """Генерує текстову конфігурацію для Grandstream"""

        # Базові параметри
        config_params = {
            'P3': name,        # Display Name
            'P30': sipserver,  # NTP Server
            'P34': secret,     # SIP Password
            'P35': name,       # SIP User ID
            'P36': name,       # Authenticate ID
            'P47': sipserver,  # SIP Server
            'P48': sipserver,  # Outbound Proxy
            'P64': 840,        # Time Zone (GMT+2)
            'P75': 1,          # Daylight Saving
            'P91': 0,          # Call Waiting disabled
            'P122': 1,         # 24-hour format
            'P237': sipserver,  # Config server
            'P271': 1,         # Account Active
            'P330': 2,         # Phonebook TFTP
            'P332': 60,        # Phonebook interval
            'P401': 0          # Second account inactive
        }

        # Додаткові параметри з kwargs
        for key, value in kwargs.items():
            if key.startswith('P') and key[1:].isdigit():
                config_params[key] = value

        # Сортуємо параметри за номерами
        sorted_params = sorted(config_params.items(),
                               key=lambda x: int(x[0][1:]))

        # Формуємо конфігурацію
        config_lines = [f"{param}={value}" for param, value in sorted_params]
        return '\n'.join(config_lines)

    def _convert_to_binary(self, h_mac: str, config_text: str) -> bytes:
        """Конвертує текстову конфігурацію у binary формат Grandstream"""

        h_crlf = '0d0a'
        b_mac = bytes.fromhex(h_mac)
        b_crlf = bytes.fromhex(h_crlf)

        # Обробляємо конфігурацію як в оригінальному Perl скрипті
        a_body = ""
        for line in config_text.split('\n'):
            line = line.strip()
            if line and '=' in line:
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip()

                # URL-encode значення
                val = urllib.parse.quote(val, safe='A-Za-z0-9._-')
                a_body += f"{key}={val}&"

        a_body += 'gnkey=0b82'

        # Вирівнювання
        if len(a_body) % 2 != 0:
            a_body += '\0'
        if len(a_body) % 4 != 0:
            a_body += '\0\0'

        a_body_bytes = a_body.encode('ascii')

        # Довжина та checksum
        d_length = 8 + (len(a_body_bytes) // 2)
        b_length = struct.pack('>I', d_length)

        d_checksum = 0
        for data in [b_length, b_mac, b_crlf, b_crlf, a_body_bytes]:
            if len(data) % 2:
                data += b'\0'
            for i in range(0, len(data), 2):
                word = struct.unpack('>H', data[i:i+2])[0]
                d_checksum += word

        d_checksum = (65536 - (d_checksum & 0xFFFF)) & 0xFFFF
        b_checksum = struct.pack('>H', d_checksum)

        return b_length + b_checksum + b_mac + b_crlf + b_crlf + a_body_bytes

    def generate_config(self, **kwargs) -> bytes:
        """Генерує binary конфігурацію для Grandstream"""

        mac_address = kwargs.get('mac_address', '')
        if not isinstance(mac_address, str) or not mac_address.islower() or len(mac_address) != 12 or not all(c in '0123456789abcdef' for c in mac_address):
            raise ValueError("mac_address must be a 12-character lowercase hex string (0-9, a-f) without separators")

        name = kwargs.get('name', '')
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")

        secret = kwargs.get('secret', '')
        if not isinstance(secret, str) or not secret:
            raise ValueError("secret must be a non-empty string")

        sipserver = kwargs.get('sipserver', '')
        if not isinstance(sipserver, str) or not sipserver:
            raise ValueError("sipserver must be a non-empty string")

        if not (is_valid_ip(sipserver) or is_valid_fqdn(sipserver)):
            raise ValueError("sipserver must be a valid IPv4 address or FQDN")

        if not all([mac_address, name, secret, sipserver]):
            raise ValueError("mac_address, name, secret, and sipserver are required parameters")

        config_text = self._generate_config_text(
            name, secret, sipserver, **kwargs)
        return self._convert_to_binary(mac_address, config_text)


class CiscoSPAGenerator(PhoneConfigGenerator):
    """Генератор конфігурацій для телефонів Cisco SPA"""

    def get_supported_models(self) -> list:
        return ['SPA112', 'SPA122', 'SPA232D', 'SPA504G', 'SPA508G', 'SPA514G', 'SPA525G2']

    def generate_config(self, **kwargs) -> bytes:
        """Генерує XML конфігурацію для Cisco SPA"""

        name = kwargs.get('name', '')
        secret = kwargs.get('secret', '')
        sipserver = kwargs.get('sipserver', '')

        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        if not isinstance(secret, str) or not secret:
            raise ValueError("secret must be a non-empty string")
        if not isinstance(sipserver, str) or not sipserver:
            raise ValueError("sipserver must be a non-empty string")
        if not isinstance(sipserver, str) or not sipserver:
            raise ValueError("sipserver must be a non-empty string")
        if not (is_valid_ip(sipserver) or is_valid_fqdn(sipserver)):
            raise ValueError("sipserver must be a valid IPv4 address or FQDN")
        if not all([name, secret, sipserver]):
            raise ValueError(
                "name, secret, and sipserver are required parameters")

        # Створюємо XML структуру
        root = ET.Element('flat-profile')

        # Основні SIP параметри
        sip_params = {
            'Line_1_Display_Name': name,
            'Line_1_User_ID': name,
            'Line_1_Password': secret,
            'Line_1_Use_Auth_ID': 'Yes',
            'Line_1_Auth_ID': name,
            'Proxy_1': sipserver,
            'Register_1': sipserver,
            'Outbound_Proxy_1': sipserver,
            'Use_Outbound_Proxy_1': 'Yes',
            'Register_Expires_1': '3600',
            'Line_Enable_1': 'Yes',
            'SIP_Port_1': '5060',
            'RTP_Port_Min_1': '16384',
            'RTP_Port_Max_1': '16482'
        }

        # Додаткові параметри з kwargs
        sip_params.update(kwargs)

        # Додаємо параметри в XML
        for param, value in sorted(sip_params.items()):
            elem = ET.SubElement(root, param.replace('_', ' '))
            elem.text = str(value)

        # Конвертуємо в bytes
        xml_str = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        return xml_str


class Provisioning:
    """Основний клас для управління provisioning різних телефонів"""

    def __init__(self):
        self.generators = {
            'grandstream': GrandstreamGXPGenerator(),
            'cisco': CiscoSPAGenerator()
        }

    def get_supported_vendors(self) -> list:
        """Повертає список підтримуваних вендорів"""
        return list(self.generators.keys())

    def get_supported_models(self, vendor: str) -> list:
        """Повертає список підтримуваних моделей для вендора"""
        if vendor.lower() not in self.generators:
            raise ValueError(f"Vendor '{vendor}' not supported")

        return self.generators[vendor.lower()].get_supported_models()

    def generate_grandstream_config(self, mac_address: str, name: str,
                                    secret: str, sipserver: str, **kwargs) -> bytes:
        """Генерує конфігурацію для телефонів Grandstream"""
        return self.generators['grandstream'].generate_config(
            name=name, secret=secret,
            sipserver=sipserver, **kwargs
        )

    def generate_cisco_config(self, name: str, secret: str, sipserver: str,
                              model: str = 'SPA504G', **kwargs) -> bytes:
        """Генерує конфігурацію для телефонів Cisco SPA"""
        return self.generators['cisco'].generate_config(
            name=name, secret=secret, sipserver=sipserver,
            model=model, **kwargs
        )

    def save_config(self, config_data: bytes, filename: str) -> bool:
        """Зберігає конфігурацію у файл"""
        try:
            with open(filename, 'wb') as f:
                f.write(config_data)
            return True
        except Exception as e:
            print(f"Помилка при збереженні файлу: {e}")
            return False

