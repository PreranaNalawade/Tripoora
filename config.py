import os
from dotenv import load_dotenv

load_dotenv()


def _as_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql://touristdb_gi02_user:0RcLjArSHQRGDGewr3ABXtfRR27lFYdp@dpg-d7ev879kh4rs73danap0-a/touristdb_gi02"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Database connection pool settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,           # Increased from 10
        'max_overflow': 40,        # Increased from 20
        'pool_recycle': 1800,      # Recycle connections after 30 minutes
        'pool_pre_ping': True,     # Verify connections before using
        'pool_timeout': 30,        # Wait up to 30 seconds for a connection
        'connect_args': {
            'connect_timeout': 10  # PostgreSQL connection timeout
        }
    }

    APP_ENV = os.getenv("APP_ENV", "development")
    DEBUG = _as_bool("FLASK_DEBUG", APP_ENV != "production")
    AUTO_CREATE_TABLES = _as_bool("AUTO_CREATE_TABLES", APP_ENV != "production")

    UPLOAD_FOLDER = os.path.join(os.getcwd(), "static/uploads")
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf"}

    # Security defaults for production deployment.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = _as_bool("SESSION_COOKIE_SECURE", APP_ENV == "production")
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
    TO_EMAIL = os.getenv("TO_EMAIL", "")
