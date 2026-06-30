from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

load_dotenv()  # Load .env file if it exists (for local dev)

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-local-hr-platform-migration")
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

allowed_hosts_env = os.environ.get("ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_env.split(",")]

csrf_trusted_origins_env = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in csrf_trusted_origins_env.split(",")] if csrf_trusted_origins_env else []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "core",
    "hr",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Serve static files in production
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.current_profile",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"

# Database Configuration
# Fallback to local SQLite if DATABASE_URL is not provided (e.g., local dev)
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Casablanca"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Enable Whitenoise compression and caching
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media Storage Configuration
if os.environ.get("AWS_ACCESS_KEY_ID"):
    # AWS S3 Storage for production
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "eu-west-3")
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
else:
    # Local storage fallback
    MEDIA_URL = "media/"
    MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_TIMEOUT_MS = env_int("GEMINI_TIMEOUT_MS", 20000)
RAG_MAX_CONTEXT_ITEMS = env_int("RAG_MAX_CONTEXT_ITEMS", 8)
RAG_MAX_CONTEXT_TOKENS = env_int("RAG_MAX_CONTEXT_TOKENS", 6500)
GEMINI_API_CONFIGURED = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

BREVO_API_CONFIGURED = bool(os.environ.get("BREVO_API_KEY"))
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "")
BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME", "HR Platform")
BREVO_ACCOUNT_VERIFICATION_TEMPLATE_ID = os.environ.get("BREVO_ACCOUNT_VERIFICATION_TEMPLATE_ID", "")
BREVO_PASSWORD_RESET_TEMPLATE_ID = os.environ.get("BREVO_PASSWORD_RESET_TEMPLATE_ID", "")
BREVO_ACCOUNT_APPROVED_TEMPLATE_ID = os.environ.get("BREVO_ACCOUNT_APPROVED_TEMPLATE_ID", "")
BREVO_ACCOUNT_REJECTED_TEMPLATE_ID = os.environ.get("BREVO_ACCOUNT_REJECTED_TEMPLATE_ID", "")
ACCOUNT_VERIFICATION_CODE_TTL_MINUTES = env_int("ACCOUNT_VERIFICATION_CODE_TTL_MINUTES", 10)
ACCOUNT_VERIFICATION_MAX_ATTEMPTS = env_int("ACCOUNT_VERIFICATION_MAX_ATTEMPTS", 5)
ACCOUNT_VERIFICATION_RESEND_COOLDOWN_SECONDS = env_int("ACCOUNT_VERIFICATION_RESEND_COOLDOWN_SECONDS", 60)
PASSWORD_RESET_CODE_TTL_MINUTES = env_int("PASSWORD_RESET_CODE_TTL_MINUTES", 10)
PASSWORD_RESET_MAX_ATTEMPTS = env_int("PASSWORD_RESET_MAX_ATTEMPTS", 5)
PASSWORD_RESET_RESEND_COOLDOWN_SECONDS = env_int("PASSWORD_RESET_RESEND_COOLDOWN_SECONDS", 60)

# Logging Configuration for Production
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}

# Security Settings for Production (when DEBUG is False)
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Railway provides HTTPS, so we trust the X-Forwarded-Proto header
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

