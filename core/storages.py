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

