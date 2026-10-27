from flask import current_app, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, decode_token


def client_ip() -> str:
    return f"ip:{get_remote_address()}"


def user_or_ip() -> str:
    """Rate-limit signed-in users individually so students sharing a network do not share a quota."""
    token = request.cookies.get(current_app.config["JWT_ACCESS_COOKIE_NAME"])
    if token:
        try:
            return f"user:{decode_token(token)['sub']}"
        except Exception:
            pass
    return client_ip()


def request_email() -> str:
    data = request.get_json(silent=True)
    email = data.get("email") if isinstance(data, dict) else None
    return f"email:{str(email or '').strip().lower()[:255]}"


db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
jwt = JWTManager()
# If Redis is unavailable, keep serving with per-process limits instead of failing requests.
limiter = Limiter(key_func=user_or_ip, headers_enabled=True, swallow_errors=True, in_memory_fallback_enabled=True)
