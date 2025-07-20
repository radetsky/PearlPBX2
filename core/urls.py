from django.urls import path

from core.views import base_views

urlpatterns = [
    path('login/', base_views.LoginView.as_view(), name='login'),
    path('logout/', base_views.LogoutView.as_view(), name='logout'),
    path('', base_views.HomepageDispatchView.as_view(), name='homepage'),
]
