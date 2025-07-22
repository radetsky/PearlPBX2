import django.contrib.auth.views as django_auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import TemplateView


class LoginView(django_auth_views.LoginView):
    login_url = "/login/"
    template_name = "login.html"
    success_url = reverse_lazy("homepage")
    redirect_authenticated_user = True


class LogoutView(django_auth_views.LogoutView):
    template_name = "logout.html"


class NotFoundView(TemplateView):
    template_name = "404.html"


class HomepageView(
    LoginRequiredMixin,
    TemplateView,
):
    template_name = "home.html"


class ReportsView(
    LoginRequiredMixin,
    TemplateView,
):
    template_name = "reports.html"
