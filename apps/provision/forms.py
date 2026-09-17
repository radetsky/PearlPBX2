from django import forms

from apps.provision.models import PhoneDevice
from core.models import SIPUser
from core.validators import validate_mac_address


class SIPUserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        """Show username instead of object representation"""
        return f"{obj.username} ({obj.name})" if obj.name else obj.username


class PhoneDeviceForm(forms.ModelForm):
    sip_user = SIPUserChoiceField(
        queryset=SIPUser.objects.all().order_by("username"),
        required=False,
        empty_label="No SIP User assigned",
        help_text="Select SIP user for this device",
    )

    sip_server = forms.CharField(
        max_length=255,
        required=False,
        help_text="SIP server address for this device",
        initial="127.0.0.1",
    )

    def clean_mac_address(self):
        mac_address = self.cleaned_data.get("mac_address")
        if not mac_address:
            return mac_address
        return validate_mac_address(mac_address)

    class Meta:
        model = PhoneDevice
        fields = ["telephone_type", "mac_address", "sip_user", "sip_server"]
