import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class MOHFileSystemStorage(FileSystemStorage):
    """
    Custom FileSystemStorage for MusicOnHold files.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if settings.DEVMODE == settings.DEVMODE_WITHOUT_ASTERISK:
            self.location = "moh/"
            self.base_url = "/moh/"
        else:
            self.location = "/var/lib/asterisk/moh/"
            self.base_url = "/moh/"

    def save(self, name, content, max_length=None):
        """Ensure directory exists before saving the file."""
        full_path = os.path.join(self.location, name)
        dir_path = os.path.dirname(full_path)
        try:
            os.makedirs(dir_path, exist_ok=True)
        except PermissionError:
            pass  # Skip if no permissions, let Django handle the error on actual save
        return super().save(name, content, max_length)


class SoundsFileSystemStorage(FileSystemStorage):
    """
    Custom FileSystemStorage for sound files.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if settings.DEVMODE == settings.DEVMODE_WITHOUT_ASTERISK:
            self.location = "sounds/"
        else:
            self.location = "/var/lib/asterisk/sounds/"

