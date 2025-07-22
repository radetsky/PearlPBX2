from django.urls import path
from . import views

urlpatterns = [
    path("cdr/", views.cdr_report_view, name="cdr_report"),
]
