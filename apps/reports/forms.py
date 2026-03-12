from django import forms
from django.utils import timezone
from django.utils.timezone import localtime

from apps.reports.models import QueueLog
from apps.callback.models import CallbackService

ASTERISK_NONE = "NONE"


def _get_queue_choices(empty_label="All Queues"):
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
        label="Date From",
        required=False,
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "class": "uk-input uk-border-rounded",
            }
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0),
    )

    date_to = forms.DateTimeField(
        label="Date To",
        required=False,
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "class": "uk-input uk-border-rounded",
            }
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=23, minute=59, second=59, microsecond=0),
    )

    # Queue filter
    queuename = forms.ChoiceField(
        label="Queue",
        required=False,
        widget=forms.Select(attrs={"class": "uk-select uk-border-rounded"}),
        choices=[("", "All Queues")],
    )

    # Agent filter
    agent = forms.ChoiceField(
        label="Agent",
        required=False,
        widget=forms.Select(attrs={"class": "uk-select uk-border-rounded"}),
        choices=[("", "All Agents")],
    )

    # Event filter
    event = forms.MultipleChoiceField(
        label="Events",
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "uk-checkbox"}),
        choices=[
            ("ABANDON", "Abandoned"),
            ("COMPLETEAGENT", "Completed by Agent"),
            ("COMPLETECALLER", "Completed by Caller"),
            ("CONNECT", "Connected"),
            ("ENTERQUEUE", "Enter Queue"),
            ("EXITWITHKEY", "Exit with Key"),
            ("EXITWITHTIMEOUT", "Exit with Timeout"),
            ("RINGNOANSWER", "Ring No Answer"),
        ],
    )

    # Report type
    REPORT_TYPES = [
        ("summary", "Summary Statistics"),
        ("detailed", "Detailed Report"),
        ("agent_performance", "Agent Performance"),
        ("queue_performance", "Queue Performance"),
        ("lost_and_found", "Lost and Found"),
    ]

    report_type = forms.ChoiceField(
        label="Report Type",
        choices=REPORT_TYPES,
        initial="summary",
        widget=forms.RadioSelect(attrs={"class": "uk-radio"}),
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["queuename"].choices = _get_queue_choices("All Queues")

        agents = (
            QueueLog.objects.values_list("agent", flat=True)
            .distinct()
            .exclude(agent=ASTERISK_NONE)
            .order_by("agent")
        )
        self.fields["agent"].choices = [("", "All Agents")] + [(a, a) for a in agents]

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
        initial=lambda: localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0),
    )
    created_end = forms.DateTimeField(
        label="Created to",
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=23, minute=59, second=59, microsecond=0),
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
        initial=lambda: localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0),
    )

    end_date = forms.DateTimeField(
        label="End date",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=23, minute=59, second=59, microsecond=0),
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


class _AnalyticsBaseForm(forms.Form):
    date_from = forms.DateTimeField(
        label="Date From",
        required=True,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "uk-input uk-border-rounded"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0),
    )

    date_to = forms.DateTimeField(
        label="Date To",
        required=True,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "uk-input uk-border-rounded"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=23, minute=59, second=59, microsecond=0),
    )


class AnalyticsDateRangeForm(_AnalyticsBaseForm):
    exclude_contacts = forms.BooleanField(
        label="Exclude known numbers (Contacts)",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
    )


class _AnalyticsQueueFilterForm(_AnalyticsBaseForm):
    queuename = forms.ChoiceField(
        label="Queue",
        required=False,
        widget=forms.Select(attrs={"class": "uk-select uk-border-rounded"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["queuename"].choices = _get_queue_choices("All queues")


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
        ("", "All"),
        ("NEW", "New"),
        ("ANSWERED", "Answered"),
        ("BUSY", "Busy"),
        ("PENDING", "Pending"),
    ]

    start_date = forms.DateTimeField(
        label="Created from",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0),
    )

    end_date = forms.DateTimeField(
        label="Created to",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        initial=lambda: localtime(timezone.now()).replace(hour=23, minute=59, second=59, microsecond=0),
    )

    src = forms.CharField(
        label="Source number",
        max_length=16,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Enter source number"}
        ),
    )

    dst = forms.CharField(
        label="Destination number",
        max_length=16,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Enter destination number"}
        ),
    )

    dial_status = forms.ChoiceField(
        label="Dial status",
        choices=DIAL_STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    service = forms.ChoiceField(
        label="Service",
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
        choices=[("", "All")],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically populate service list
        services = CallbackService.objects.filter(is_active=True)
        service_choices = [("", "All")] + [(s.id, s.name) for s in services]
        self.fields["service"].choices = service_choices
