from django import forms
from django.utils import timezone
from django.utils.timezone import localtime
from django.utils.translation import gettext_lazy as _

from apps.reports.models import QueueLog
from apps.callback.models import CallbackService

ASTERISK_NONE = "NONE"


def _get_queue_choices(empty_label=None):
    if empty_label is None:
        empty_label = _("All Queues")
    queues = (
        QueueLog.objects.values_list("queuename", flat=True)
        .distinct()
        .exclude(queuename=ASTERISK_NONE)
        .order_by("queuename")
    )
    return [("", empty_label)] + [(q, q) for q in queues]


class QueueLogReportForm(forms.Form):
    # Date filters
    date_from = forms.DateTimeField(
        label=_("Date From"),
        required=False,
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={
                "type": "datetime-local",
                "class": "uk-input uk-border-rounded",
            }
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0),
    )

    date_to = forms.DateTimeField(
        label=_("Date To"),
        required=False,
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={
                "type": "datetime-local",
                "class": "uk-input uk-border-rounded",
            }
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=23, minute=59, second=59, microsecond=0),
    )

    # Queue filter
    queuename = forms.ChoiceField(
        label=_("Queue"),
        required=False,
        widget=forms.Select(attrs={"class": "uk-select uk-border-rounded"}),
        choices=[("", _("All Queues"))],
    )

    # Agent filter
    agent = forms.ChoiceField(
        label=_("Agent"),
        required=False,
        widget=forms.Select(attrs={"class": "uk-select uk-border-rounded"}),
        choices=[("", _("All Agents"))],
    )

    # Event filter
    event = forms.MultipleChoiceField(
        label=_("Events"),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "uk-checkbox"}),
        choices=[
            ("ABANDON", _("Abandoned")),
            ("COMPLETEAGENT", _("Completed by Agent")),
            ("COMPLETECALLER", _("Completed by Caller")),
            ("CONNECT", _("Connected")),
            ("ENTERQUEUE", _("Enter Queue")),
            ("EXITWITHKEY", _("Exit with Key")),
            ("EXITWITHTIMEOUT", _("Exit with Timeout")),
            ("RINGNOANSWER", _("Ring No Answer")),
        ],
    )

    # Report type
    REPORT_TYPES = [
        ("summary", _("Summary Statistics")),
        ("detailed", _("Detailed Report")),
        ("agent_performance", _("Agent Performance")),
        ("queue_performance", _("Queue Performance")),
        ("lost_and_found", _("Lost and Found")),
    ]

    report_type = forms.ChoiceField(
        label=_("Report Type"),
        choices=REPORT_TYPES,
        initial="summary",
        widget=forms.RadioSelect(attrs={"class": "uk-radio"}),
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["queuename"].choices = _get_queue_choices()

        agents = (
            QueueLog.objects.values_list("agent", flat=True)
            .distinct()
            .exclude(agent=ASTERISK_NONE)
            .order_by("agent")
        )
        self.fields["agent"].choices = [("", _("All Agents"))] + [(a, a) for a in agents]

    def get_queryset(self):
        """Returns filtered data based on form"""
        queryset = QueueLog.objects.all().order_by("-time")

        if self.is_valid():
            cleaned_data = self.cleaned_data

            if cleaned_data.get("date_from"):
                queryset = queryset.filter(time__gte=cleaned_data["date_from"])

            if cleaned_data.get("date_to"):
                queryset = queryset.filter(time__lte=cleaned_data["date_to"])

            if cleaned_data.get("queuename"):
                queryset = queryset.filter(queuename=cleaned_data["queuename"])

            if cleaned_data.get("agent"):
                queryset = queryset.filter(agent=cleaned_data["agent"])

            if cleaned_data.get("event"):
                queryset = queryset.filter(event__in=cleaned_data["event"])

        return queryset


# Form for searching MonitorFilenames (call recordings)
class MonitorFilenamesReportForm(forms.Form):
    src = forms.CharField(
        label=_("Source number"),
        max_length=64,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Enter source number")}
        ),
    )
    dst = forms.CharField(
        label=_("Destination number"),
        max_length=64,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Enter destination number")}
        ),
    )
    created_start = forms.DateTimeField(
        label=_("Created from"),
        required=False,
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0),
    )
    created_end = forms.DateTimeField(
        label=_("Created to"),
        required=False,
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=23, minute=59, second=59, microsecond=0),
    )


