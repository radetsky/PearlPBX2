from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.operator_panel, name='operator_panel'),

    # Черги
    path('api/queues/', views.get_all_queues, name='get_all_queues'),
    path('api/queues/<str:queue_name>/', views.get_queue_state, name='get_queue_state'),

    # Канали
    path('api/channels/', views.get_all_channels, name='get_all_channels'),
    path('api/channels/<path:channel_name>/', views.get_channel, name='get_channel'),
    path('api/channels/type/<str:channel_type>/', views.get_channels_by_type, name='get_channels_by_type'),
    path('api/calls/active/', views.get_active_calls, name='get_active_calls'),
]
