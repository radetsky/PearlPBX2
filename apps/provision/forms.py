import re

from django import forms
from django.core.exceptions import ValidationError

from apps.provision.models import PhoneDevice
from core.models import SIPUser


class SIPUserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        """Show username instead of object representation"""
        return f"{obj.username} ({obj.name})" if obj.name else obj.username


class PhoneDeviceForm(forms.ModelForm):
    sip_user = SIPUserChoiceField(
        queryset=SIPUser.objects.all().order_by('username'),
        required=False,
        empty_label="No SIP User assigned",
        help_text="Select SIP user for this device"
    )

    sip_server = forms.CharField(
        max_length=255,
        required=False,
        help_text="SIP server address for this device",
        initial='127.0.0.1'
    )

    def clean_mac_address(self):
        mac_address = self.cleaned_data.get('mac_address')
        if not mac_address:
            return mac_address

        # Normalize MAC address format (remove spaces and dashes, convert to uppercase)
        mac_address = re.sub(r'[\s-]', '', mac_address).upper()
        # Add colons between every 2 characters if none exist
        if ':' not in mac_address and len(mac_address) == 12:
            mac_address = ':'.join([mac_address[i:i+2] for i in range(0, 12, 2)])
        elif '-' in mac_address:
            mac_address = mac_address.replace('-', ':')

        # Validate MAC address format (XX:XX:XX:XX:XX:XX)
        mac_pattern = re.compile(r'^([0-9A-F]{2}[:]){5}([0-9A-F]{2})$')
        if not mac_pattern.match(mac_address):
            raise ValidationError(
                'Invalid MAC address format. Expected format: XX:XX:XX:XX:XX:XX (e.g., 00:1A:2B:3C:4D:5E)'
            )

        return mac_address

    class Meta:
        model = PhoneDevice
        fields = ['telephone_type', 'mac_address', 'sip_user', 'sip_server']