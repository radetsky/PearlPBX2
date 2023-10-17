from django import forms
from django.core import validators
from django.core.exceptions import ValidationError
from django.forms import fields
from django.utils.translation import gettext_lazy as _

from .models import SIPPeer, SIPTransport, SIPUser, DialplanContext, DialplanExtension, RoutingTable


def validate_alphanumeric(value):
    if value == "":
        return True

    try:
        value.encode('ascii')

    except UnicodeEncodeError:
        raise ValidationError(
            _('This value: %(value)s must contain only English letters and digits.'),
            params={'value': value},
        )

    if not value.isalnum():
        raise ValidationError(
            _('This value: %(value)s must contain only English letters and digits.'),
            params={'value': value},
        )


def min3len(value):
    if value == "":
        return True

    if len(value) < 3:
        raise ValidationError(
            _('This value: %(value)s must be longer than 2 characters.'),
            params={'value': value},
        )


class SIPTransportChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name}"


class DialplanContextChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name}"


class RoutingTableChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name}"


class SIPUserForm(forms.ModelForm):

    name = forms.CharField(label="Description",
                           required=True,
                           validators=[min3len],
                           help_text='Full name of user, description of connection',
                           )

    username = forms.CharField(label="Username",
                               required=True,
                               validators=[validate_alphanumeric, min3len],
                               help_text='Username/ID for the incoming connection '
                               )

    transport = SIPTransportChoiceField(label="Transport",
                                        required=True,
                                        help_text='Select transport for the user',
                                        queryset=SIPTransport.objects.all(),
                                        empty_label=None,
                                        )
    routing_table = RoutingTableChoiceField(label="Routing Table",
                                            required=True,
                                            help_text='Select routing table for the user',
                                            queryset=RoutingTable.objects.all(),
                                            empty_label=None,
                                            )

    context = DialplanContextChoiceField(label="Context",
                                         required=True,
                                         help_text='Select context for the user',
                                         queryset=DialplanContext.objects.all(),
                                         empty_label=None,
                                         )
    custom_extension = forms.CharField(label="Incoming dialplan",
                                       widget=forms.Textarea,
                                       required=False,
                                       help_text='Custom dialplan for incoming calls to the user')

    custom_settings = forms.CharField(label='Settings',
                                      widget=forms.Textarea,
                                      required=False,
                                      help_text='Custom user settings in asterisk pjsip.conf format')

    custom_auth_settings = forms.CharField(label='Auth Settings',
                                           widget=forms.Textarea,
                                           required=False,
                                           help_text='Custom user AUTH settings in asterisk pjsip.conf format')

    custom_aor_settings = forms.CharField(label='Aor Settings',
                                          widget=forms.Textarea,
                                          required=False,
                                          help_text='Custom user AOR settings in asterisk pjsip.conf format')

    class Meta:
        model = SIPUser
        fields = ['name', 'username', 'secret',
                  'transport', 'extension', 'routing_table', 'context', 'allowed_extension',
                  'custom_extension', 'custom_settings', 'custom_auth_settings', 'custom_aor_settings']

        widgets = {
            # telling Django your password field in the mode is a password input on the template
            'secret': forms.PasswordInput(render_value=True),
        }


class SIPPeerForm(forms.ModelForm):
    name = forms.CharField(label="Channel name",
                           required=True,
                           validators=[validate_alphanumeric, min3len],
                           help_text='Name of the channel. Use only English letters and digits.'
                           )

    username = forms.CharField(label="Username",
                               required=False,
                               validators=[validate_alphanumeric, min3len],
                               help_text='Optional username for the connection used for remote side.'
                               )

    transport = SIPTransportChoiceField(label="Transport",
                                        required=True,
                                        help_text='Select transport for the peer',
                                        queryset=SIPTransport.objects.all(),
                                        empty_label=None,
                                        )

    context = DialplanContextChoiceField(label="Context",
                                         required=True,
                                         help_text='Select context for the peer',
                                         queryset=DialplanContext.objects.all(),
                                         empty_label=None,
                                         )

    class Meta:
        model = SIPPeer
        fields = '__all__'

        widgets = {
            'secret': forms.PasswordInput(render_value=True)
        }


class DialplanExtensionForm(forms.ModelForm):
    context = DialplanContextChoiceField(label="Context",
                                         required=True,
                                         help_text='Select context for the extension',
                                         queryset=DialplanContext.objects.all(),
                                         empty_label=None,
                                         )
    ext = forms.CharField(label="Extension",
                          required=True,
                          help_text='Extension for the dialplan.'
                          )

    dialplan = forms.CharField(label='Dialplan',
                               widget=forms.Textarea,
                               required=True,
                               help_text='Use Asterisk AEL syntax to define the dialplan.')

    description = forms.CharField(label="Description",
                                  required=False,
                                  help_text='Description of the extension.'
                                  )

    class Meta:
        model = DialplanExtension
        fields = '__all__'
