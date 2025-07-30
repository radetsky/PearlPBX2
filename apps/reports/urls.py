from django.urls import path
from . import views

urlpatterns = [
    path("cdr/", views.cdr_report_view, name="cdr_report"),
    path("monitor/", views.monitor_report_view, name="monitor_report"),
]
