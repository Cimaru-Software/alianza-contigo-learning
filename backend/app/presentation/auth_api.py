import re
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from html import escape

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token, create_refresh_token, get_jwt,
    get_jwt_identity, jwt_required, set_access_cookies, set_refresh_cookies,
    unset_jwt_cookies,
)
from itsdangerous import BadSignature, URLSafeTimedSerializer
from limits import parse
from sqlalchemy.exc import IntegrityError

from app.extensions import client_ip, db, limiter, request_email
from app.infrastructure.email_service import branded_html, send_html_later
from app.infrastructure.persistence.models import UserModel, check_dummy_password
from app.presentation import validation

auth_api = Blueprint("auth", __name__)
ROLES = {"admin", "teacher", "student"}
RESET_TOKEN_MAX_AGE = 30 * 60
FAILED_LOGINS_PER_ACCOUNT_IP = parse("10 per 15 minutes")
FAILED_LOGINS_PER_ACCOUNT = parse("50 per hour")
PASSWORD_MESSAGE = "La contraseña debe tener al menos 8 caracteres, una letra y un número."


def error(message, status=400, code="invalid_request"):
    return jsonify({"error": code, "message": message}), status


def json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def clean_text(value, max_length):
    """Trimmed text, "" when missing, or None when it is not text, is too long or has control characters."""
    if value is None:
        return ""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if len(value) > max_length or validation.SINGLE_LINE_FORBIDDEN.search(value):
        return None
    return value


def person_fields(data, *, cedula_required):
    """Validate the fields shared by student registration and teacher creation (raises ValidationError)."""
    fields = {
        "firstName": validation.person_name(data.get("firstName"), "El nombre"),
        "lastName": validation.person_name(data.get("lastName"), "El apellido"),
        "email": validation.email(data.get("email")),
        "phone": validation.phone(data.get("phone")),
        "nationalId": validation.cedula(data.get("nationalId"), required=cedula_required),
    }
    if not password_is_valid(data.get("password")):
        return None, error(PASSWORD_MESSAGE)
    if UserModel.query.filter_by(email=fields["email"]).first():
        return None, error("Ya existe una cuenta con este correo.", 409, "email_exists")
    if fields["nationalId"] and UserModel.query.filter_by(national_id=fields["nationalId"]).first():
        return None, error("Ya existe una cuenta con esta cédula.", 409, "national_id_exists")
    return fields, None


def save_new_user(user):
    """Commit a new account; a concurrent duplicate sign-up becomes a 409 instead of a 500."""
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("Ya existe una cuenta con este correo o cédula.", 409, "email_exists")
    return None


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapped(*args, **kwargs):
            if get_jwt().get("role") not in roles:
                return error("No tienes permisos para realizar esta acción.", 403, "forbidden")
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def password_is_valid(password):
    return isinstance(password, str) and 8 <= len(password) <= 128 and bool(re.search(r"[A-Za-z]", password)) and bool(re.search(r"\d", password))


def issue_session(user, **payload):
    claims = {"role": user.role}
    response = jsonify({"user": user.to_dict(), **payload})
    set_access_cookies(response, create_access_token(identity=str(user.id), additional_claims=claims))
    # The password fingerprint lets a password change revoke refresh tokens issued before it.
    set_refresh_cookies(response, create_refresh_token(identity=str(user.id), additional_claims={**claims, "pwd": user.password_fingerprint()}))
    return response


@auth_api.post("/register")
@limiter.limit(lambda: current_app.config.get("RATELIMIT_REGISTER", "40 per minute;400 per hour"), key_func=client_ip)
def register():
    data = validation.json_object()
    fields, failure = person_fields(data, cedula_required=True)
    if failure:
        return failure
    user = UserModel(first_name=fields["firstName"], last_name=fields["lastName"], email=fields["email"],
                     role="student", national_id=fields["nationalId"] or None, phone=fields["phone"] or None)
    user.set_password(data["password"])
    failure = save_new_user(user)
    if failure:
        return failure
    return issue_session(user), 201


def seconds_until_reset(strategy, item, keys):
    return max(1, int(strategy.get_window_stats(item, *keys).reset_time - time.time()))


