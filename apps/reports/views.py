import csv

from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import HttpResponse

from apps.reports.models import CDR
from apps.reports.forms import CDRReportForm, MonitorFilenamesReportForm
from core.models import MonitorFilenames


def monitor_report_view(request):
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


def cdr_report_view(request):
    form = CDRReportForm(request.GET or None)
    cdrs = None
    statistics = None

    def filter_cdr_queryset(form):
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

    cdrs_json = []
    if form.is_valid():
        cdrs = filter_cdr_queryset(form)

        statistics = {
            "total_calls": cdrs.count(),
            "total_duration": cdrs.aggregate(Sum("duration"))["duration__sum"] or 0,
            "total_billsec": cdrs.aggregate(Sum("billsec"))["billsec__sum"] or 0,
            "answered_calls": cdrs.filter(disposition="ANSWERED").count(),
        }

        paginator = Paginator(cdrs, 50)
        page_number = request.GET.get("page")
        cdrs = paginator.get_page(page_number)
        cdrs_json = [
            {
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
            }
            for cdr in cdrs
        ]

    if "export" in request.GET and form.is_valid():
        export_queryset = filter_cdr_queryset(form)
        return export_cdr_csv(request, export_queryset)

    context = {
        "form": form,
        "cdrs": cdrs,
        "statistics": statistics,
        "cdrs_json": cdrs_json if cdrs else [],
    }

    return render(request, "cdr.html", context)


def export_cdr_csv(request, queryset):
    response = HttpResponse(content_type="text/csv")
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
