import datetime
import json
import logging
import threading

import django.contrib.auth.views as django_auth_views
import redis
from asterisk.ami import AMIClient, SimpleAction
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.reports.models import CDR
from core.models import Blacklist, Contact, Queue, RoutingRecord, SIPPeer, SIPUser

logger = logging.getLogger(__name__)


class LoginView(django_auth_views.LoginView):
    login_url = "/login/"
    template_name = "login.html"
    success_url = reverse_lazy("homepage")
    redirect_authenticated_user = True


class LogoutView(django_auth_views.LogoutView):
    template_name = "logout.html"


class NotFoundView(TemplateView):
    template_name = "404.html"


class HomepageView(LoginRequiredMixin, TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["stats"] = {
            "sip_users": SIPUser.objects.count(),
            "sip_peers": SIPPeer.objects.count(),
            "queues": Queue.objects.count(),
            "routing_records": RoutingRecord.objects.count(),
            "contacts": Contact.objects.count(),
            "blocklist": Blacklist.objects.count(),
        }
        since = timezone.now().date() - datetime.timedelta(days=13)
        cdr_rows = (
            CDR.objects.filter(start__date__gte=since)
            .values("start__date", "disposition")
            .annotate(count=Count("id"))
            .order_by("start__date")
        )
        ctx["cdr_chart_data"] = [
            {
                "date": str(row["start__date"]),
                "disposition": row["disposition"],
                "count": row["count"],
            }
            for row in cdr_rows
        ]
        return ctx


class HomepageStatusView(LoginRequiredMixin, View):
    def get(self, request):
        result = {"asterisk": None, "active_calls": 0, "queues": []}

        try:
            r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            channels_raw = r.get("asterisk:channels:all")
            if channels_raw:
                channels = json.loads(channels_raw)
                bridges = {
                    v.get("bridge_id")
                    for v in channels.values()
                    if v.get("bridge_id")
                }
                result["active_calls"] = len(bridges)

            queue_keys = list(r.scan_iter("asterisk:queue:*"))
            if queue_keys:
                raw_values = r.mget(queue_keys)
                for key, raw in zip(queue_keys, raw_values):
                    if not raw:
                        continue
                    q = json.loads(raw)
                    members = q.get("members", {})
                    available = sum(
                        1
                        for m in members.values()
                        if m.get("status") == "1" and not m.get("paused")
                    )
                    calls = q.get("calls", {})
                    result["queues"].append({
                        "name": key.split(":")[-1],
                        "callers": len(calls),
                        "available_members": available,
                        "total_members": len(members),
                    })
        except Exception as e:
            logger.warning("Redis unavailable in HomepageStatusView: %s", e)

        ami_result = {}
        done = threading.Event()

        def on_login(response, **kwargs):
            client.send_action(SimpleAction("CoreStatus"), callback=on_status)

        def on_status(response, **kwargs):
            for k in ("AsteriskVersion", "CoreUptime", "CoreReloadTime", "CoreCurrentCalls"):
                ami_result[k] = response.keys.get(k, "")
            try:
                client.logoff()
            except Exception:
                pass
            done.set()

        try:
            client = AMIClient(
                address=settings.ASTERISK_MANAGER_HOST,
                port=int(settings.ASTERISK_MANAGER_PORT),
            )
            client.login(
                username=settings.ASTERISK_MANAGER_USERNAME,
                secret=settings.ASTERISK_MANAGER_SECRET,
                callback=on_login,
            )
            done.wait(timeout=3)
            if ami_result:
                result["asterisk"] = ami_result
        except Exception as e:
            logger.warning("AMI unavailable in HomepageStatusView: %s", e)

        return JsonResponse(result)


class ReportsView(LoginRequiredMixin, TemplateView):
    template_name = "reports.html"