def reserve_login_attempt(email):
    """Take one attempt from the account's budget before the password is checked.

    The reservation is an atomic counter increment, so concurrent guesses cannot all slip through before
    the first failure is recorded. The hard lock is keyed by account + IP: an attacker elsewhere cannot
    lock the real user out with a handful of wrong passwords; a looser per-account cap stops distributed
    guessing. Returns the seconds to wait, or None when the attempt may proceed.
    """
    if not limiter.enabled or not email:
        return None
    try:
        strategy = limiter.limiter
        account = ("login-account", email)
        attempt = ("login", email, client_ip())
        if not strategy.test(FAILED_LOGINS_PER_ACCOUNT, *account):
            return seconds_until_reset(strategy, FAILED_LOGINS_PER_ACCOUNT, account)
        if not strategy.hit(FAILED_LOGINS_PER_ACCOUNT_IP, *attempt):
            return seconds_until_reset(strategy, FAILED_LOGINS_PER_ACCOUNT_IP, attempt)
    except Exception:
        # Same policy as the decorators (swallow_errors): a rate-limit storage outage must not block logins.
        current_app.logger.exception("No se pudo verificar el límite de intentos de inicio de sesión")
    return None


def settle_login_attempt(email, succeeded):
    if not limiter.enabled or not email:
        return
    try:
        if succeeded:
            limiter.limiter.clear(FAILED_LOGINS_PER_ACCOUNT_IP, "login", email, client_ip())
        else:
            limiter.limiter.hit(FAILED_LOGINS_PER_ACCOUNT, "login-account", email)
    except Exception:
        current_app.logger.exception("No se pudo registrar el intento de inicio de sesión")


@auth_api.post("/login")
@limiter.limit(lambda: current_app.config.get("RATELIMIT_LOGIN", "60 per minute;1000 per hour"), key_func=client_ip)
def login():
    data = json_body()
    email = (clean_text(data.get("email"), 254) or "").lower()
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    wait = reserve_login_attempt(email)
    if wait:
        response = jsonify({"error": "rate_limited", "message": "Demasiados intentos fallidos. Espera unos minutos e inténtalo nuevamente."})
        response.headers["Retry-After"] = str(wait)
        return response, 429
    user = UserModel.query.filter_by(email=email).first() if email else None
    if not user:
        check_dummy_password(password)
        settle_login_attempt(email, succeeded=False)
        return error("Correo o contraseña incorrectos.", 401, "invalid_credentials")
    if not user.check_password(password):
        settle_login_attempt(email, succeeded=False)
        return error("Correo o contraseña incorrectos.", 401, "invalid_credentials")
    settle_login_attempt(email, succeeded=True)
    if not user.is_active:
        return error("Esta cuenta se encuentra desactivada.", 403, "inactive_account")
    requested_role = data.get("role")
    if requested_role and user.role != requested_role:
        return error("Esta cuenta no tiene acceso a este portal.", 403, "wrong_portal")
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()
    return issue_session(user)


@auth_api.get("/me")
@jwt_required()
def me():
    user = db.session.get(UserModel, uuid.UUID(get_jwt_identity()))
    if not user or not user.is_active:
        return error("Sesión no disponible.", 401, "session_invalid")
    return jsonify({"user": user.to_dict()})


@auth_api.patch("/profile")
@role_required("student", "teacher", "admin")
def update_profile():
    user = db.session.get(UserModel, uuid.UUID(get_jwt_identity()))
    if not user:
        return error("Sesión no disponible.", 401, "session_invalid")
    data = validation.json_object()
    # Blank names keep the current value, as the profile form sends every field.
    if validation.text(data.get("firstName"), "El nombre", 100):
        user.first_name = validation.person_name(data["firstName"], "El nombre")
    if validation.text(data.get("lastName"), "El apellido", 100):
        user.last_name = validation.person_name(data["lastName"], "El apellido")
    if "phone" in data:
        user.phone = validation.phone(data.get("phone")) or None
    if data.get("avatarKey") in {"navy", "gold", "emerald", "plum"}:
        user.avatar_key = data["avatarKey"]
    db.session.commit()
    return jsonify({"user": user.to_dict()})


@auth_api.post("/change-password")
@limiter.limit("10 per hour")
@role_required("student", "teacher", "admin")
def change_password():
    user = db.session.get(UserModel, uuid.UUID(get_jwt_identity()))
    data = json_body()
    current_password = data.get("currentPassword")
    if not isinstance(current_password, str) or not user.check_password(current_password):
        return error("La contraseña actual es incorrecta.", 400, "wrong_password")
    if not password_is_valid(data.get("newPassword")):
        return error("La nueva contraseña debe tener al menos 8 caracteres, una letra y un número.")
    user.set_password(data["newPassword"])
    db.session.commit()
    # Other devices lose their refresh token; this one gets a fresh session.
    return issue_session(user, message="Contraseña actualizada correctamente.")


