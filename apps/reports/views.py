import csv
import mimetypes
import os

from django.views import View
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import HttpResponse, Http404, FileResponse, JsonResponse

from apps.callback.models import CallbackNumber

from apps.reports.mixins import ReportViewPermissionMixin
from apps.reports.models import CDR
from apps.reports.forms import CDRReportForm, MonitorFilenamesReportForm, CallbackNumberReportForm

from core.models import MonitorFilenames

from django.views.generic import FormView
from django.db.models import Count, Avg, F, Case, When, IntegerField
from django.db.models.functions import Cast

from django.db.models.functions import TruncDate, TruncHour
from .forms import QueueLogReportForm
from .models import QueueLog

CONTENT_TYPE_CSV = "text/csv"



# AJAX endpoint: return all QueueLog records for a given callid as JSON
class QueueLogRecordsByCallIdView(ReportViewPermissionMixin, View):
    def get(self, request, callid):
        records = QueueLog.objects.filter(callid=callid).order_by('time')
        data = [
            {
                "time": r.time.strftime('%Y-%m-%d %H:%M:%S') if r.time else '',
                "callid": r.callid,
                "queuename": r.queuename,
                "agent": r.agent,
                "event": r.event,
                "data1": r.data1,
                "data2": r.data2,
                "data3": r.data3,
                "data4": r.data4,
                "data5": r.data5,
            }
            for r in records
        ]
        return JsonResponse({"records": data})

