"""Request validation shared by every blueprint.

SQL injection is prevented structurally: every query goes through SQLAlchemy with bound parameters and
no SQL is ever assembled from strings (tests/test_input_security.py guards this). These helpers are the
second layer: each field must have the expected type, length and character set, so hostile or malformed
input becomes a 400 with a clear message instead of reaching the database or raising a 500.
Free text (descriptions, messages) keeps quotes and symbols: it is stored as data and escaped on output.
"""
import re
import uuid
from decimal import Decimal, InvalidOperation

from flask import current_app, request

from app.domain.identity import is_valid_cedula
from app.infrastructure.email_verification import InvalidEmail, normalize_real_email

# NUL and other C0 controls: PostgreSQL rejects NUL in text, and none of them belong in user input.
MULTILINE_FORBIDDEN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SINGLE_LINE_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f]")
PHONE_PATTERN = re.compile(r"\+?[0-9(][0-9 ()-]*[0-9]")
NAME_PUNCTUATION = set(" '’-.")
MAX_PRICE = Decimal("99999999.99")


class ValidationError(Exception):
    """Rendered as a JSON 400 by the handler registered in create_app."""

    def __init__(self, message, status=400, code="invalid_request"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def json_object():
    """The JSON body as a dict; {} when there is no body; 400 when it is an array, number or string."""
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValidationError("La solicitud no es válida.")
    return data


def text(value, label, max_length, *, required=False, multiline=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValidationError(f"{label}: el formato no es válido.")
    value = value.strip()
    if required and not value:
        raise ValidationError(f"{label} es obligatorio.")
    if len(value) > max_length:
        raise ValidationError(f"{label} supera los {max_length} caracteres permitidos.")
    if (MULTILINE_FORBIDDEN if multiline else SINGLE_LINE_FORBIDDEN).search(value):
        raise ValidationError(f"{label} contiene caracteres no permitidos.")
    return value


def person_name(value, label):
    """Letters (any alphabet, with accents), spaces, apostrophes, hyphens and periods."""
    value = text(value, label, 100, required=True)
    if not any(ch.isalpha() for ch in value) or not all(ch.isalpha() or ch in NAME_PUNCTUATION for ch in value):
        raise ValidationError(f"{label} solo puede contener letras, espacios, apóstrofos y guiones.")
    return " ".join(value.split())


def phone(value):
    value = text(value, "El teléfono", 30)
    digits = sum(ch.isdigit() for ch in value)
    if value and (not PHONE_PATTERN.fullmatch(value) or not 7 <= digits <= 15):
        raise ValidationError("Ingresa un teléfono válido (7 a 15 dígitos).")
    return value


def cedula(value, *, required):
    value = text(value, "La cédula", 10, required=required)
    if value and not is_valid_cedula(value):
        raise ValidationError("La cédula no es válida. Verifica los 10 dígitos.")
    return value


def email(value):
    """A real, contactable address: valid syntax, not disposable and (in production) a domain with MX/A records."""
    value = text(value, "El correo electrónico", 254, required=True)
    config = current_app.config
    try:
        return normalize_real_email(
            value,
            check_deliverability=config.get("EMAIL_CHECK_DELIVERABILITY", False),
            timeout=config.get("EMAIL_DNS_TIMEOUT", 3),
        )
    except InvalidEmail as exc:
        raise ValidationError(str(exc)) from exc


def integer(value, label, *, default, minimum, maximum):
    """Whole number clamped to [minimum, maximum]; accepts 5, 5.0 and "5"; rejects text and booleans."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValidationError(f"{label} debe ser un número entero.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str) and re.fullmatch(r"-?\d{1,9}", value.strip()):
        number = int(value)
    else:
        raise ValidationError(f"{label} debe ser un número entero.")
    return max(minimum, min(maximum, number))


def money(value, label="El precio"):
    if value is None or value == "":
        return Decimal("0.00")
    if isinstance(value, bool):
        raise ValidationError(f"{label} no es válido.")
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValidationError(f"{label} no es válido.") from exc
    if not amount.is_finite():
        raise ValidationError(f"{label} no es válido.")
    if amount < 0:
        raise ValidationError(f"{label} no puede ser negativo.")
    if amount > MAX_PRICE:
        raise ValidationError(f"{label} supera el máximo permitido.")
    return amount.quantize(Decimal("0.01"))


def safe_url(value, label):
    """An uploaded file or an http(s) link; blocks javascript:, data: and other schemes that run code."""
    value = text(value, label, 500)
    if value and not value.startswith(("/api/v1/uploads/", "https://", "http://")):
        raise ValidationError(f"{label} debe ser un archivo subido o un enlace http(s).")
    return value


def string_list(value, label, *, max_items, max_length):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > max_items:
        raise ValidationError(f"{label}: se esperaba una lista de hasta {max_items} elementos.")
    return [text(item, label, max_length) for item in value]


def index_list(value, label, *, size):
    """Distinct option indexes, each inside range(size)."""
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{label}: indica al menos una respuesta correcta.")
    if any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item < size for item in value):
        raise ValidationError(f"{label}: la respuesta correcta debe ser una de las opciones.")
    return sorted(set(value))


def uuid_or_none(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
