from django.contrib import admin
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.urls import path, reverse
from django.utils.html import format_html

from apps.provision.models import PhoneDevice
from apps.provision.forms import PhoneDeviceForm


@admin.register(PhoneDevice)
class PhoneDeviceAdmin(admin.ModelAdmin):
    form = PhoneDeviceForm
    list_display = ['mac_address', 'telephone_type', 'get_sip_user_username', 'created_at', 'modified_at']
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
        # TODO: Implement actual configuration application logic here
        # For now, we'll just simulate the process
        success_count = 0
        failed_devices = []
        
        for device in queryset:
            try:
                # Simulate configuration application
                # Here you would implement the actual provisioning logic
                # For example: generate config files, send to device, etc.
                
                # Mock implementation - check if device has required data
                if device.mac_address and device.telephone_type:
                    # Simulate successful configuration
                    success_count += 1
                    # TODO: Add actual provisioning logic here:
                    # - Generate device-specific configuration file
                    # - Upload to TFTP/HTTP server
                    # - Send reboot command to device
                    # - Log the operation
                else:
                    failed_devices.append(device.mac_address or f"Device {device.id}")
                    
            except Exception as e:
                failed_devices.append(f"{device.mac_address}: {str(e)}")
        
        # Show results to user
        if success_count > 0:
            messages.success(
                request, 
                f'Successfully applied configurations to {success_count} device(s).'
            )
        
        if failed_devices:
            messages.warning(
                request,
                f'Failed to apply configurations to: {", ".join(failed_devices)}'
            )
    
    def save_model(self, request, obj, form, change):
        if not change:  # Creating new object
            obj.created_by = request.user
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)
