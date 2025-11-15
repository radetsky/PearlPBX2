#!/usr/bin/env python3
import struct
import urllib.parse
import xml.etree.ElementTree as ET

from abc import ABC, abstractmethod
import re
import socket
from xml.dom import minidom


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
    """Abstract base class for phone configuration generators"""

    @abstractmethod
    def generate_config(self, **kwargs) -> bytes:
        """Generate a configuration file in the required format"""
        pass

    @abstractmethod
    def get_supported_models(self) -> list:
        """Return the list of supported models"""
        pass


class GrandstreamGXPGenerator(PhoneConfigGenerator):
    """Configuration generator for Grandstream GXP phones"""

    def get_supported_models(self) -> list:
        return ['GXP1200','GXP1610', 'GXP1620', 'GXP1625', 'GXP2130', 'GXP2135', 'GXP2160', 'GXP2170']

    def _generate_config_text(self, name: str, secret: str, sipserver: str, **kwargs) -> str:
        """Generate a text configuration for Grandstream"""

        # Base parameters
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

        # Additional parameters from kwargs
        for key, value in kwargs.items():
            if key.startswith('P') and key[1:].isdigit():
                config_params[key] = value

        # Sort parameters by number
        sorted_params = sorted(config_params.items(),
                               key=lambda x: int(x[0][1:]))

        # Build configuration lines
        config_lines = [f"{param}={value}" for param, value in sorted_params]
        return '\n'.join(config_lines)

    def _convert_to_binary(self, h_mac: str, config_text: str) -> bytes:
        """Convert text configuration into Grandstream binary format"""

        h_crlf = '0d0a'
        b_mac = bytes.fromhex(h_mac)
        b_crlf = bytes.fromhex(h_crlf)

        # Process configuration as in the original Perl script
        a_body = ""
        for line in config_text.split('\n'):
            line = line.strip()
            if line and '=' in line:
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip()

                # URL-encode the value
                val = urllib.parse.quote(val, safe='A-Za-z0-9._-')
                a_body += f"{key}={val}&"

        a_body += 'gnkey=0b82'

        # Padding/alignment
        if len(a_body) % 2 != 0:
            a_body += '\0'
        if len(a_body) % 4 != 0:
            a_body += '\0\0'

        a_body_bytes = a_body.encode('ascii')

        # Length and checksum
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
        """Generate the binary configuration for Grandstream"""

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

        # Remove parameters that are passed separately from kwargs
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in ['name', 'secret', 'sipserver', 'mac_address']}
        config_text = self._generate_config_text(
            name, secret, sipserver, **filtered_kwargs)
        return self._convert_to_binary(mac_address, config_text)


class CiscoSPAGenerator(PhoneConfigGenerator):
    """Configuration generator for Cisco SPA phones"""

    def get_supported_models(self) -> list:
        return ['SPA112', 'SPA122', 'SPA232D', 'SPA504G', 'SPA508G', 'SPA514G', 'SPA525G2']

    def generate_config(self, **kwargs) -> bytes:
        """Generate an XML configuration for Cisco SPA with the specified structure"""

        name = kwargs.get('name', '')
        secret = kwargs.get('secret', '')
        sipserver = kwargs.get('sipserver', '')

        if not all([name, secret, sipserver]):
            raise ValueError("name, secret, and sipserver are required parameters")

        # Create XML structure
        root = ET.Element('flat-profile')

        # Add required fields with groups
        fields = {
            'User_ID_1_': {'value': name, 'group': 'Ext_1/Subscriber_Information'},
            'Password_1_': {'value': secret, 'group': 'Ext_1/Subscriber_Information'},
            'Use_Auth_ID_1_': {'value': 'No', 'group': 'Ext_1/Subscriber_Information'},
            'Auth_ID_1_': {'value': '', 'group': 'Ext_1/Subscriber_Information'},
            'Display_Name_1_': {'value': name, 'group': 'Ext_1/Subscriber_Information'},
            'Proxy_1_': {'value': sipserver, 'group': 'Ext_1/Proxy_and_Registration'},
            'Station_Name': {'value': name, 'group': 'Phone/General'},
            'Station_Display_Name': {'value': name, 'group': 'Phone/General'},
            'Voice_Mail_Number': {'value': '', 'ua': 'rw'},
            'Text_Logo': {'value': 'PearlPBX', 'group': 'Phone/General'},
            'BMP_Picture_Download_URL': {'value': '', 'group': 'Phone/General'},
            'Select_Logo': {'value': 'Text Logo', 'group': 'Phone/General'},
            'Select_Background_Picture': {'value': 'None', 'group': 'Phone/General'},
            'Time_Format': {'value': '24hr', 'group': 'User/Supplementary_Services'},
            'DND_Serv': {'value': 'No', 'group': 'Phone/Supplementary_Services'},
        }

        for field, attributes in fields.items():
            elem = ET.SubElement(root, field)
            elem.text = attributes.get('value', '')
            for attr, attr_value in attributes.items():
                if attr != 'value':
                    elem.set(attr, attr_value)

        # Convert to bytes with pretty-printing
        tree = ET.ElementTree(root)
        try:
            ET.indent(tree, space="  ")
            xml_str = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        except AttributeError:
            rough = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            xml_str = minidom.parseString(rough).toprettyxml(encoding='utf-8')

        return xml_str


class Provisioning:
    """Main class for managing provisioning of different phones"""

    def __init__(self):
        self.generators = {
            'grandstream': GrandstreamGXPGenerator(),
            'cisco': CiscoSPAGenerator()
        }

    def get_supported_vendors(self) -> list:
        """Return the list of supported vendors"""
        return list(self.generators.keys())

    def get_supported_models(self, vendor: str) -> list:
        """Return the list of supported models for a vendor"""
        if vendor.lower() not in self.generators:
            raise ValueError(f"Vendor '{vendor}' not supported")

        return self.generators[vendor.lower()].get_supported_models()

    def generate_grandstream_config(self, mac_address: str, name: str,
                                    secret: str, sipserver: str, **kwargs) -> bytes:
        """Generate configuration for Grandstream phones"""
        return self.generators['grandstream'].generate_config(
            mac_address=mac_address,
            name=name, secret=secret,
            sipserver=sipserver, **kwargs
        )

    def generate_cisco_config(self, name: str, secret: str, sipserver: str,
                              model: str = 'SPA504G', **kwargs) -> bytes:
        """Generate configuration for Cisco SPA phones"""
        return self.generators['cisco'].generate_config(
            name=name, secret=secret, sipserver=sipserver,
            model=model, **kwargs
        )

    def save_config(self, config_data: bytes, filename: str) -> bool:
        """Save configuration to a file"""
        try:
            with open(filename, 'wb') as f:
                f.write(config_data)
            return True
        except Exception as e:
            print(f"Error saving file: {e}")
            return False

