import os
from django.core.management.base import BaseCommand, CommandError
from core.models import SoundFile
from core.storages import SoundsFileSystemStorage


class Command(BaseCommand):
    help = "Import sound files from filesystem into the database."

    VALID_EXTENSIONS = SoundFile.VALID_EXTENSIONS

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default=None,
            help="Path to scan for sound files (default: /var/lib/asterisk/sounds/)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be imported without making changes",
        )

    def handle(self, *args, **kwargs):
        dry_run = kwargs["dry_run"]
        path = kwargs["path"]

        if path is None:
            storage = SoundsFileSystemStorage()
            path = storage.location

        if not os.path.exists(path):
            raise CommandError(f"Directory {path} does not exist.")

        if not os.path.isdir(path):
            raise CommandError(f"{path} is not a directory.")

        sound_files = self.scan_directory(path)

        imported = []
        skipped = []
        errors = []

        for file_info in sound_files:
            result = self.process_file(file_info, dry_run)
            if result["status"] == "imported":
                imported.append(result)
            elif result["status"] == "skipped":
                skipped.append((file_info["relative_path"], result["reason"]))
            elif result["status"] == "error":
                errors.append((file_info["relative_path"], result["reason"]))

        self.print_results(imported, skipped, errors, dry_run)

    def scan_directory(self, base_path):
        """Scan directory for sound files and return list of file info dicts."""
        sound_files = []

        for root, _dirs, files in os.walk(base_path):
            for filename in files:
                ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if ext not in self.VALID_EXTENSIONS:
                    continue

                full_path = os.path.join(root, filename)
                relative_path = os.path.relpath(full_path, base_path)
                parts = relative_path.split(os.sep)

                if len(parts) >= 2:
                    language = parts[0]
                    name_with_ext = parts[-1]
                else:
                    language = ""
                    name_with_ext = parts[0]

                name = name_with_ext.rsplit(".", 1)[0]

                sound_files.append({
                    "full_path": full_path,
                    "relative_path": relative_path,
                    "language": language,
                    "name": name,
                    "filename": filename,
                })

        return sound_files

    def validate_file(self, file_info):
        """Validate file info and return error message or None."""
        name = file_info["name"]
        language = file_info["language"]

        if len(name) > 64:
            return f"name too long ({len(name)} > 64 chars)"

        if len(language) > 3:
            return f"language too long ({len(language)} > 3 chars)"

        return None

    def process_file(self, file_info, dry_run):
        """Process a single sound file and return result dict."""
        validation_error = self.validate_file(file_info)
        if validation_error:
            return {"status": "error", "reason": validation_error}

        name = file_info["name"]
        language = file_info["language"]
        relative_path = file_info["relative_path"]

        existing = SoundFile.objects.filter(name=name, language=language).first()
        if existing:
            return {"status": "skipped", "reason": "already exists in database"}

        if not dry_run:
            SoundFile.objects.create(
                name=name,
                language=language,
                file=relative_path,
            )

        return {
            "status": "imported",
            "name": name,
            "language": language,
            "file": relative_path,
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
                    f"  [{item['language']}] {item['name']} -> {item['file']}"
                )
            self.stdout.write("")

        if skipped:
            self.stdout.write(self.style.WARNING("Skipped:"))
            for path, reason in skipped:
                self.stdout.write(f"  {path} - {reason}")
            self.stdout.write("")

        if errors:
            self.stdout.write(self.style.ERROR("Errors:"))
            for path, reason in errors:
                self.stdout.write(f"  {path} - {reason}")
            self.stdout.write("")

        summary = f"Summary: Imported {len(imported)}, skipped {len(skipped)}, errors {len(errors)}"
        if dry_run:
            self.stdout.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
