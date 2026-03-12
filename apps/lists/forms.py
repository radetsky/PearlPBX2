from django import forms

from core.models import Blacklist, Contact, Whitelist

_INPUT = {"class": "uk-input uk-border-rounded"}
_DT_INPUT = {"type": "datetime-local", "class": "uk-input uk-border-rounded"}

_LIST_FIELDS = ["callerid", "destination", "reason", "expiration_date"]
_LIST_WIDGETS = {
    "callerid": forms.TextInput(attrs=_INPUT),
    "destination": forms.TextInput(attrs=_INPUT),
    "reason": forms.TextInput(attrs=_INPUT),
    "expiration_date": forms.DateTimeInput(attrs=_DT_INPUT, format="%Y-%m-%dT%H:%M"),
}


class BlocklistForm(forms.ModelForm):
    class Meta:
        model = Blacklist
        fields = _LIST_FIELDS
        widgets = _LIST_WIDGETS


class AllowlistForm(forms.ModelForm):
    class Meta:
        model = Whitelist
        fields = _LIST_FIELDS
        widgets = _LIST_WIDGETS


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["callerid", "name"]
        widgets = {
            "callerid": forms.TextInput(attrs=_INPUT),
            "name": forms.TextInput(attrs=_INPUT),
        }
