import environ

from django.utils.translation import gettext_lazy as _
from pathlib import Path

env = environ.Env()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

VERSION = (BASE_DIR / "VERSION").read_text().strip()

DEVMODE_WITHOUT_ASTERISK = "without_asterisk_on_localhost"
DEVMODE_DEVELOPMENT = "Development"  # Ubuntu on VPS
DEVMODE_PRODUCTION = "Production"  # Production server
DEVMODE_STAGING = "Staging"  # Staging server
DEVMODE = env.str("DEVMODE", "Development")

DEBUG = False
SECRET_KEY = env.str(
    "DJANGO_SECRET_KEY", ""
)  # python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'

if DEVMODE not in (DEVMODE_PRODUCTION, DEVMODE_STAGING):
    # SECURITY WARNING: don't run with debug turned on in production!
    DEBUG = True
    # SECURITY WARNING: keep the secret key used in production secret!
    SECRET_KEY = "django-insecure-dom_8=vl0m@(cfoacp393+*&3s#jrtl#rt45o6=k3#7%llprq^"


ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1"])

# Application definition

INSTALLED_APPS = [
    # 'django.contrib.admin',
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "core",
    "apps.api",
    "apps.callback",
    "apps.provision",
    "apps.reports",
    "apps.dashboard",
    "apps.lists",
    "pbx.apps.MyAdminConfig",  # replaces 'django.contrib.admin'
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "pbx.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": ["templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.template_config_context_processor",
                "core.context_processors.header_menu_context_processor",
            ],
        },
    },
]

WSGI_APPLICATION = "pbx.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env.str("DB_NAME", "rad"),
        "USER": env.str("DB_USER", "rad"),
        "PASSWORD": env.str("DB_PASS", "rad"),
        "HOST": env.str("DB_HOST", "localhost"),
        "PORT": env.int("DB_PORT", 5432),
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "uk"

LANGUAGES = [
    ("uk", _("Ukrainian")),
    ("en", _("English")),
    ("es", _("Spanish")),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

TIME_ZONE = "Europe/Kyiv"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"  # For collectstatic in production

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Allow large admin forms (e.g. routing tables with many inline records)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

# secure cookies
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True

if DEVMODE != DEVMODE_PRODUCTION:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

# settings.py

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "level": "DEBUG",  # Set this to DEBUG
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",  # Keep this as INFO for Django-related logging
        },
        # Add this to configure your logger
        "core": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "__main__": {  # If the logger name is __main__
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
    },
}

ASGI_APPLICATION = "pbx.asgi.application"

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# custom PBX settings (not Django settings)

# where the configuration /etc/asterisk files are stored in the filesystem
ASTERISK_ROOT_DIR = env.str("ASTERISK_ROOT_DIR", "/tmp")
# where the configuration files are stored in the ASTERISK_ROOT_DIR
ASTERISK_CONFIG_DIR = env.str("ASTERISK_CONFIG_DIR", "/etc/asterisk")
# where the backup files are stored
ASTERISK_BACKUP_DIR = env.str("ASTERISK_BACKUP_DIR", "/tmp/backup/asterisk")
ASTERISK_MANAGER_PORT = env.int("ASTERISK_MANAGER_PORT", 5038)
ASTERISK_MANAGER_HOST = env.str("ASTERISK_MANAGER_HOST", "127.0.0.1")
ASTERISK_MANAGER_BIND = env.str("ASTERISK_MANAGER_BIND", "127.0.0.1")
ASTERISK_MANAGER_USERNAME = env.str("ASTERISK_MANAGER_USERNAME", "django")
ASTERISK_MANAGER_SECRET = env.str(
    "ASTERISK_MANAGER_SECRET",
    "lFDccdsjqPWPe7ah7OJqLDxdtY6KM1VeTsS8V027msBpulwZHLmeaWnA-hWbpgkz3PZfdQ5GeCE63-lWTgqx3Q",
)

ASTERISK_MONITOR_DIR = env.str(
    "ASTERISK_MONITOR_DIR", default="/var/spool/asterisk/monitor"
)

ASTERISK_BACKUP_MONITOR_DIR = env.str("ASTERISK_BACKUP_MONITOR_DIR", default="")

TFTP_DIR = env.str("TFTP_DIR", default="/var/lib/tftpboot/")

PEARLPBX_DEFAULT_ROUTING_TABLE = "PEARLPBX"
PEARLPBX_DEFAULT_ROUTING_RECORD = "PEARLPBX-Users"
PEARLPBX_DEFAULT_ROUTING_PREFIX = "_2XX"

# 0 = current day (since 00:00); >0 = sliding window in minutes
DASHBOARD_MISSED_CALL_WINDOW_MINUTES = env.int(
    "DASHBOARD_MISSED_CALL_WINDOW_MINUTES", 0
)

PHONE_COUNTRY_CODE = env.str("PHONE_COUNTRY_CODE", "380")
PHONE_LOCAL_CODE = env.str("PHONE_LOCAL_CODE", "044")
PHONE_REQUIRED_LEN = env.int("PHONE_REQUIRED_LEN", 10)
PHONE_CITYCODE_LEN = env.int("PHONE_CITYCODE_LEN", 7)

TEMPLATE_DATE_FORMAT = "d/m/y"
TEMPLATE_TIME_FORMAT = "H:i:s"
TEMPLATE_DATETIME_FORMAT = "%s %s" % (TEMPLATE_DATE_FORMAT, TEMPLATE_TIME_FORMAT)
TEMPLATE_MOMENT_DATETIME_FORMAT = "DD/MM/YY HH:mm:ss"
TEMPLATE_POPUP_TIMEOUT_MS = 5000

LOGIN_REDIRECT_URL = "/"

HEADER_MENU_PAGES = [
    {
        "title": _("Dashboard"),
        "url": "/dashboard/",
        "item_icon": "home",
        "allowed_roles": ["admin", "superuser", "Report Viewer"],
    },
    {
        "title": _("Parking"),
        "url": "/dashboard/ulines/",
        "item_icon": "grid",
        "allowed_roles": ["admin", "superuser", "Report Viewer"],
    },
    {
        "title": _("Reports"),
        "url": "/reports/",
        "item_icon": "print",
        "allowed_roles": ["admin", "superuser", "Report Viewer"],
    },
    {
        "title": _("Lists"),
        "url": "/lists/",
        "item_icon": "list",
        "allowed_roles": ["admin", "superuser", "Report Viewer"],
    },
    {
        "title": _("Admin panel"),
        "url": "/admin",
        "item_icon": "settings",
        "allowed_roles": ["superuser"],
    },
]
