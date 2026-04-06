"""
Django settings for DroneWatch project.
Drone Surveillance Dashboard — rebuilt with Django + Channels.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'dronewatch-dev-key-change-in-production'

DEBUG = True

ALLOWED_HOSTS = ['*']

# ========================= INSTALLED APPS =========================

INSTALLED_APPS = [
    'daphne',
    'django.contrib.staticfiles',
    'channels',
    'surveillance',
]

# ========================= MIDDLEWARE =========================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
]

# ========================= URL CONFIG =========================

ROOT_URLCONF = 'dronewatch.urls'

# ========================= TEMPLATES =========================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.template.context_processors.static',
            ],
        },
    },
]

# ========================= ASGI =========================

ASGI_APPLICATION = 'dronewatch.asgi.application'

# ========================= CHANNELS =========================

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# ========================= STATIC FILES =========================

STATIC_URL = '/static/'

# ========================= DATABASES =========================
# No database needed for this project

DATABASES = {}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ========================= LOGGING =========================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
