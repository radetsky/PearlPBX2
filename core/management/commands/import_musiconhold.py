import os
import re
from django.core.management.base import BaseCommand, CommandError
from core.models import MusicOnHold, MusicOnHoldModes, MusicOnHoldSortModes


class Command(BaseCommand):
    help = "Import MusicOnHold classes from an existing Asterisk musiconhold.conf file."

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path", type=str, help="Path to the musiconhold.conf file to import"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be imported without making changes",
        )

    def handle(self, *args, **kwargs):
        file_path = kwargs["file_path"]
        dry_run = kwargs["dry_run"]

        if not os.path.exists(file_path):
            raise CommandError(f"File {file_path} does not exist.")

        with open(file_path, "r") as f:
            content = f.read()

        sections = self.parse_musiconhold_conf(content)

        imported = []
        skipped = []
        errors = []

        for section_name, settings in sections.items():
            if section_name.lower() == "general":
                skipped.append((section_name, "general section ignored"))
                continue

            result = self.process_section(section_name, settings, dry_run)
            if result["status"] == "imported":
                imported.append(result)
            elif result["status"] == "skipped":
                skipped.append((section_name, result["reason"]))
            elif result["status"] == "error":
                errors.append((section_name, result["reason"]))

        self.print_results(imported, skipped, errors, dry_run)

    def parse_musiconhold_conf(self, content):
        """Parse INI-style musiconhold.conf file and return sections dict."""
        sections = {}
        current_section = None
        section_pattern = re.compile(r"^\[([^\]]+)\]")
        keyvalue_pattern = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.*)$")

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(";") or line.startswith("#"):
                continue

            section_match = section_pattern.match(line)
            if section_match:
                current_section = section_match.group(1)
                sections[current_section] = {}
                continue

            if current_section is not None:
                kv_match = keyvalue_pattern.match(line)
                if kv_match:
                    key = kv_match.group(1)
                    value = kv_match.group(2).strip()
                    sections[current_section][key] = value

        return sections

    def normalize_directory(self, directory):
        """Strip common prefixes from directory path."""
        if not directory:
            return ""

        prefixes_to_strip = [
            "/var/lib/asterisk/moh/",
            "moh/",
        ]

        for prefix in prefixes_to_strip:
            if directory.startswith(prefix):
                directory = directory[len(prefix) :]
                break

        return directory.rstrip("/")

    def validate_section(self, name, settings):
        """Validate section settings and return error message or None."""
        if len(name) > 32:
            return f"name too long ({len(name)} > 32 chars)"

        mode = settings.get("mode", "files")
        valid_modes = [choice[0] for choice in MusicOnHoldModes.choices]

        if mode not in valid_modes:
            return f"unsupported mode '{mode}'"

        directory = self.normalize_directory(settings.get("directory", ""))
        if len(directory) > 64:
            return f"directory too long ({len(directory)} > 64 chars)"

        sort_mode = settings.get("sort", "random")
        valid_sorts = [choice[0] for choice in MusicOnHoldSortModes.choices]
        if sort_mode not in valid_sorts:
            return f"unsupported sort mode '{sort_mode}'"

        return None

    def process_section(self, name, settings, dry_run):
        """Process a single MOH section and return result dict."""
        validation_error = self.validate_section(name, settings)
        if validation_error:
            return {"status": "error", "reason": validation_error}

        if MusicOnHold.objects.filter(name=name).exists():
            return {"status": "skipped", "reason": "already exists in database"}

        mode = settings.get("mode", "files")
        directory = self.normalize_directory(settings.get("directory", ""))
        sort_mode = settings.get("sort", "random")

        if not dry_run:
            MusicOnHold.objects.create(
                name=name,
                mode=mode,
                directory=directory,
                sort=sort_mode,
            )

        return {
            "status": "imported",
            "name": name,
            "mode": mode,
            "directory": directory,
            "sort": sort_mode,
        }

    def print_results(self, imported, skipped, errors, dry_run):
        """Print formatted results."""
        if dry_run:
            self.stdout.write(
                self.style.WARNING("\n=== DRY RUN - No changes made ===\n")
            )

        if imported:
            self.stdout.write(self.style.SUCCESS("Imported:"))
            for item in imported:
                self.stdout.write(
                    f"  [{item['name']}] mode={item['mode']}, "
                    f"directory={item['directory']}, sort={item['sort']}"
                )
            self.stdout.write("")

        if skipped:
            self.stdout.write(self.style.WARNING("Skipped:"))
            for name, reason in skipped:
                self.stdout.write(f"  [{name}] - {reason}")
            self.stdout.write("")

        if errors:
            self.stdout.write(self.style.ERROR("Errors:"))
            for name, reason in errors:
                self.stdout.write(f"  [{name}] - {reason}")
            self.stdout.write("")

        summary = f"Summary: Imported {len(imported)}, skipped {len(skipped)}, errors {len(errors)}"
        if dry_run:
            self.stdout.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