class QueueLogReportView(ReportViewPermissionMixin, FormView):
    template_name = "queue.html"
    form_class = QueueLogReportForm

    def get(self, request, *args, **kwargs):
        """Handle GET requests for pagination"""
        if request.GET:
            # Create form with GET data for pagination
            form = QueueLogReportForm(request.GET)
            if form.is_valid():
                return self.form_valid(form)
            else:
                return self.form_invalid(form)
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        queryset = form.get_queryset()
        report_type = form.cleaned_data.get("report_type", "summary")

        context.update(
            {
                "queryset": queryset,
                "report_data": self.get_report_data(queryset, report_type, self.request),
                "report_type": report_type,
                "total_records": queryset.count(),
            }
        )

        # Якщо запит на експорт
        if self.request.GET.get("export") == "csv":
            return self.export_csv(queryset, report_type)

        return render(self.request, self.template_name, context)

    def form_invalid(self, form):
        # If form is invalid, show basic data
        context = self.get_context_data(form=form)
        queryset = QueueLog.objects.none()
        context.update(
            {
                "queryset": queryset,
                "report_data": {},
                "report_type": "summary",
                "total_records": 0,
            }
        )
        return render(self.request, self.template_name, context)

    def get_report_data(self, queryset, report_type, request=None):
        """Generates report data based on type"""
        if report_type == "summary":
            return self.get_summary_data(queryset)
        elif report_type == "detailed":
            return self.get_detailed_data(queryset, request)
        elif report_type == "agent_performance":
            return self.get_agent_performance_data(queryset)
        elif report_type == "queue_performance":
            return self.get_queue_performance_data(queryset)
        elif report_type == "lost_and_found":
            return self.get_lost_and_found_data(queryset)

        return {}

    def _get_callerid_for_lost_call(self, lost, CDR):
        """Extract callerid from CDR or fallback to queue log fields."""
        if lost.callid:
            cdr = CDR.objects.filter(uniqueid=lost.callid).first()
            if cdr:
                return cdr.src
        return lost.agent or lost.data1 or lost.callid

    def get_lost_and_found_data(self, queryset):
        """Lost and Found report: For each ABANDON, find callerid, then in CDR find calls from/to this number after ABANDON."""
        from apps.reports.models import CDR

        lost_calls = queryset.filter(event="ABANDON").order_by("-time")[:50]
        results = []
        for lost in lost_calls:
            callerid = self._get_callerid_for_lost_call(lost, CDR)
            abandon_time = lost.time

            incoming = (
                CDR.objects.filter(src=callerid, start__gt=abandon_time, disposition="ANSWERED")
                .order_by("start")
                .first()
            )
            outgoing = (
                CDR.objects.filter(dst=callerid, start__gt=abandon_time, disposition="ANSWERED")
                .order_by("start")
                .first()
            )
            results.append({
                "abandon_time": abandon_time,
                "callerid": callerid,
                "incoming_time": incoming.start if incoming else None,
                "incoming_dstchannel": incoming.dstchannel if incoming else None,
                "outgoing_time": outgoing.start if outgoing else None,
                "outgoing_channel": outgoing.channel if outgoing else None,
            })
        return {
            "lost_and_found": results,
            "total_lost_calls": lost_calls.count(),
        }

    def get_summary_data(self, queryset):
        """Summary statistics"""
        total_calls = queryset.filter(event="ENTERQUEUE").count()
        answered_calls = queryset.filter(
            event__in=["COMPLETEAGENT", "COMPLETECALLER"]
        ).count()
        abandoned_calls = queryset.filter(event="ABANDON").count()

        # Average wait time (from data1 for ABANDON and CONNECT)
        avg_wait_time = (
            queryset.filter(
                event__in=["ABANDON", "CONNECT"], data1__isnull=False)
            .exclude(data1="")
            .aggregate(
                avg=Avg(
                    Case(
                        # Only fully numeric strings
                        When(
                            data1__regex=r'^[0-9]+$',  # avoid backslash issues
                            # force integer branch
                            then=Cast(F("data1"), output_field=IntegerField())
                        ),
                        # non-numeric -> NULL (excluded from AVG)
                        default=None,
                        output_field=IntegerField(),       # expression type for Django ORM
                    )
                )
            )["avg"] or 0
        )
        # Daily statistics
        daily_stats = (
            queryset.annotate(date=TruncDate("time"))
            .values("date")
            .annotate(
                total=Count("id"),
                answered=Count(
                    Case(
                        When(event__in=["COMPLETEAGENT", "COMPLETECALLER"], then=1))
                ),
                abandoned=Count(Case(When(event="ABANDON", then=1))),
            )
            .order_by("date")
        )

        return {
            "total_calls": total_calls,
            "answered_calls": answered_calls,
            "abandoned_calls": abandoned_calls,
            "answer_rate": (answered_calls / total_calls * 100)
            if total_calls > 0
            else 0,
            "abandon_rate": (abandoned_calls / total_calls * 100)
            if total_calls > 0
            else 0,
            "avg_wait_time": round(avg_wait_time, 2),
            "daily_stats": list(daily_stats),
        }

    def get_detailed_data(self, queryset, request=None):
        """Detailed report"""
        recent_calls = queryset.order_by("-time")
        paginated_calls = None

        if request:
            paginator = Paginator(recent_calls, 50)
            page_number = request.GET.get("page")
            paginated_calls = paginator.get_page(page_number)
        else:
            paginated_calls = recent_calls[:50]

        return {
            "calls_by_hour": list(
                queryset.annotate(hour=TruncHour("time"))
                .values("hour")
                .annotate(count=Count("id"))
                .order_by("hour")
            ),
            "events_distribution": list(
                queryset.values("event").annotate(
                    count=Count("id")).order_by("-count")
            ),
            "recent_calls": paginated_calls,
        }

    def get_agent_performance_data(self, queryset):
        """Agent performance"""
        # Agent statistics
        agents_data = (
            queryset.exclude(agent="NONE")
            .values("agent")
            .annotate(
                total_events=Count("id"),
                answered=Count(
                    Case(
                        When(event__in=["COMPLETEAGENT", "COMPLETECALLER"], then=1))
                ),
                connects=Count(Case(When(event="CONNECT", then=1))),
                ringnoanswer=Count(Case(When(event="RINGNOANSWER", then=1))),
            )
            .order_by("-answered")
        )

        # Average talk time for each agent
        for agent_data in agents_data:
            agent = agent_data["agent"]
            # Talk time stored in data2 for COMPLETEAGENT/COMPLETECALLER
            talk_time = (
                queryset.filter(
                    agent=agent,
                    event__in=["COMPLETEAGENT", "COMPLETECALLER"],
                    data2__isnull=False,
                )
                .exclude(data2="")
                .aggregate(
                    avg=Avg(
                        Case(
                            When(
                                data2__regex=r'^[0-9]+$',  # only pure digits
                                then=Cast(
                                    F("data2"), output_field=IntegerField())
                            ),
                            default=None,                  # skip non-numeric rows
                            output_field=IntegerField(),   # result type for ORM
                        )
                    )
                )["avg"] or 0
            )

            agent_data["avg_talk_time"] = round(talk_time, 2)
            agent_data["answer_rate"] = (
                agent_data["answered"] / agent_data["connects"] * 100
                if agent_data["connects"] > 0
                else 0
            )

        return {
            "agents_data": list(agents_data),
            "top_performers": list(agents_data)[:10],
        }

    def get_queue_performance_data(self, queryset):
        """Queue performance"""
        queues_data = (
            queryset.exclude(queuename="NONE")
            .values("queuename")
            .annotate(
                total_calls=Count(Case(When(event="ENTERQUEUE", then=1))),
                answered=Count(
                    Case(
                        When(event__in=["COMPLETEAGENT", "COMPLETECALLER"], then=1))
                ),
                abandoned=Count(Case(When(event="ABANDON", then=1))),
            )
            .order_by("-total_calls")
        )

        # Add calculated fields
        for queue_data in queues_data:
            total = queue_data["total_calls"]
            queue_data["answer_rate"] = (
                queue_data["answered"] / total * 100 if total > 0 else 0
            )
            queue_data["abandon_rate"] = (
                queue_data["abandoned"] / total * 100 if total > 0 else 0
            )

        return {
            "queues_data": list(queues_data),
            "queue_comparison": list(queues_data)[:10],
        }

    def export_csv(self, queryset, report_type):
        """Export data to CSV"""
        response = HttpResponse(content_type=CONTENT_TYPE_CSV)
        response["Content-Disposition"] = (
            f'attachment; filename="queuelog_report_{report_type}.csv"'
        )

        writer = csv.writer(response)

        if report_type == "detailed":
            writer.writerow(
                [
                    "Time",
                    "Call ID",
                    "Queue",
                    "Agent",
                    "Event",
                    "Data 1",
                    "Data 2",
                    "Data 3",
                ]
            )
            for record in queryset:
                writer.writerow(
                    [
                        record.time,
                        record.callid,
                        record.queuename,
                        record.agent,
                        record.event,
                        record.data1,
                        record.data2,
                        record.data3,
                    ]
                )
        else:
            # For other report types export aggregated data
            report_data = self.get_report_data(queryset, report_type)

            if report_type == "summary":
                writer.writerow(["Metric", "Value"])
                writer.writerow(
                    ["Total Calls", report_data.get("total_calls", 0)])
                writer.writerow(
                    ["Answered", report_data.get("answered_calls", 0)])
                writer.writerow(
                    ["Abandoned", report_data.get("abandoned_calls", 0)])
                writer.writerow(
                    ["Answer Rate %",
                        f"{report_data.get('answer_rate', 0):.2f}%"]
                )
                writer.writerow(
                    ["Average Wait Time (sec)", report_data.get(
                        "avg_wait_time", 0)]
                )

        return response


