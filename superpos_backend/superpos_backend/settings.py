import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Environment-driven config ────────────────────────────────────────────────
# Defaults keep local dev / CI working with zero setup. Production MUST set:
#   DJANGO_SECRET_KEY, DJANGO_DEBUG=false, DJANGO_ALLOWED_HOSTS,
#   POSTGRES_PASSWORD (+ the other POSTGRES_* if they differ),
#   CORS_ALLOWED_ORIGINS. See .env.example at the backend root.

def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')

def _env_list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(',') if x.strip()]

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    # Dev-only fallback. Never rely on it outside localhost.
    'django-insecure-04=$d_(0!%!7z34#j4wr@f@kq-1r-@8t7s6(e)9lcavnz%g0%q',
)

DEBUG = _env_bool('DJANGO_DEBUG', True)

ALLOWED_HOSTS = _env_list('DJANGO_ALLOWED_HOSTS', '*' if DEBUG else 'localhost,127.0.0.1')

# ── Apps ─────────────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    # local
    'accounts',
    'pos',
]

# ── Middleware ────────────────────────────────────────────────────────────────

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',          # must be first
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Hard-blocks /api/* for inactive or expired tenants. Runs after the
    # standard auth stack so request.user (if any) is already populated; we
    # also peek at the JWT manually for DRF-only requests.
    'accounts.middleware.SubscriptionCheckMiddleware',
]

ROOT_URLCONF = 'superpos_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'superpos_backend.wsgi.application'

# ── Database (PostgreSQL) ─────────────────────────────────────────────────────

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'superpos'),
        'USER': os.environ.get('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'K2362003k'),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}

# ── Auth user model ───────────────────────────────────────────────────────────

AUTH_USER_MODEL = 'accounts.User'

# Username uniqueness is enforced per-tenant via `User._meta.unique_together`
# rather than globally on the column. The auth.E003 check assumes
# USERNAME_FIELD is globally unique — silenced intentionally. Login flows
# must scope by tenant (custom serializer handles this).
SILENCED_SYSTEM_CHECKS = ['auth.E003']

# ── Password validation ───────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Internationalisation ──────────────────────────────────────────────────────

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Cairo'
USE_I18N = True
USE_TZ = True

# ── Static files ──────────────────────────────────────────────────────────────

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Media (uploaded files: tenant logos, etc.) ────────────────────────────────

MEDIA_URL  = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── CORS ──────────────────────────────────────────────────────────────────────
# Production: set CORS_ALLOWED_ORIGINS (comma-separated, with scheme) to the
# frontend origin(s); the allow-all fallback is for local dev only.

_cors_origins = _env_list('CORS_ALLOWED_ORIGINS', '')
if _cors_origins:
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = _cors_origins
else:
    CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# ── Django REST Framework ─────────────────────────────────────────────────────

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'superpos_backend.pagination.StandardPageNumberPagination',
    'PAGE_SIZE': 20,
}

# ── Simple JWT ────────────────────────────────────────────────────────────────

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=120),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# ── drf-spectacular (Swagger / OpenAPI) ───────────────────────────────────────

SPECTACULAR_SETTINGS = {
    'TITLE': 'SuperPOS API',
    'DESCRIPTION': 'REST API for the SuperPOS point-of-sale system.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
    },
}
