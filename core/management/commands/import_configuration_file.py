import os
from django.core.management.base import BaseCommand, CommandError
from core.models import ConfigurationFile


class Command(BaseCommand):
    help = "Import a configuration file and store it in the database, creating a new version if the file already exists."

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path", type=str, help="Path to the file to be imported"
        )
        parser.add_argument(
            "config_path", type=str, help="Path in the Asterisk configuration"
        )

    def handle(self, *args, **kwargs):
        file_path = kwargs["file_path"]
        config_path = kwargs["config_path"]

        if not os.path.exists(file_path):
            raise CommandError(f"File {file_path} does not exist.")

        with open(file_path, "r") as file:
            content = file.read()

        file_name = os.path.basename(file_path)
        latest_file = (
            ConfigurationFile.objects.filter(name=file_name, path=config_path)
            .order_by("-version")
            .first()
        )

        if latest_file:
            new_version = latest_file.version + 1
        else:
            new_version = 1

        new_config_file = ConfigurationFile(
            name=file_name,
            description=f"Imported from {file_path}",
            content=content,
            path=config_path,
            version=new_version,
        )
        new_config_file.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully imported {file_path} as version {new_version} of {file_name}"
            )
        )
