from django import forms
from django.utils import timezone
from datetime import timedelta


# Form for searching MonitorFilenames (call recordings)
class MonitorFilenamesReportForm(forms.Form):
    src = forms.CharField(
        label="Source number",
        max_length=64,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Enter source number"}
        ),
    )
    dst = forms.CharField(
        label="Destination number",
        max_length=64,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Enter destination number"}
        ),
    )
    created_start = forms.DateTimeField(
        label="Created from",
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
    )
    created_end = forms.DateTimeField(
        label="Created to",
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
    )


class CDRReportForm(forms.Form):
    DISPOSITION_CHOICES = [
        ("", "All"),
        ("ANSWERED", "Answered"),
        ("BUSY", "Busy"),
        ("NO ANSWER", "No answer"),
        ("FAILED", "Failed"),
    ]

    start_date = forms.DateTimeField(
        label="Start date",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        initial=lambda: timezone.now().replace(hour=0, minute=0, second=0)
        - timedelta(days=1),
    )

    end_date = forms.DateTimeField(
        label="End date",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        initial=lambda: timezone.now(),
    )

    src_number = forms.CharField(
        label="Source number",
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Enter number"}
        ),
    )

    dst_number = forms.CharField(
        label="Destination number",
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Enter number"}
        ),
    )
    src_channel = forms.CharField(
        label="Source channel",
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Enter channel"}
        ),
    )
    dst_channel = forms.CharField(
        label="Destination channel",
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Enter channel"}
        ),
    )
    disposition = forms.ChoiceField(
        label="Call status",
        choices=DISPOSITION_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    min_duration = forms.IntegerField(
        label="Min. duration (sec)",
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
    )
    max_duration = forms.IntegerField(
        label="Max. duration (sec)",
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
    )
