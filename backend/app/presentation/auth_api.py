import re
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
from sqlalchemy.exc import IntegrityError

from app.extensions import client_ip, db, limiter, request_email
from app.infrastructure.email_service import branded_html, send_html_later
from app.infrastructure.persistence.models import UserModel, check_dummy_password

auth_api = Blueprint("auth", __name__)
ROLES = {"admin", "teacher", "student"}
EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
RESET_TOKEN_MAX_AGE = 30 * 60
PASSWORD_MESSAGE = "La contraseña debe tener al menos 8 caracteres, una letra y un número."


def error(message, status=400, code="invalid_request"):
    return jsonify({"error": code, "message": message}), status


def json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def clean_text(value, max_length):
    """Trimmed text, "" when missing, or None when it is not text or is too long."""
    if value is None:
        return ""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if len(value) <= max_length else None


def person_fields(data):
    """Validate the fields shared by student registration and teacher creation."""
    limits = {"firstName": 100, "lastName": 100, "email": 254, "phone": 30, "nationalId": 30}
    fields = {key: clean_text(data.get(key), limit) for key, limit in limits.items()}
    if None in fields.values():
        return None, error("Uno de los campos supera la longitud permitida.")
    fields["email"] = fields["email"].lower()
    if not all((fields["firstName"], fields["lastName"], fields["email"], data.get("password"))):
        return None, error("Completa todos los campos obligatorios.")
    if not EMAIL_PATTERN.fullmatch(fields["email"]):
        return None, error("Ingresa un correo electrónico válido.")
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
    data = json_body()
    fields, failure = person_fields(data)
    if failure:
        return failure
    user = UserModel(first_name=fields["firstName"], last_name=fields["lastName"], email=fields["email"],
                     role="student", national_id=fields["nationalId"] or None, phone=fields["phone"] or None)
    user.set_password(data["password"])
    failure = save_new_user(user)
    if failure:
        return failure
    return issue_session(user), 201


@auth_api.post("/login")
@limiter.limit(lambda: current_app.config.get("RATELIMIT_LOGIN", "60 per minute;1000 per hour"), key_func=client_ip)
@limiter.limit("10 per 15 minutes", key_func=request_email, deduct_when=lambda response: response.status_code == 401)
def login():
    data = json_body()
    email = (clean_text(data.get("email"), 254) or "").lower()
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    user = UserModel.query.filter_by(email=email).first() if email else None
    if not user:
        check_dummy_password(password)
        return error("Correo o contraseña incorrectos.", 401, "invalid_credentials")
    if not user.check_password(password):
        return error("Correo o contraseña incorrectos.", 401, "invalid_credentials")
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
    data = json_body()
    first_name = clean_text(data.get("firstName"), 100)
    last_name = clean_text(data.get("lastName"), 100)
    phone = clean_text(data.get("phone"), 30)
    if None in (first_name, last_name, phone):
        return error("Uno de los campos supera la longitud permitida.")
    if first_name:
        user.first_name = first_name
    if last_name:
        user.last_name = last_name
    if "phone" in data:
        user.phone = phone or None
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
    data = json_body()
    fields, failure = person_fields(data)
    if failure:
        return failure
    user = UserModel(first_name=fields["firstName"], last_name=fields["lastName"], email=fields["email"], role="teacher", phone=fields["phone"] or None)
    user.set_password(data["password"])
    failure = save_new_user(user)
    if failure:
        return failure
    return jsonify({"user": user.to_dict()}), 201
