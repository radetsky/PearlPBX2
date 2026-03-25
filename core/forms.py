from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.core.exceptions import ValidationError
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from core.models import (
    DialplanMacro,
    SIPPeer,
    SIPTransport,
    SIPUser,
    DialplanContext,
    DialplanExtension,
    RoutingTable,
    ConfigurationFile,
    Queue,
)

from core.validators import AsteriskDialplanValidator
from core.widgets import PasswordWithToggleInput


def validate_alphanumeric(value):
    if value == "":
        return True

    try:
        value.encode("ascii")

    except UnicodeEncodeError:
        raise ValidationError(
            _("This value: %(value)s must contain only English letters and digits."),
            params={"value": value},
        )

    if not value.isalnum():
        raise ValidationError(
            _("This value: %(value)s must contain only English letters and digits."),
            params={"value": value},
        )


def min3len(value):
    if value == "":
        return True

    if len(value) < 3:
        raise ValidationError(
            _("This value: %(value)s must be longer than 2 characters."),
            params={"value": value},
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
    name = forms.CharField(
        label=_("Description"),
        required=True,
        validators=[min3len],
        help_text=_("Full name of user, description of connection"),
    )

    username = forms.CharField(
        label=_("Username"),
        required=True,
        validators=[validate_alphanumeric, min3len],
        help_text=_("Username/ID for the incoming connection"),
    )

    transport = SIPTransportChoiceField(
        label=_("Transport"),
        required=True,
        help_text=_("Select transport for the user"),
        queryset=SIPTransport.objects.all(),
        empty_label=None,
    )
    nat = forms.BooleanField(
        label=_("NAT"),
        required=False,
        help_text=_(
            "Enable NAT for the user. Use only if you are sure that your user is behind NAT."
        ),
    )
    routing_table = RoutingTableChoiceField(
        label=_("Routing Table"),
        required=True,
        help_text=_("Select routing table for the user"),
        queryset=RoutingTable.objects.all(),
        empty_label=None,
    )

    auth_type = forms.ChoiceField(
        label=_("Auth type"),
        required=True,
        help_text=_("Select type of authentication"),
        choices=SIPUser.AUTHTYPE_CHOICES,
    )
    custom_extension = forms.CharField(
        label=_("Incoming dialplan"),
        widget=forms.Textarea,
        required=False,
        help_text=_("Custom dialplan for incoming calls to the user"),
    )

    custom_settings = forms.CharField(
        label=_("Settings"),
        widget=forms.Textarea,
        required=False,
        help_text=_("Custom user settings in asterisk pjsip.conf format"),
    )

    custom_auth_settings = forms.CharField(
        label=_("Auth Settings"),
        widget=forms.Textarea,
        required=False,
        help_text=_("Custom user AUTH settings in asterisk pjsip.conf format"),
    )

    custom_aor_settings = forms.CharField(
        label=_("Aor Settings"),
        widget=forms.Textarea,
        required=False,
        help_text=_("Custom user AOR settings in asterisk pjsip.conf format"),
    )

    class Meta:
        model = SIPUser
        fields = [
            "name",
            "username",
            "secret",
            "transport",
            "nat",
            "extension",
            "routing_table",
            "auth_type",
            "custom_extension",
            "custom_settings",
            "custom_auth_settings",
            "custom_aor_settings",
        ]

        widgets = {
            # telling Django your password field in the mode is a password input on the template
            "secret": PasswordWithToggleInput(),
        }


class SIPPeerForm(forms.ModelForm):
    name = forms.CharField(
        label=_("Channel name"),
        required=True,
        validators=[validate_alphanumeric, min3len],
        help_text=_("Name of the channel. Use only English letters and digits."),
    )

    username = forms.CharField(
        label=_("Username"),
        required=False,
        validators=[validate_alphanumeric, min3len],
        help_text=_("Optional username for the connection used for remote side."),
    )

    transport = SIPTransportChoiceField(
        label=_("Transport"),
        required=True,
        help_text=_("Select transport for the peer"),
        queryset=SIPTransport.objects.all(),
        empty_label=None,
    )

    routing_table = RoutingTableChoiceField(
        label=_("Routing Table"),
        required=True,
        help_text=_("Select routing table for the peer"),
        queryset=RoutingTable.objects.all(),
        empty_label=None,
    )
    custom_auth_settings = forms.CharField(
        label=_("Auth Settings"),
        widget=forms.Textarea,
        required=False,
        help_text=_("Custom user AUTH settings in asterisk pjsip.conf format"),
    )
    custom_aor_settings = forms.CharField(
        label=_("Aor Settings"),
        widget=forms.Textarea,
        required=False,
        help_text=_("Custom user AOR settings in asterisk pjsip.conf format"),
    )

    class Meta:
        model = SIPPeer
        fields = "__all__"

        widgets = {"secret": PasswordWithToggleInput()}


class DialplanExtensionForm(forms.ModelForm):
    DIALPLAN_TEMPLATE = """
NoOp(CALL BEGIN >>>> :'${CALLERID(name)}'@<${CALLERID(num)}>);
Set(CHANNEL(language)=ua);
Set(TIMEOUT(absolute)=3600);
// Only for outgoing call thru the PSTN
Set(CALLERID(num)=?
// For GSM or FXO gateways
// Set(CALLERID(num)=${CALLERID(NAME)});
// ====================================================
// Normalize the CallerID for incoming calls.
// You can edit the macro to use in your country.
// Admin -> Dialplan macros -> callerid_normalization()
// Or create the new one for your conditions.
&callerid_normalization();
// Turn on record of the call except rules in the database
AGI(agi://127.0.0.1:4573/mixmonitor,${CALLERID(num)},${EXTEN});
// And now, you can Answer the call or something else what do you want
"""

    context = DialplanContextChoiceField(
        label=_("Context"),
        required=True,
        help_text=_("Select context for the extension"),
        queryset=DialplanContext.objects.all(),
        empty_label=None,
    )
    ext = forms.CharField(
        label=_("Extension"), required=True, help_text=_("Extension for the dialplan.")
    )

    dialplan = forms.CharField(
        label=_("Dialplan"),
        widget=forms.Textarea(
            attrs={
                "cols": 80,
                "rows": 24,
                "style": "font-family:monospace; font-size:16px;",
            }
        ),
        required=True,
        help_text=_("Use Asterisk AEL syntax to define the dialplan."),
        initial=DIALPLAN_TEMPLATE.strip(),
    )

    description = forms.CharField(
        label=_("Description"),
        required=False,
        help_text=_("Description of the extension."),
    )

    def clean_dialplan(self):
        dialplan = self.cleaned_data["dialplan"]

        allowed_macros = set(DialplanMacro.objects.values_list("name", flat=True))

        validator = AsteriskDialplanValidator(allowed_macros=allowed_macros)
        try:
            validator(dialplan)
        except ValidationError as e:
            raise forms.ValidationError(e.messages)

        return dialplan

    class Meta:
        model = DialplanExtension
        fields = "__all__"


class ConfigurationFileForm(forms.ModelForm):
    class Meta:
        model = ConfigurationFile
        fields = ["name", "description", "path", "content"]
        widgets = {
            "content": forms.Textarea(attrs={"style": "font-family: monospace;"}),
        }


class RoutingTableAdminForm(forms.ModelForm):
    class Meta:
        model = RoutingTable
        fields = "__all__"

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if not name:
            return name

        # Check if the name already exists in DialplanContext.
        # Note: Both DialplanContext.name and RoutingTable.name are context names in extensions.ael and must not be the same.
        if DialplanContext.objects.filter(name=name).exists():
            raise forms.ValidationError(
                format_lazy(
                    _(
                        'Context with the name "{name}" already exists in the DialplanContext table. Please choose a different name.'
                    ),
                    name=name,
                )
            )
        return name


class DialplanContextAdminForm(forms.ModelForm):
    class Meta:
        model = DialplanContext
        fields = "__all__"

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if not name:
            return name

        # Check if the name already exists in RoutingTable.
        if RoutingTable.objects.filter(name=name).exists():
            raise forms.ValidationError(
                format_lazy(
                    _(
                        'Context with the name "{name}" already exists in the RoutingTable table. Please choose a different name.'
                    ),
                    name=name,
                )
            )
        return name


DEFAULT_QUEUE_MEMBER_PENALTY = 100


class QueueAdminForm(forms.ModelForm):
    add_sip_users = forms.ModelMultipleChoiceField(
        queryset=SIPUser.objects.all().order_by("username"),
        required=False,
        label=_("Add SIP Users"),
        help_text=format_lazy(
            _(
                "Select users to add as queue members. Each user will get INTERFACE=PJSIP/username, penalty={penalty}. Already existing members are not duplicated."
            ),
            penalty=DEFAULT_QUEUE_MEMBER_PENALTY,
        ),
        widget=FilteredSelectMultiple(_("SIP Users"), is_stacked=False),
    )

    class Meta:
        model = Queue
        fields = "__all__"
