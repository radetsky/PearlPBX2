from os import makedirs
import tarfile
import datetime

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import render, redirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView
from django.db import transaction
from django.db.models import Max, OuterRef, Subquery

from core.ami import AsteriskManagementInterface
from core.conf import (
    make_pjsip_conf,
    make_queues_conf,
    make_queuerules_conf,
    make_extensions_ael,
    make_manager_conf,
    make_musiconhold_conf,
    write_tls_cert_files,
)

from core.models import ConfigurationFile, SystemConfiguration


class MyAdminSite(admin.AdminSite):
    site_header = _("PBX Setup")
    index_title = _("PBX Administration")


class ApplyChangesForm(forms.Form):
    commit_changes = forms.BooleanField(
        required=True, label="Apply Changes", initial=False
    )


class ApplyChangesView(UserPassesTestMixin, TemplateView):
    template_name = "admin/apply.html"

    def test_func(self):
        return self.request.user.is_superuser

    def _crlf_to_lf(self, content: str) -> str:
        """
        Convert CRLF line endings to LF.
        This is necessary because Asterisk expects LF line endings in its configuration files.
        """
        return content.replace("\r\n", "\n").replace("\r", "")

    def _build_cfgfiles(self):
        """Build dictionary of configuration files to be generated."""
        cfgfiles = {}
        cfgfiles["/etc/asterisk/extensions.ael"] = make_extensions_ael()
        cfgfiles["/etc/asterisk/pjsip.conf"] = make_pjsip_conf()
        cfgfiles["/etc/asterisk/queues.conf"] = make_queues_conf()
        cfgfiles["/etc/asterisk/queuerules.conf"] = make_queuerules_conf()
        cfgfiles["/etc/asterisk/manager.conf"] = make_manager_conf()
        cfgfiles["/etc/asterisk/musiconhold.conf"] = make_musiconhold_conf()
        for cfg in self.get_latest_configuration_files():
            if cfg.path not in cfgfiles:
                cfgfiles[cfg.path] = cfg.content

        for path, content in cfgfiles.items():
            cfgfiles[path] = self._crlf_to_lf(content)

        return dict(sorted(cfgfiles.items()))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = ApplyChangesForm()
        context["cfgfiles"] = self._build_cfgfiles()
        return context

    def post(self, request, *args, **kwargs):
        form = ApplyChangesForm(request.POST)
        cfgfiles = self._build_cfgfiles()

        if form.is_valid():
            try:
                self.apply_changes(cfgfiles)
                if settings.DEVMODE != settings.DEVMODE_WITHOUT_ASTERISK:
                    ami = AsteriskManagementInterface()
                    if request.POST.get("reload_type") == "soft":
                        ami.soft_reload()
                    else:
                        ami.restart()
                messages.success(request, _("Configurations files saved successfully."))

                return redirect("admin:index")
            except Exception as e:
                messages.error(
                    request, _("An error occurred: %(error)s") % {"error": str(e)}
                )

        context = self.get_context_data(**kwargs)
        context["cfgfiles"] = cfgfiles
        context["form"] = form
        return render(request, self.template_name, context)

    def get_latest_configuration_files(self):
        # First, annotate each ConfigurationFile with the latest version for that name
        latest_versions = ConfigurationFile.objects.values("name").annotate(
            latest_version=Max("version")
        )
        # Then, get the corresponding records with the latest version
        latest_configuration_files = ConfigurationFile.objects.filter(
            version=Subquery(
                latest_versions.filter(name=OuterRef("name")).values("latest_version")[
                    :1
                ]
            )
        )
        return latest_configuration_files

    @transaction.atomic
    def apply_changes(self, cfgfiles):
        created_configuration_files = []
        for path, content in cfgfiles.items():
            cfg_object = self.create_configuration_file(
                path.split("/")[-1], path, content
            )
            created_configuration_files.append(cfg_object)

        system_configuration = SystemConfiguration.objects.create()
        system_configuration.configuration_files.set(created_configuration_files)
        self.backup_dir()
        write_tls_cert_files()
        self.apply_to_fs(system_configuration)

    def apply_to_fs(self, system_configuration):
        # try to mkdir ASTERISK_ROOT_DIR
        try:
            makedirs(settings.ASTERISK_ROOT_DIR, exist_ok=True)
        except FileExistsError:
            pass

        for cfg in system_configuration.configuration_files.all():
            directory = settings.ASTERISK_ROOT_DIR + "/".join(cfg.path.split("/")[:-1])
            try:
                makedirs(directory, exist_ok=True)
            except FileExistsError:
                pass

            path = settings.ASTERISK_ROOT_DIR + cfg.path
            with open(path, "w") as f:
                f.write(cfg.content)

    def backup_dir(self):
        # check if exists ASTERISK_BACKUP_DIR
        try:
            makedirs(settings.ASTERISK_BACKUP_DIR)
        except FileExistsError:
            pass

        # archive all files from ASTERISK_ROOT_DIR to ASTERISK_BACKUP_DIR/asterisk-<timestamp>.tar.gz
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        backup_file = f"{settings.ASTERISK_BACKUP_DIR}/asterisk-{timestamp}.tar.gz"
        with tarfile.open(backup_file, "w:gz") as tar:
            tar.add(settings.ASTERISK_ROOT_DIR + settings.ASTERISK_CONFIG_DIR)

    def create_configuration_file(self, name, path, content):
        # fetch previous versions of the file
        prev_cfg = (
            ConfigurationFile.objects.filter(path=path).order_by("-version").first()
        )
        if prev_cfg:
            # Compare the content of the previous version with the new content
            if prev_cfg.content == content:
                # If the content is the same, return the previous version
                return prev_cfg

            version = prev_cfg.version + 1
        else:
            version = 1

        return ConfigurationFile.objects.create(
            name=name, content=content, path=path, version=version
        )
