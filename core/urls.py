from django.urls import path

from core.views import base_views

urlpatterns = [
    path("login/", base_views.LoginView.as_view(), name="login"),
    path("accounts/login/", base_views.LoginView.as_view(), name="login"),
    path("logout/", base_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", base_views.HomepageView.as_view(), name="homepage"),
    path("reports/", base_views.ReportsView.as_view(), name="reports"),
    path("", base_views.HomepageView.as_view(), name="home"),
]
