from django import forms
from django.contrib import admin
from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from core.conf import make_pjsip_conf, make_queues_conf, make_extensions_ael


class MyAdminSite(admin.AdminSite):
    site_header = "PBX Setup"
    index_title = "PBX Administration"


class ApplyChangesForm(forms.Form):
    pass

class ApplyChangesView(TemplateView):
    template_name = "admin/apply.html"

    # display the form on the page
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = ApplyChangesForm()
        return context

    def post(self, request, *args, **kwargs):
        form = ApplyChangesForm(request.POST)
        cfgfiles = {} # dictionary of config files to be written
        cfgfiles['/etc/asterisk/extensions.ael'] = make_extensions_ael()
        cfgfiles['/etc/asterisk/pjsip.conf'] = make_pjsip_conf()
        cfgfiles['/etc/asterisk/queues.conf'] = make_queues_conf()

        context = {'cfgfiles': cfgfiles, 'form': form}

        return render(request, self.template_name, context)
