"""Local development settings for wger"""

import os

# ruff: noqa: F405
# ruff: noqa: F403

# wger
from .settings_global import *

DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 't')

# List of administrators
ADMINS = ['"Your name" <your_email@example.com>']
MANAGERS = ADMINS

# Secret key: read from environment if present, generate random key for local run
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', os.environ.get('SECRET_KEY', ''))
if not SECRET_KEY:
    import secrets
    SECRET_KEY = secrets.token_urlsafe(50)

# List of allowed hosts (env-driven with localhost defaults, no wildcard)
_allowed_hosts_env = os.environ.get('ALLOWED_HOSTS', os.environ.get('DJANGO_ALLOWED_HOSTS', ''))
if _allowed_hosts_env:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_env.split(',') if h.strip()]
else:
    ALLOWED_HOSTS = [
        'localhost',
        '127.0.0.1',
    ]

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# WGER application
WGER_SETTINGS['ALLOW_UPLOAD_VIDEOS'] = True
WGER_SETTINGS['ALLOW_GUEST_USERS'] = True
WGER_SETTINGS['ALLOW_REGISTRATION'] = False
WGER_SETTINGS['DOWNLOAD_INGREDIENTS_FROM'] = 'WGER'  # or 'None' to disable
WGER_SETTINGS['EMAIL_FROM'] = 'wger Workout Manager <wger@example.com>'
WGER_SETTINGS['EXERCISE_CACHE_TTL'] = 500
WGER_SETTINGS['INGREDIENT_CACHE_TTL'] = 500
WGER_SETTINGS['SYNC_EXERCISES_CELERY'] = False
WGER_SETTINGS['SYNC_EXERCISE_IMAGES_CELERY'] = True
WGER_SETTINGS['SYNC_EXERCISE_VIDEOS_CELERY'] = False
WGER_SETTINGS['SYNC_INGREDIENTS_CELERY'] = True
WGER_SETTINGS['USE_CELERY'] = False
WGER_SETTINGS['CACHE_API_EXERCISES_CELERY'] = True
WGER_SETTINGS['CACHE_API_EXERCISES_CELERY_FORCE_UPDATE'] = True
WGER_SETTINGS['ROUTINE_CACHE_TTL'] = 500
DEFAULT_FROM_EMAIL = WGER_SETTINGS['EMAIL_FROM']


SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

_csrf_origins_env = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]
if _csrf_origins_env:
    for origin in _csrf_origins_env.split(','):
        origin = origin.strip()
        if origin and origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)


EXPOSE_PROMETHEUS_METRICS = True

COMPRESS_ENABLED = False
AXES_ENABLED = os.environ.get('AXES_ENABLED', 'False').lower() in ('true', '1', 't')
AXES_HANDLER = 'axes.handlers.database.AxesDatabaseHandler'



# Does not really cache anything
CACHES_DUMMY = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        'TIMEOUT': 100,
    }
}

# High-performance in-memory cache, resets when the server restarts
CACHE_LOCMEM = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'wger-cache',
        'TIMEOUT': 86400,
        'OPTIONS': {
            'MAX_ENTRIES': 10000,
            'CULL_FREQUENCY': 0,
        }
    }
}

# Redis cache
CACHE_REDIS = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://localhost:6379/1',
        'TIMEOUT': 5000,
        'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
    }
}


# Use Redis if environment variable set, else high-capacity LocMemCache
if os.environ.get('USE_REDIS', 'false').lower() == 'true':
    CACHES = CACHE_REDIS
else:
    CACHES = CACHE_LOCMEM
# CACHES = CACHES_DUMMY


# Django Debug Toolbar
# INSTALLED_APPS += ['django_extensions', 'debug_toolbar']
# MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware", ]
# INTERNAL_IPS = ["127.0.0.1", ]

# AUTH_PROXY_HEADER = 'HTTP_X_REMOTE_USER'
# AUTH_PROXY_USER_EMAIL_HEADER = 'HTTP_X_REMOTE_USER_EMAIL'
# AUTH_PROXY_USER_NAME_HEADER = 'HTTP_X_REMOTE_USER_NAME'
# AUTH_PROXY_TRUSTED_IPS = ['127.0.0.1', ]
# AUTH_PROXY_CREATE_UNKNOWN_USER = True


DBCONFIG_PG = {
    'ENGINE': 'django_prometheus.db.backends.postgresql',
    'NAME': 'wger',
    'USER': 'wger',
    'PASSWORD': 'wger',
    'HOST': 'localhost',
    'PORT': '5432',
}


DBCONFIG_SQLITE = {
    'ENGINE': 'django_prometheus.db.backends.sqlite3',
    'NAME': os.environ.get('DJANGO_DB_DATABASE', BASE_DIR.parent / 'database.sqlite'),
    'OPTIONS': {
        'timeout': 20,
    }
}

DATABASES = {
    # 'default': DBCONFIG_PG,
    'default': DBCONFIG_SQLITE,
}


# Import other local settings that are not in version control
try:
    from .local_dev_extra import *
except ImportError:
    pass

# Configure SQLite pragmas for Docker mount compatibility
from django.db.backends.signals import connection_created
from django.dispatch import receiver

@receiver(connection_created)
def configure_sqlite(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode = WAL;')
        cursor.execute('PRAGMA synchronous = NORMAL;')
        cursor.execute('PRAGMA cache_size = -64000;')
        cursor.execute('PRAGMA temp_store = MEMORY;')
        cursor.execute('PRAGMA mmap_size = 268435456;')
        cursor.execute('PRAGMA busy_timeout = 20000;')