@auth_api.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    user = db.session.get(UserModel, uuid.UUID(get_jwt_identity()))
    if not user or not user.is_active:
        return error("Sesión no disponible.", 401, "session_invalid")
    fingerprint = get_jwt().get("pwd")
    if fingerprint and fingerprint != user.password_fingerprint():
        return error("La contraseña cambió. Inicia sesión nuevamente.", 401, "session_invalid")
    response = jsonify({"user": user.to_dict()})
    set_access_cookies(response, create_access_token(identity=str(user.id), additional_claims={"role": user.role}))
    return response


@auth_api.post("/logout")
def logout():
    response = jsonify({"message": "Sesión cerrada."})
    unset_jwt_cookies(response)
    return response


def reset_serializer():
    return URLSafeTimedSerializer(current_app.config["JWT_SECRET_KEY"], salt="password-reset")


def send_reset_email(user, token):
    link = f'{current_app.config["FRONTEND_URL"]}/restablecer-contrasena?token={token}'
    html = branded_html(
        "Restablece tu contraseña",
        f"Hola {escape(user.first_name)},",
        "Recibimos una solicitud para cambiar la contraseña de tu cuenta. Usa el botón para crear una nueva. "
        "<div style='margin-top:20px;padding:16px 18px;background:#F7F8FA;border-left:3px solid #C89432;border-radius:6px;color:#405168;font-size:13px'>"
        "Este enlace vence en <strong>30 minutos</strong>. Si no solicitaste el cambio, puedes ignorar este correo; tu contraseña seguirá igual.</div>",
        "Crear nueva contraseña",
        link,
    )
    # Queued so the response time does not reveal whether the email is registered.
    send_html_later(user.email, "Restablece tu contraseña — Alianza Contigo", html)


@auth_api.post("/forgot-password")
@limiter.limit("20 per hour", key_func=client_ip)
@limiter.limit("3 per hour", key_func=request_email)
def forgot_password():
    email = (clean_text(json_body().get("email"), 254) or "").lower()
    user = UserModel.query.filter_by(email=email, is_active=True).first() if email else None
    if user:
        # Signed with the current password fingerprint, so the link stops working once used.
        token = reset_serializer().dumps({"sub": str(user.id), "pwd": user.password_fingerprint()})
        send_reset_email(user, token)
    return jsonify({"message": "Si el correo está registrado, recibirás un enlace de recuperación."})


@auth_api.post("/reset-password")
@limiter.limit("20 per hour", key_func=client_ip)
def reset_password():
    data = json_body()
    if not password_is_valid(data.get("password")):
        return error("La contraseña debe tener al menos 8 caracteres, una letra y un número.")
    token = data.get("token")
    try:
        decoded = reset_serializer().loads(token, max_age=RESET_TOKEN_MAX_AGE) if isinstance(token, str) else None
        user = db.session.get(UserModel, uuid.UUID(decoded["sub"])) if isinstance(decoded, dict) else None
    except (BadSignature, ValueError, KeyError, TypeError):
        return error("El enlace es inválido o venció.", 400, "invalid_token")
    if not user or not user.is_active or decoded.get("pwd") != user.password_fingerprint():
        return error("El enlace es inválido o ya fue utilizado.", 400, "invalid_token")
    user.set_password(data["password"])
    db.session.commit()
    return jsonify({"message": "Contraseña actualizada correctamente."})


@auth_api.get("/users")
@role_required("admin")
def users():
    role = request.args.get("role")
    query = UserModel.query
    if role in ROLES:
        query = query.filter_by(role=role)
    return jsonify({"users": [user.to_dict() for user in query.order_by(UserModel.created_at.desc()).all()]})


@auth_api.post("/teachers")
@role_required("admin")
def create_teacher():
    data = validation.json_object()
    fields, failure = person_fields(data, cedula_required=False)
    if failure:
        return failure
    user = UserModel(first_name=fields["firstName"], last_name=fields["lastName"], email=fields["email"], role="teacher",
                     national_id=fields["nationalId"] or None, phone=fields["phone"] or None)
    user.set_password(data["password"])
    failure = save_new_user(user)
    if failure:
        return failure
    return jsonify({"user": user.to_dict()}), 201
