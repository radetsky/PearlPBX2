# SPDX-License-Identifier: LicenseRef-PolyForm-Shield-1.0.0
# Copyright (C) 2024-2026 Alex Radetsky

import environ

from django.core.exceptions import ImproperlyConfigured
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
SECRET_KEY = env.str("DJANGO_SECRET_KEY", "")  # generate with: openssl rand -hex 50

if DEVMODE == DEVMODE_WITHOUT_ASTERISK:
    # DEBUG and a committed key are only acceptable for local, non-network dev.
    # SECURITY WARNING: don't run with debug turned on in production!
    DEBUG = True
    # SECURITY WARNING: keep the secret key used in production secret!
    SECRET_KEY = "django-insecure-dom_8=vl0m@(cfoacp393+*&3s#jrtl#rt45o6=k3#7%llprq^"
elif not SECRET_KEY:
    # Any network-reachable mode (Development / Staging / Production) must
    # supply its own secret via the environment — never the committed one.
    raise ImproperlyConfigured(
        f"DJANGO_SECRET_KEY must be set for DEVMODE={DEVMODE!r}."
    )


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
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "core",
    "apps.api",
    "apps.callback",
    "apps.provision",
    "apps.reports",
    "apps.dashboard",
    "apps.lists",
    "apps.webhooks",
    "pbx.apps.MyAdminConfig",  # replaces 'django.contrib.admin'
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "core.middleware.ForceEnglishAPIMiddleware",
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
        "TIME_ZONE": env.str("DB_TIME_ZONE", "Europe/Kyiv"),
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

if DEVMODE not in (DEVMODE_PRODUCTION, DEVMODE_STAGING):
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

# settings.py

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",  # Keep this as INFO for Django-related logging
        },
        # Keep application logs at INFO by default to avoid flooding journald with
        # AMI event payloads (which contain caller IDs / PII).
        "core": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "__main__": {  # If the logger name is __main__
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
    },
}

ASGI_APPLICATION = "pbx.asgi.application"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.api.exceptions.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "PearlPBX2 API",
    "DESCRIPTION": "REST API for PearlPBX2 — blacklist, whitelist, contacts, custom lists, call origination, and call recordings.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379")

# Public base URL of this web interface; used to build absolute links
# (e.g. call recording URLs in CRM webhook payloads).
PEARLPBX_PUBLIC_URL = env.str("PEARLPBX_PUBLIC_URL", default="http://localhost:8000")

# Outgoing email. SMTP is used as soon as EMAIL_HOST is set; otherwise mail is
# printed to stdout so a dev machine can never accidentally send a real report.
# On a typical Asterisk host with a local MTA, EMAIL_HOST=localhost is enough.
EMAIL_HOST = env.str("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
# Without a timeout smtplib blocks forever on an unresponsive relay, which would
# hang the nightly cron job indefinitely instead of failing it.
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=30)
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="pearlpbx2@localhost")

EMAIL_BACKEND = env.str(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.smtp.EmailBackend"
        if EMAIL_HOST
        else "django.core.mail.backends.console.EmailBackend"
    ),
)

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ImproperlyConfigured(
        "EMAIL_USE_TLS and EMAIL_USE_SSL are mutually exclusive - set only one."
    )

# Default recipients of `manage.py mail_report` (comma-separated).
# Empty means the report is not configured and the command is a no-op.
MAIL_REPORT_RECIPIENTS = env.list("MAIL_REPORT_RECIPIENTS", default=[])
# Default number of rows in the longest-calls table.
MAIL_REPORT_LIMIT = env.int("MAIL_REPORT_LIMIT", default=10)

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
            "capacity": 256,  # max messages buffered per channel (default 100)
            "expiry": 60,  # seconds a message may sit before being dropped
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
# No default secret: it would end up in manager.conf with full AMI rights.
# Require it explicitly for network-reachable deployments, fall back to an obvious
# placeholder only for local dev.
ASTERISK_MANAGER_SECRET = env.str("ASTERISK_MANAGER_SECRET", "")
if not ASTERISK_MANAGER_SECRET:
    if DEVMODE in (DEVMODE_PRODUCTION, DEVMODE_STAGING):
        raise ImproperlyConfigured(
            "ASTERISK_MANAGER_SECRET must be set in Production/Staging. "
            "Generate one with: openssl rand -base64 48"
        )
    ASTERISK_MANAGER_SECRET = "dev-insecure-ami-secret-change-me"

# AMI client/response timeout (seconds) used when a caller of
# core.ami.AsteriskManagementInterface doesn't pass one explicitly. Long by design:
# it covers slow admin operations like `core restart now` (pbx/admin.py's Apply
# Changes flow), which can legitimately take a while.
ASTERISK_AMI_DEFAULT_TIMEOUT = env.int("ASTERISK_AMI_DEFAULT_TIMEOUT", 3600)

# AMI client/response timeout (seconds) for short, synchronous actions that don't
# wait on a dial/answer (QueuePause, QueueStatus, Hangup). Matches the timeout
# services/fastagi/fastagi.py already uses for its own AMI QueueStatus query.
ASTERISK_AMI_QUICK_TIMEOUT = env.int("ASTERISK_AMI_QUICK_TIMEOUT", 5)

# Extra seconds of slack added on top of an Originate's own Asterisk-side timeout_ms
# when bounding the AMI client's response wait, so a slow-but-successful round trip
# isn't cut off right as Asterisk's own Originate timeout fires.
ASTERISK_AMI_RESPONSE_MARGIN = env.int("ASTERISK_AMI_RESPONSE_MARGIN", 5)

ASTERISK_MONITOR_DIR = env.str(
    "ASTERISK_MONITOR_DIR", default="/var/spool/asterisk/monitor"
)

ASTERISK_BACKUP_MONITOR_DIR = env.str("ASTERISK_BACKUP_MONITOR_DIR", default="")

TFTP_DIR = env.str("TFTP_DIR", default="/var/lib/tftpboot/")

PEARLPBX_DEFAULT_ROUTING_TABLE = "PEARLPBX"
PEARLPBX_DEFAULT_ROUTING_RECORD = "PEARLPBX-Users"
PEARLPBX_DEFAULT_ROUTING_PREFIX = "_2XX"

# Dialplan context (ConfBridge room = ${EXTEN}) created by migration
# core.0079_create_conference_dialplan_context. If changed from the default,
# create a matching DialplanContext/DialplanExtension manually — renaming or
# deleting that row does not follow this setting automatically.
PEARLPBX_CONFERENCE_CONTEXT = env.str("PEARLPBX_CONFERENCE_CONTEXT", default="conference")

# 0 = current day (since 00:00); >0 = sliding window in minutes
DASHBOARD_MISSED_CALL_WINDOW_MINUTES = env.int(
    "DASHBOARD_MISSED_CALL_WINDOW_MINUTES", 0
)

# Range of parking ULINE slots allocated by the FastAGI parking-uline handler
PARKING_ULINE_MIN = env.int("PARKING_ULINE_MIN", default=1)
PARKING_ULINE_MAX = env.int("PARKING_ULINE_MAX", default=199)

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