class AudioFileView(ReportViewPermissionMixin, View):
    def get(self, request, record_id):
        record = get_object_or_404(MonitorFilenames, id=record_id)
        file_path = record.get_audio_file_path()

        if not os.path.exists(file_path):
            raise Http404("Audio file does not exist")

        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = "audio/wav"

        response = FileResponse(
            open(file_path, "rb"),
            content_type=content_type,
            as_attachment=False,
        )
        response["Cache-Control"] = "private, max-age=3600"
        response["Content-Disposition"] = (
            f'inline; filename="{os.path.basename(file_path)}"'
        )
        return response


class MonitorReportView(ReportViewPermissionMixin, View):
    def get(self, request):
        form = MonitorFilenamesReportForm(request.GET or None)
        recordings = None

        def filter_monitor_queryset(form):
            qs = MonitorFilenames.objects.all()
            if not form.is_valid():
                return qs.none()
            data = form.cleaned_data
            if data.get("src"):
                qs = qs.filter(src__icontains=data["src"])
            if data.get("dst"):
                qs = qs.filter(dst__icontains=data["dst"])
            if data.get("created_start"):
                qs = qs.filter(created__gte=data["created_start"])
            if data.get("created_end"):
                qs = qs.filter(created__lte=data["created_end"])
            return qs.order_by("-created")

        if form.is_valid():
            recordings = filter_monitor_queryset(form)
            paginator = Paginator(recordings, 50)
            page_number = request.GET.get("page")
            recordings = paginator.get_page(page_number)

        context = {
            "form": form,
            "recordings": recordings,
        }
        return render(request, "monitor.html", context)


