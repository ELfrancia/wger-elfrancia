"""Local development settings for wger"""

import os

# ruff: noqa: F405
# ruff: noqa: F403

# wger
from .settings_global import *

DEBUG = True

# List of administrators
ADMINS = ['"Your name" <your_email@example.com>']
MANAGERS = ADMINS

# Don't use this key in production!
SECRET_KEY = 'wger-local-development-supersecret-key-1234567890!'

# List of allowed hosts (Explicit LAN IP & localhost)
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '192.168.1.103',
    '*',
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
    'http://192.168.1.103:8000',
    'https://192.168.1.103:8000',
    'http://192.168.1.103',
    'https://onyx.francescoadreani.dev',
    'http://onyx.francescoadreani.dev',
]
if _csrf_origins_env:
    for origin in _csrf_origins_env.split(','):
        origin = origin.strip()
        if origin and origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)


EXPOSE_PROMETHEUS_METRICS = True

COMPRESS_ENABLED = False
AXES_ENABLED = False
AXES_HANDLER = 'axes.handlers.database.AxesDatabaseHandler'


# Does not really cache anything
CACHES_DUMMY = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        'TIMEOUT': 100,
    }
}

# In-memory cache. Fast, but *per process*: with several gunicorn workers each
# one keeps its own copy and an invalidation done by one worker does not reach
# the others. Only use it for a single process runserver.
CACHE_LOCMEM = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'wger-cache',
        'TIMEOUT': 86400,
        'KEY_PREFIX': CACHE_KEY_PREFIX,
        'OPTIONS': {
            'MAX_ENTRIES': 10000,
            'CULL_FREQUENCY': 0,
        },
    }
}

# Shared cache, the only correct choice as soon as more than one process serves
# requests (gunicorn workers, celery, management commands).
#
# IGNORE_EXCEPTIONS makes django_redis return a cache miss instead of raising
# when redis is unreachable: the site keeps working (slower) rather than
# returning 500s. Ignored errors are logged.
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/1')

CACHE_REDIS = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'TIMEOUT': 86400,
        'KEY_PREFIX': CACHE_KEY_PREFIX,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'IGNORE_EXCEPTIONS': True,
            'SOCKET_CONNECT_TIMEOUT': 2,
            'SOCKET_TIMEOUT': 2,
        },
    }
}

DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True

# Use Redis when asked for, else the per-process LocMemCache.
#
# Keep USE_REDIS=false when running a single process (manage.py runserver);
# set it to true whenever gunicorn runs with more than one worker, otherwise
# the cache silently splits per worker and invalidation stops working.
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
    },
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
