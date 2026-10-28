"""Checks that an email address is well formed and that its domain can actually receive mail."""
import threading
import time

from email_validator import EmailNotValidError, EmailUndeliverableError, validate_email
from email_validator.deliverability import validate_email_deliverability

# Throwaway inboxes: accounts created with them cannot be contacted after enrollment.
DISPOSABLE_DOMAINS = frozenset({
    "10minutemail.com", "20minutemail.com", "discard.email", "dispostable.com", "emailondeck.com",
    "fakeinbox.com", "getnada.com", "guerrillamail.com", "guerrillamail.net", "maildrop.cc",
    "mailinator.com", "mailnesia.com", "mintemail.com", "mohmal.com", "sharklasers.com",
    "spamgourmet.com", "temp-mail.org", "tempail.com", "tempmail.com", "tempr.email",
    "throwawaymail.com", "trashmail.com", "yopmail.com", "yopmail.net",
})
_DOMAIN_TTL_SECONDS = 3600
_DOMAIN_CACHE_LIMIT = 5000
_domain_cache: dict[str, tuple[float, str | None]] = {}
_domain_cache_lock = threading.Lock()


class InvalidEmail(ValueError):
    """The address is malformed, disposable or its domain does not accept email."""


def _domain_problem(domain: str, timeout: int) -> str | None:
    """MX/A lookup cached per domain, so registrations do not wait on DNS for every request."""
    now = time.monotonic()
    with _domain_cache_lock:
        cached = _domain_cache.get(domain)
        if cached and now - cached[0] < _DOMAIN_TTL_SECONDS:
            return cached[1]
    try:
        # A DNS timeout is reported as "unknown" instead of raising: a slow resolver must not block sign-ups.
        validate_email_deliverability(domain, domain, timeout=timeout)
        problem = None
    except EmailUndeliverableError:
        problem = "El dominio del correo no existe o no recibe correos."
    with _domain_cache_lock:
        if len(_domain_cache) >= _DOMAIN_CACHE_LIMIT:
            _domain_cache.clear()
        _domain_cache[domain] = (now, problem)
    return problem


def normalize_real_email(value: str, check_deliverability: bool, timeout: int = 3) -> str:
    """Return the lowercase address or raise InvalidEmail with a message for the user."""
    try:
        # Syntax per RFC 5321/5322, no quoted local parts or IP literals, no reserved TLDs (.local, .test…).
        validated = validate_email(value, check_deliverability=False)
    except EmailNotValidError as exc:
        raise InvalidEmail("Ingresa un correo electrónico válido.") from exc
    domain = validated.ascii_domain.lower()
    if domain in DISPOSABLE_DOMAINS:
        raise InvalidEmail("No se permiten correos temporales o desechables.")
    if check_deliverability:
        problem = _domain_problem(domain, timeout)
        if problem:
            raise InvalidEmail(problem)
    return validated.normalized.lower()