class CDRReportView(ReportViewPermissionMixin, View):
    def _filter_cdr_queryset(self, form):
        """Filter CDR queryset based on form data."""
        qs = CDR.objects.all()
        if not form.is_valid():
            return qs.none()
        data = form.cleaned_data
        if data.get("start_date"):
            qs = qs.filter(start__gte=data["start_date"])
        if data.get("end_date"):
            qs = qs.filter(end__lte=data["end_date"])
        if data.get("src_number"):
            qs = qs.filter(src__icontains=data["src_number"])
        if data.get("dst_number"):
            qs = qs.filter(dst__icontains=data["dst_number"])
        if data.get("src_channel"):
            qs = qs.filter(channel__icontains=data["src_channel"])
        if data.get("dst_channel"):
            qs = qs.filter(dstchannel__icontains=data["dst_channel"])
        if data.get("disposition"):
            qs = qs.filter(disposition=data["disposition"])
        if data.get("min_duration") is not None:
            qs = qs.filter(duration__gte=data["min_duration"])
        if data.get("max_duration") is not None:
            qs = qs.filter(duration__lte=data["max_duration"])
        return qs.order_by("-start")

    def _cdr_to_dict(self, cdr):
        """Convert CDR object to dictionary for JSON serialization."""
        return {
            "start": cdr.start,
            "end": cdr.end,
            "answer": cdr.answer,
            "src": cdr.src,
            "dst": cdr.dst,
            "channel": cdr.channel,
            "dstchannel": cdr.dstchannel,
            "duration": cdr.duration,
            "billsec": cdr.billsec,
            "disposition": cdr.disposition,
            "accountcode": cdr.accountcode,
            "clid": cdr.clid,
            "dcontext": cdr.dcontext,
            "lastapp": cdr.lastapp,
            "lastdata": cdr.lastdata,
            "amaflags": cdr.amaflags,
            "userfield": cdr.userfield,
            "uniqueid": cdr.uniqueid,
            "linkedid": cdr.linkedid,
            "peeraccount": cdr.peeraccount,
            "sequence": cdr.sequence,
            "audio": cdr.get_audio_url(),
        }

    def get(self, request):
        form = CDRReportForm(request.GET or None)
        cdrs = None
        statistics = None
        cdrs_json = []

        if form.is_valid():
            cdrs = self._filter_cdr_queryset(form)

            statistics = {
                "total_calls": cdrs.count(),
                "total_duration": cdrs.aggregate(Sum("duration"))["duration__sum"] or 0,
                "total_billsec": cdrs.aggregate(Sum("billsec"))["billsec__sum"] or 0,
                "answered_calls": cdrs.filter(disposition="ANSWERED").count(),
            }

            paginator = Paginator(cdrs, 50)
            page_number = request.GET.get("page")
            cdrs = paginator.get_page(page_number)
            cdrs_json = [self._cdr_to_dict(cdr) for cdr in cdrs]

        if "export" in request.GET and form.is_valid():
            export_queryset = self._filter_cdr_queryset(form)
            return self.export_cdr_csv(request, export_queryset)

        context = {
            "form": form,
            "cdrs": cdrs,
            "statistics": statistics,
            "cdrs_json": cdrs_json if cdrs else [],
        }

        return render(request, "cdr.html", context)

    @staticmethod
    def export_cdr_csv(request, queryset):
        response = HttpResponse(content_type=CONTENT_TYPE_CSV)
        response["Content-Disposition"] = 'attachment; filename="cdr_report.csv"'
        response.write("\ufeff")  # BOM for UTF-8

        writer = csv.writer(response)
        writer.writerow(
            [
                "Date/Time",
                "Source",
                "Destination",
                "Duration",
                "Billed Duration",
                "Status",
                "Channel",
            ]
        )

        for cdr in queryset:
            writer.writerow(
                [
                    cdr.start,
                    cdr.src,
                    cdr.dst,
                    cdr.duration,
                    cdr.billsec,
                    cdr.disposition,
                    cdr.channel,
                    cdr.dstchannel,
                ]
            )

        return response