class CDRReportForm(forms.Form):
    DISPOSITION_CHOICES = [
        ("", _("All")),
        ("ANSWERED", _("Answered")),
        ("BUSY", _("Busy")),
        ("NO ANSWER", _("No answer")),
        ("FAILED", _("Failed")),
    ]

    start_date = forms.DateTimeField(
        label=_("Start date"),
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0),
    )

    end_date = forms.DateTimeField(
        label=_("End date"),
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=23, minute=59, second=59, microsecond=0),
    )

    src_number = forms.CharField(
        label=_("Source number"),
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Enter number")}
        ),
    )

    dst_number = forms.CharField(
        label=_("Destination number"),
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Enter number")}
        ),
    )
    src_channel = forms.CharField(
        label=_("Source channel"),
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Enter channel")}
        ),
    )
    dst_channel = forms.CharField(
        label=_("Destination channel"),
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Enter channel")}
        ),
    )
    disposition = forms.ChoiceField(
        label=_("Call status"),
        choices=DISPOSITION_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    min_duration = forms.IntegerField(
        label=_("Min. duration (sec)"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
    )
    max_duration = forms.IntegerField(
        label=_("Max. duration (sec)"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
    )


class _AnalyticsBaseForm(forms.Form):
    date_from = forms.DateTimeField(
        label=_("Date From"),
        required=True,
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={"type": "datetime-local", "class": "uk-input uk-border-rounded"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0),
    )

    date_to = forms.DateTimeField(
        label=_("Date To"),
        required=True,
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={"type": "datetime-local", "class": "uk-input uk-border-rounded"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=23, minute=59, second=59, microsecond=0),
    )


class AnalyticsDateRangeForm(_AnalyticsBaseForm):
    exclude_contacts = forms.BooleanField(
        label=_("Exclude known numbers (Contacts)"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
    )
    show_unique = forms.BooleanField(
        label=_("Show unique callers"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
    )


class _AnalyticsQueueFilterForm(_AnalyticsBaseForm):
    queuename = forms.ChoiceField(
        label=_("Queue"),
        required=False,
        widget=forms.Select(attrs={"class": "uk-select uk-border-rounded"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["queuename"].choices = _get_queue_choices(_("All queues"))


class AnalyticsAgentCallsForm(_AnalyticsQueueFilterForm):
    pass


class AnalyticsMissedByHourForm(_AnalyticsQueueFilterForm):
    pass


class AnalyticsCallDurationForm(_AnalyticsQueueFilterForm):
    pass


class AnalyticsQueueActivityForm(_AnalyticsQueueFilterForm):
    pass


class CallbackNumberReportForm(forms.Form):
    DIAL_STATUS_CHOICES = [
        ("", _("All")),
        ("NEW", _("New")),
        ("ANSWERED", _("Answered")),
        ("BUSY", _("Busy")),
        ("PENDING", _("Pending")),
    ]

    start_date = forms.DateTimeField(
        label=_("Created from"),
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0),
    )

    end_date = forms.DateTimeField(
        label=_("Created to"),
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=23, minute=59, second=59, microsecond=0),
    )

    src = forms.CharField(
        label=_("Source number"),
        max_length=16,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Enter source number")}
        ),
    )

    dst = forms.CharField(
        label=_("Destination number"),
        max_length=16,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Enter destination number")}
        ),
    )

    dial_status = forms.ChoiceField(
        label=_("Dial status"),
        choices=DIAL_STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    service = forms.ChoiceField(
        label=_("Service"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
        choices=[("", _("All"))],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically populate service list
        services = CallbackService.objects.filter(is_active=True)
        service_choices = [("", _("All"))] + [(s.id, s.name) for s in services]
        self.fields["service"].choices = service_choices
