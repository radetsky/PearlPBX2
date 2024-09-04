from django import forms
from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from core.conf import make_pjsip_conf, make_queues_conf, make_extensions_ael
from core.models import ConfigurationFile, SystemConfiguration
from django.db import transaction


class MyAdminSite(admin.AdminSite):
    site_header = "PBX Setup"
    index_title = "PBX Administration"


class ApplyChangesForm(forms.Form):
    commit_changes = forms.BooleanField(
        required=False, label="Apply Changes", initial=False)


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
        if form.is_valid():
            if form.cleaned_data['commit_changes']:
                try:
                    self.apply_changes(cfgfiles)
                    messages.success(
                        request, "Configurations files saved successfully.")
                    return redirect('apply_changes')
                except Exception as e:
                    messages.error(request, f"An error occurred: {str(e)}")
            else:
                # Just preview, don't save
                messages.info(
                    request, "This is a preview. The changes have not been applied yet.")

        context = self.get_context_data(**kwargs)
        context['cfgfiles'] = cfgfiles
        context['form'] = form
        return render(request, self.template_name, context)

    @transaction.atomic
    def apply_changes(self, cfgfiles):
        created_configuration_files = []
        for path, content in cfgfiles.items():
            cfg_object = self.create_configuration_file(path.split('/')[-1], path, content)
            created_configuration_files.append(cfg_object)

        system_configuration = SystemConfiguration.objects.create()
        system_configuration.configuration_files.set(created_configuration_files)


    def create_configuration_file(self, name, path, content):
        version = ConfigurationFile.objects.filter(name=name).count() + 1
        return ConfigurationFile.objects.create(name=name, content=content, path=path, version=version)