class CallbackNumberReportView(ReportViewPermissionMixin, View):
    def _filter_callback_queryset(self, form):
        """Filter callback queryset based on form data."""
        qs = CallbackNumber.objects.all()
        if not form.is_valid():
            return qs.none()
        data = form.cleaned_data
        if data.get("start_date"):
            qs = qs.filter(created__gte=data["start_date"])
        if data.get("end_date"):
            qs = qs.filter(created__lte=data["end_date"])
        if data.get("src"):
            qs = qs.filter(src__icontains=data["src"])
        if data.get("dst"):
            qs = qs.filter(dst__icontains=data["dst"])
        if data.get("dial_status"):
            qs = qs.filter(dial_status=data["dial_status"])
        if data.get("service"):
            qs = qs.filter(service_id=data["service"])
        return qs.order_by("-created")

    def get(self, request):
        form = CallbackNumberReportForm(request.GET or None)
        callbacks = None
        statistics = None

        if form.is_valid():
            callbacks = self._filter_callback_queryset(form)

            statistics = {
                "total_callbacks": callbacks.count(),
                "new_callbacks": callbacks.filter(dial_status="NEW").count(),
                "answered_callbacks": callbacks.filter(dial_status="ANSWERED").count(),
                "busy_callbacks": callbacks.filter(dial_status="BUSY").count(),
                "pending_callbacks": callbacks.filter(dial_status="PENDING").count(),
            }

            paginator = Paginator(callbacks, 50)
            page_number = request.GET.get("page")
            callbacks = paginator.get_page(page_number)

        if "export" in request.GET and form.is_valid():
            export_queryset = self._filter_callback_queryset(form)
            return self.export_callback_csv(request, export_queryset)

        context = {
            "form": form,
            "callbacks": callbacks,
            "statistics": statistics,
        }

        return render(request, "callback_report.html", context)

    @staticmethod
    def export_callback_csv(request, queryset):
        response = HttpResponse(content_type=CONTENT_TYPE_CSV)
        response["Content-Disposition"] = 'attachment; filename="callback_report.csv"'
        response.write("\ufeff")  # BOM for UTF-8

        writer = csv.writer(response)
        writer.writerow(
            [
                "ID",
                "Created",
                "Source",
                "Destination",
                "Status",
                "Updated",
                "Schedule Time",
                "Service",
            ]
        )

        for cb in queryset:
            writer.writerow(
                [
                    cb.id,
                    cb.created,
                    cb.src,
                    cb.dst,
                    cb.dial_status,
                    cb.updated,
                    cb.schedule_time,
                    cb.service.name if cb.service else "",
                ]
            )

        return response