import os


class BaseConfig:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-development-secret")
    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    JWT_COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "Lax")
    JWT_ACCESS_COOKIE_NAME = "alianza_access_token"
    JWT_REFRESH_COOKIE_NAME = "alianza_refresh_token"
    JWT_ACCESS_CSRF_COOKIE_NAME = "alianza_access_csrf"
    JWT_REFRESH_CSRF_COOKIE_NAME = "alianza_refresh_csrf"
    JWT_ACCESS_TOKEN_EXPIRES = 900
    JWT_REFRESH_TOKEN_EXPIRES = 60 * 60 * 24 * 30
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
    MAIL_SENDER = os.getenv("MAIL_SENDER", "Alianza Contigo")
    MAIL_RECIPIENT = os.getenv("MAIL_RECIPIENT") or EMAIL_ADDRESS
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
    # Reject sign-ups whose email domain has no MX/A records (cached per domain, see email_verification).
    EMAIL_CHECK_DELIVERABILITY = os.getenv("EMAIL_CHECK_DELIVERABILITY", "true").lower() == "true"
    EMAIL_DNS_TIMEOUT = int(os.getenv("EMAIL_DNS_TIMEOUT", "3"))
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "/app/uploads")
    # The global ceiling must accommodate course videos. The upload endpoint applies
    # stricter per-type limits to images and documents.
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "500")) * 1024 * 1024
    MAX_DOCUMENT_UPLOAD_MB = int(os.getenv("MAX_DOCUMENT_UPLOAD_MB", "25"))
    MAX_VIDEO_UPLOAD_MB = int(os.getenv("MAX_VIDEO_UPLOAD_MB", "500"))
    BANK_NAME = os.getenv("BANK_NAME", "BANCO DEL AUSTRO")
    BANK_ACCOUNT_TYPE = os.getenv("BANK_ACCOUNT_TYPE", "CUENTA CORRIENTE")
    BANK_ACCOUNT_NUMBER = os.getenv("BANK_ACCOUNT_NUMBER", "2401000456")
    BANK_ACCOUNT_HOLDER = os.getenv("BANK_ACCOUNT_HOLDER", "ALIANZACONTIGO S.A.S")
    BANK_ACCOUNT_ID = os.getenv("BANK_ACCOUNT_ID", "0195185840001")
    PAYPHONE_STORE_ID = os.getenv("PAYPHONE_STORE_ID", "")
    PAYPHONE_TOKEN = os.getenv("PAYPHONE_TOKEN", "")
    # Pool sized for gunicorn threads per worker; pre-ping drops connections Postgres closed.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "10")),
    }
    # Number of reverse proxies (Caddy) in front of the API whose X-Forwarded-For is trusted.
    TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))
    EMAIL_ASYNC = os.getenv("EMAIL_ASYNC", "true").lower() == "true"
    RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "true").lower() == "true"
    # Use redis:// in production so every gunicorn worker shares the same counters.
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    # Short timeouts so a stalled Redis degrades to in-memory limits instead of hanging requests.
    RATELIMIT_STORAGE_OPTIONS = {"socket_connect_timeout": 0.5, "socket_timeout": 0.5} if RATELIMIT_STORAGE_URI.startswith("redis") else {}
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "600 per minute")
    # Per-IP limits sized so a whole classroom behind one public IP can register at once.
    RATELIMIT_REGISTER = os.getenv("RATELIMIT_REGISTER", "40 per minute;400 per hour")
    RATELIMIT_LOGIN = os.getenv("RATELIMIT_LOGIN", "60 per minute;1000 per hour")


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://alianza:alianza@localhost:5432/alianza_contigo",
    )


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "")


INSECURE_JWT_SECRETS = {"", "change-this-development-secret", "development-only-change-me", "replace-with-at-least-64-random-characters"}


def get_config():
    if os.getenv("FLASK_ENV") == "production" and not ProductionConfig.SQLALCHEMY_DATABASE_URI:
        raise RuntimeError("DATABASE_URL is required in production")
    if os.getenv("FLASK_ENV") == "production" and ProductionConfig.JWT_SECRET_KEY in INSECURE_JWT_SECRETS:
        raise RuntimeError("JWT_SECRET_KEY must be set to a random secret in production")
    return ProductionConfig if os.getenv("FLASK_ENV") == "production" else DevelopmentConfig
