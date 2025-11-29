from django.contrib import admin

from apps.callback.models import CallbackNumber, CallbackService

class CallbackNumberAdmin(admin.ModelAdmin):
    list_display = ['id', 'src', 'dst', 'dial_status', 'schedule_time', 'service']
    list_filter = ['dial_status', 'service']
    search_fields = ['src', 'dst']
    readonly_fields = ['created', 'updated']

admin.site.register(CallbackNumber, CallbackNumberAdmin)
admin.site.register(CallbackService)