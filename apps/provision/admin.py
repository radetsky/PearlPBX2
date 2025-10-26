from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.urls import path, reverse
from django.utils.html import format_html

from apps.provision.models import PhoneDevice
from apps.provision.forms import PhoneDeviceForm
from apps.provision.provisioning_manager import PhoneProvisioningManager


@admin.register(PhoneDevice)
class PhoneDeviceAdmin(admin.ModelAdmin):
    form = PhoneDeviceForm
    list_display = ['mac_address', 'telephone_type', 'get_sip_user_username', 'get_configuration_status', 'created_at', 'modified_at']
    list_filter = ['telephone_type', 'created_at', 'modified_at']
    search_fields = ['mac_address', 'sip_user__username', 'sip_user__name']
    readonly_fields = ['created_at', 'modified_at', 'created_by', 'modified_by']

    fieldsets = (
        ('Device Information', {
            'fields': ('telephone_type', 'mac_address', 'sip_user')
        }),
        ('Audit Information', {
            'fields': ('created_at', 'created_by', 'modified_at', 'modified_by'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='SIP User', ordering='sip_user__username')
    def get_sip_user_username(self, obj):
        """Display SIP user username instead of object representation"""
        if obj.sip_user:
            return obj.sip_user.username
        return '-'

    @admin.display(description='Config Status')
    def get_configuration_status(self, obj):
        """Display configuration status of the device"""
        # TODO: Implement actual status checking logic
        # This could check if config file exists, last sync time, etc.

        if not obj.mac_address or not obj.telephone_type:
            return format_html('<span style="color: red;">❌ Incomplete</span>')
        elif obj.sip_user:
            return format_html('<span style="color: green;">✅ Ready</span>')
        else:
            return format_html('<span style="color: orange;">⚠️ No SIP User</span>')

    actions = ['apply_configurations_to_phones']

    def get_urls(self):
        """Add custom URL for applying configurations to all devices"""
        urls = super().get_urls()
        custom_urls = [
            path('apply-all-configurations/',
                 self.admin_site.admin_view(self.apply_all_configurations_view),
                 name='provision_phonedevice_apply_all'),
        ]
        return custom_urls + urls

    def apply_all_configurations_view(self, request):
        """Apply configurations to all phone devices"""
        if request.method == 'POST':
            all_devices = PhoneDevice.objects.all()
            return self.apply_configurations_to_phones(request, all_devices)

        # Redirect back to changelist
        from django.shortcuts import redirect
        return redirect('admin:provision_phonedevice_changelist')

    @admin.action(description='Apply configurations to selected phones')
    def apply_configurations_to_phones(self, request, queryset):
        """Apply configurations to selected phone devices"""
        manager = PhoneProvisioningManager(settings.TFTP_DIR)
        results = {'successful': [], 'failed': []}

        for device in queryset:
            result = manager.provision_device(device)
            if result['success']:
                results['successful'].append(result)
            else:
                results['failed'].append(result)

        # Show results to user
        success_count = len(results['successful'])
        if success_count > 0:
            successful_devices = [r['device_mac'] for r in results['successful']]
            messages.success(
                request,
                f'Successfully generated configurations for {success_count} device(s): {", ".join(successful_devices)}'
            )

        if results['failed']:
            failed_messages = [f"{r['device_mac']}: {r['error']}" for r in results['failed']]
            messages.error(
                request,
                f'Failed to generate configurations: {"; ".join(failed_messages)}'
            )

    def save_model(self, request, obj, form, change):
        if not change:  # Creating new object
            obj.created_by = request.user
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)
