from django.shortcuts import redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from .models import PhoneDevice


@staff_member_required
def apply_all_configurations(request):
    """Apply configurations to all phone devices"""
    if request.method == "POST":
        devices = PhoneDevice.objects.all()
        success_count = 0

        for device in devices:
            if device.mac_address and device.telephone_type:
                # Simulate configuration application
                success_count += 1

        messages.success(request, f"Applied configurations to {success_count} devices.")
        return redirect("admin:provision_phonedevice_changelist")

    return redirect("admin:provision_phonedevice_changelist")
