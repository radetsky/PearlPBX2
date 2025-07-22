from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.http import HttpResponse
import csv
from .models import CDR
from .forms import CDRReportForm


def cdr_report_view(request):
    form = CDRReportForm(request.GET or None)
    cdrs = None
    statistics = None

    if form.is_valid():
        cdrs = CDR.objects.all()

        start_date = form.cleaned_data.get('start_date')
        end_date = form.cleaned_data.get('end_date')
        if start_date:
            cdrs = cdrs.filter(calldate__gte=start_date)
        if end_date:
            cdrs = cdrs.filter(calldate__lte=end_date)

        src_number = form.cleaned_data.get('src_number')
        dst_number = form.cleaned_data.get('dst_number')
        if src_number:
            cdrs = cdrs.filter(src__icontains=src_number)
        if dst_number:
            cdrs = cdrs.filter(dst__icontains=dst_number)
        src_channel = form.cleaned_data.get('src_channel')
        if src_channel:
            cdrs = cdrs.filter(channel__icontains=src_channel)
        dst_channel = form.cleaned_data.get('dst_channel')
        if dst_channel:
            cdrs = cdrs.filter(dstchannel__icontains=dst_channel)

        disposition = form.cleaned_data.get('disposition')
        if disposition:
            cdrs = cdrs.filter(disposition=disposition)

        min_duration = form.cleaned_data.get('min_duration')
        if min_duration is not None:
            cdrs = cdrs.filter(duration__gte=min_duration)

        cdrs = cdrs.order_by('-calldate')

        statistics = {
            'total_calls': cdrs.count(),
            'total_duration': cdrs.aggregate(Sum('duration'))['duration__sum'] or 0,
            'total_billsec': cdrs.aggregate(Sum('billsec'))['billsec__sum'] or 0,
            'answered_calls': cdrs.filter(disposition='ANSWERED').count(),
        }

        paginator = Paginator(cdrs, 50)  # 50 записів на сторінку
        page_number = request.GET.get('page')
        cdrs = paginator.get_page(page_number)

    if 'export' in request.GET and cdrs:
        return export_cdr_csv(request, CDR.objects.filter(
            **{k: v for k, v in form.cleaned_data.items() if v}
        ))

    context = {
        'form': form,
        'cdrs': cdrs,
        'statistics': statistics,
    }

    return render(request, 'cdr.html', context)


def export_cdr_csv(request, queryset):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="cdr_report.csv"'
    response.write('\ufeff')  # BOM for UTF-8

    writer = csv.writer(response)
    writer.writerow([
        'Дата/Час', 'Відправник', 'Отримувач', 'Тривалість',
        'Оплачена тривалість', 'Статус', 'Канал'
    ])

    for cdr in queryset:
        writer.writerow([
            cdr.calldate,
            cdr.src,
            cdr.dst,
            cdr.duration,
            cdr.billsec,
            cdr.disposition,
            cdr.channel,
        ])

    return response
