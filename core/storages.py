from django.conf import settings
from django.core.files.storage import FileSystemStorage


class MOHFileSystemStorage(FileSystemStorage):
    """
    Custom FileSystemStorage for MusicOnHold files.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if settings.DEVMODE == settings.DEVMODE_PRODUCTION:
            self.location = '/var/lib/asterisk/moh/'
        else:
            self.location = 'moh/'

class SoundsFileSystemStorage(FileSystemStorage):
    """
    Custom FileSystemStorage for sound files.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if settings.DEVMODE == settings.DEVMODE_PRODUCTION:
            self.location = '/var/lib/asterisk/sounds/'
        else:
            self.location = 'sounds/'


