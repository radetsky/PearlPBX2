"""
Utility for bulk generation of phone device configuration files
"""

import os
from apps.provision.models import PhoneDevice
from apps.provision.provision import (
    Provisioning,
    GrandstreamGXPGenerator,
    CiscoSPAGenerator,
)

from core.models import Settings


class PhoneProvisioningManager:
    """Manager for provisioning phone devices"""

    def __init__(self, config_directory="/var/lib/tftpboot/"):
        self.config_directory = config_directory
        self.provisioning = Provisioning()

        # Mapping of phone types to vendors and generators
        self.phone_mapping = {
            "spa502g": ("cisco", "SPA502G"),
            "spa504g": ("cisco", "SPA504G"),
            "gxp1200": ("grandstream", "GXP1200"),
        }

        # Create the configuration directory if it does not exist
        os.makedirs(config_directory, exist_ok=True)

    def normalize_mac_address(self, mac_address):
        """Normalize MAC address to the required format"""
        # Remove all separators and convert to lowercase
        mac_clean = (
            mac_address.replace(":", "").replace("-", "").replace(" ", "").lower()
        )

        if len(mac_clean) != 12:
            raise ValueError(f"Invalid MAC address format: {mac_address}")

        return mac_clean

    def get_sip_server(self):
        """Get SIP server address from settings"""
        settings_obj = Settings.objects.first()
        if settings_obj:
            return settings_obj.ip_addr_for_provisioning
        return "192.168.0.1"  # fallback

    def generate_config_for_device(self, device):
        """Generate configuration for a single device"""
        if not device.sip_user:
            raise ValueError(f"Device {device.mac_address} has no SIP user assigned")

        if device.telephone_type not in self.phone_mapping:
            raise ValueError(
                f"Phone type {device.telephone_type} is not supported for provisioning"
            )

        vendor, model = self.phone_mapping[device.telephone_type]
        sip_server = self.get_sip_server()
        if device.sip_server and device.sip_server.strip():
            sip_server = device.sip_server.strip()

        # Prepare parameters
        params = {
            "name": device.sip_user.username,
            "secret": device.sip_user.secret,
            "sipserver": sip_server,
        }

        # Add MAC address for Grandstream
        if vendor == "grandstream":
            params["mac_address"] = self.normalize_mac_address(device.mac_address)

        # Generate configuration
        if vendor == "cisco":
            generator = CiscoSPAGenerator()
            config_data = generator.generate_config(**params)
            filename = f"{model}/{device.mac_address.replace(':', '').lower()}.xml"  # Cisco files in model-specific dirs
        elif vendor == "grandstream":
            generator = GrandstreamGXPGenerator()
            config_data = generator.generate_config(**params)
            filename = f"cfg{device.mac_address.replace(':', '').lower()}"
        else:
            raise ValueError(f"Unsupported vendor: {vendor}")

        return config_data, filename

    def save_config_file(self, config_data, filename):
        """Save configuration file"""
        filepath = os.path.join(self.config_directory, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "wb") as f:
            f.write(config_data)

        return filepath

    def provision_device(self, device):
        """Full provisioning cycle for a single device"""
        try:
            # Generate configuration
            config_data, filename = self.generate_config_for_device(device)

            # Save file
            filepath = self.save_config_file(config_data, filename)

            return {
                "success": True,
                "device_mac": device.mac_address,
                "filename": filename,
                "filepath": filepath,
                "size": len(config_data),
            }

        except Exception as e:
            return {"success": False, "device_mac": device.mac_address, "error": str(e)}

    def provision_all_supported_devices(self):
        """Provision all supported devices"""
        # Filter only supported phone types
        supported_types = list(self.phone_mapping.keys())

        devices = PhoneDevice.objects.filter(
            telephone_type__in=supported_types,
            sip_user__isnull=False,
            mac_address__isnull=False,
        ).exclude(mac_address="")

        results = {"total_devices": devices.count(), "successful": [], "failed": []}

        for device in devices:
            result = self.provision_device(device)

            if result["success"]:
                results["successful"].append(result)
            else:
                results["failed"].append(result)

        return results
