"""Input security: SQL injection, control characters, real emails, Ecuadorian cédula, brute force.

Also covers the fixes for DEF-05 (content edits keep progress), DEF-06 (courses with history cannot be
deleted), DEF-07/DEF-08 (atomic login budget per account + IP) and the JSON error contract.
"""
import ast
from pathlib import Path

import pytest
from email_validator import EmailUndeliverableError

from app.domain.identity import is_valid_cedula
from app.extensions import db
from app.infrastructure import email_verification
from app.infrastructure.persistence.models import CourseModel, LessonProgressModel, PaymentOrderModel, TrainingAreaModel, UserModel
from app.presentation import api as api_module
from tests.conftest import area_id, cedula, enroll, login

API = "/api/v1"
APP_SOURCE = Path(__file__).resolve().parents[1] / "app"
SQL_INJECTION_PAYLOADS = [
    "' OR '1'='1",
    "' OR 1=1 --",
    "admin'--",
    "'; DROP TABLE users; --",
    "1; DELETE FROM courses",
    "' UNION SELECT password_hash FROM users --",
    "\" OR \"\"=\"",
    "'); TRUNCATE payment_orders; --",
]


def registration(**overrides):
    return {"firstName": "Ana", "lastName": "Torres", "email": "nueva@example.com", "password": "Seguro123", "nationalId": cedula(7), **overrides}


# --- Ecuadorian cédula (Registro Civil modulo-10) --------------------------------------------

@pytest.mark.parametrize(
    "value, valid",
    [
        ("1710034065", True),           # published example, Pichincha
        ("0926687856", True),           # Guayas
        ("3050000011", True),           # 30: Ecuadorians registered abroad
        ("1710034066", False),          # wrong check digit
        ("0010034060", False),          # province 00
        ("2510034062", False),          # province 25 does not exist
        ("1760034065", False),          # third digit 6: not a natural person (RUC of public entity)
        ("171003406", False),           # 9 digits
        ("17100340650", False),         # 11 digits
        ("17100340A5", False),          # letters
        ("١٧١٠٠٣٤٠٦٥", False),          # Unicode digits are not accepted
        ("", False),
        (1710034065, False),            # not a string
    ],
)
def test_cedula_check_digit_algorithm(value, valid):
    assert is_valid_cedula(value) is valid


def test_cedula_generator_used_by_tests_is_itself_valid():
    assert all(is_valid_cedula(cedula(n, province)) for n in range(0, 999_999, 7919) for province in (1, 9, 17, 24, 30))


def test_registration_requires_a_real_cedula(web):
    assert web.post(API + "/auth/register", json=registration(nationalId="")).status_code == 400
    response = web.post(API + "/auth/register", json=registration(nationalId="1234567890"))
    assert response.status_code == 400 and "cédula" in response.json["message"]
    assert web.post(API + "/auth/register", json=registration()).status_code == 201


def test_teacher_cedula_is_optional_but_validated(web):
    login(web, "admin@example.com")
    teacher = {"firstName": "Luis", "lastName": "Mora", "email": "luis.mora@example.com", "password": "Seguro123"}
    assert web.post(API + "/auth/teachers", json={**teacher, "nationalId": "0000000000"}).status_code == 400
    created = web.post(API + "/auth/teachers", json={**teacher, "nationalId": cedula(3)})
    assert created.status_code == 201 and created.json["user"]["nationalId"] == cedula(3)


# --- Real email addresses --------------------------------------------------------------------

@pytest.mark.parametrize(
    "address",
    ["ana@", "ana@@example.com", "ana..torres@example.com", "ana torres@example.com", "ana@localhost",
     "ana@empresa.local", "ana@demo.test", "ana@[127.0.0.1]", "\"ana\"@example.com", "a" * 250 + "@example.com"],
)
def test_malformed_or_reserved_emails_are_rejected(web, address):
    assert web.post(API + "/auth/register", json=registration(email=address)).status_code == 400


@pytest.mark.parametrize("address", ["ana@mailinator.com", "ana@yopmail.com", "ana@guerrillamail.com"])
def test_disposable_emails_are_rejected(web, address):
    response = web.post(API + "/auth/register", json=registration(email=address))
    assert response.status_code == 400 and "temporales" in response.json["message"]


def test_email_domain_must_receive_mail_and_lookups_are_cached(app, web, monkeypatch):
    lookups = []

    def fake_deliverability(domain, _domain_i18n, timeout):
        lookups.append(domain)
        if domain == "dominio-inexistente.com":
            raise EmailUndeliverableError("The domain name does not exist.")
        return {"mx": [(10, f"mail.{domain}")]}

    monkeypatch.setattr(email_verification, "validate_email_deliverability", fake_deliverability)
    monkeypatch.setattr(email_verification, "_domain_cache", {})
    app.config["EMAIL_CHECK_DELIVERABILITY"] = True
    rejected = web.post(API + "/auth/register", json=registration(email="ana@dominio-inexistente.com"))
    assert rejected.status_code == 400 and "no recibe correos" in rejected.json["message"]
    assert web.post(API + "/auth/register", json=registration(email="Ana.Torres@Empresa.EC")).json["user"]["email"] == "ana.torres@empresa.ec"
    assert web.post(API + "/auth/register", json=registration(email="otra@empresa.ec", nationalId=cedula(8))).status_code == 201
    assert lookups == ["dominio-inexistente.com", "empresa.ec"]  # second empresa.ec sign-up hit the cache


def test_contact_form_validates_email_name_and_phone(web):
    base = {"name": "José Pérez", "email": "jose@example.com", "phone": "+593 99 044 8031", "courseSlug": "curso-base", "message": "Hola"}
    assert web.post(API + "/contact", json={**base, "email": "jose@yopmail.com"}).status_code == 400
    assert web.post(API + "/contact", json={**base, "name": "<script>alert(1)</script>"}).status_code == 400
    assert web.post(API + "/contact", json={**base, "phone": "llámame"}).status_code == 400
    assert web.post(API + "/contact", json=base).status_code == 503  # valid input; SMTP not configured in tests


# --- Names and phones ------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["José", "María José", "Ñúñez", "O'Brien", "Pérez-Gómez", "Ma. Fernanda"])
def test_real_names_are_accepted(web, name):
    assert web.post(API + "/auth/register", json=registration(firstName=name)).status_code == 201


@pytest.mark.parametrize("name", ["Ana1", "<b>Ana</b>", "Ana;", "Robert'); DROP TABLE users;--", "---", "Ana\u0000"])
def test_names_with_symbols_or_code_are_rejected(web, name):
    assert web.post(API + "/auth/register", json=registration(firstName=name)).status_code == 400


@pytest.mark.parametrize("value, status", [("0990448031", 201), ("+593 99 044 8031", 201), ("(07) 283-1234", 201), ("123", 400), ("099-ABC-1234", 400), ("+" + "9" * 16, 400)])
def test_phone_format(web, value, status):
    assert web.post(API + "/auth/register", json=registration(phone=value)).status_code == status


# --- SQL injection ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_sql_injection_in_login_is_just_a_wrong_credential(app, web, payload):
    assert web.post(API + "/auth/login", json={"email": payload, "password": payload}).status_code == 401
    assert web.post(API + "/auth/login", json={"email": "ana@example.com", "password": payload}).status_code == 401
    with app.app_context():
        assert UserModel.query.count() == 5


@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_sql_injection_in_free_text_is_stored_literally(app, web, payload):
    login(web, "admin@example.com")
    created = web.post(API + "/training-areas", json={"name": payload})
    assert created.status_code == 201 and created.json["name"] == payload
    with app.app_context():
        assert TrainingAreaModel.query.filter_by(name=payload).count() == 1
        assert UserModel.query.count() == 5 and CourseModel.query.count() == 1


@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_sql_injection_in_urls_and_filters_finds_nothing(web, payload):
    assert web.get(f"{API}/courses/{payload}").status_code == 404
    login(web, "admin@example.com")
    users = web.get(API + "/auth/users", query_string={"role": payload}).json["users"]
    assert len(users) == 5  # an unknown role is ignored, never interpolated
    assert web.get(API + "/payments/orders", query_string={"status": payload}).status_code == 200


def test_no_sql_is_assembled_from_strings_in_the_application():
    """Guard: every query must go through the ORM with bound parameters."""
    problems = []
    for path in APP_SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("sqlalchemy"):
                if any(alias.name == "text" for alias in node.names):
                    problems.append(f"{path.name}: imports sqlalchemy.text")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"execute", "exec_driver_sql", "text"}:
                first = node.args[0] if node.args else None
                if isinstance(first, (ast.JoinedStr, ast.BinOp, ast.Constant)) or (isinstance(first, ast.Call) and getattr(first.func, "attr", "") == "format"):
                    problems.append(f"{path.name}:{node.lineno} builds SQL from a string")
    assert problems == []


# --- Control characters ----------------------------------------------------------------------

def test_control_characters_are_rejected_before_reaching_the_database(web):
    assert web.get(API + "/courses/curso%00base").status_code == 400
    assert web.get(API + "/courses", query_string={"q": "a\x00b"}).status_code == 400
    assert web.post(API + "/auth/login", json={"email": "ana@example.com\x00", "password": "x"}).status_code == 401
    assert web.post(API + "/auth/forgot-password", json={"email": "ana\x00@example.com"}).status_code == 200
    login(web, "admin@example.com")
    assert web.post(API + "/training-areas", json={"name": "Área\x00"}).status_code == 400
    response = web.put(API + "/courses/curso-base", json={"fullDescription": "Línea 1\nLínea 2\tcon tab"})
    assert response.status_code == 200 and response.json["fullDescription"] == "Línea 1\nLínea 2\tcon tab"
    assert web.put(API + "/courses/curso-base", json={"fullDescription": "x\x07"}).status_code == 400


def test_unsafe_urls_are_rejected(web):
    login(web, "admin@example.com")
    for url in ["javascript:alert(1)", "data:text/html,<script>", "//evil.example/x.png", "ftp://x/y"]:
        assert web.put(API + "/courses/curso-base", json={"coverUrl": url}).status_code == 400
    assert web.put(API + "/courses/curso-base", json={"coverUrl": "/api/v1/uploads/portada.png"}).status_code == 200


# --- Error contract --------------------------------------------------------------------------

def test_errors_always_answer_json(lenient_web, monkeypatch):
    missing = lenient_web.get(API + "/no-existe")
    assert missing.status_code == 404 and missing.is_json
    assert lenient_web.delete(API + "/health").status_code == 405
    monkeypatch.setattr(api_module, "serialize_course", lambda *a, **k: 1 / 0)
    broken = lenient_web.get(API + "/courses")
    assert broken.status_code == 500 and broken.json["error"] == "server_error"


def test_health_reports_database_outage(app, web, monkeypatch):
    def down(*_args, **_kwargs):
        raise RuntimeError("connection refused")

    assert web.get(API + "/health").json["status"] == "ok"
    with app.app_context():
        monkeypatch.setattr(db.session, "execute", down)
        response = web.get(API + "/health")
    assert response.status_code == 503 and response.json["database"] == "unavailable"


# --- DEF-05: editing content keeps progress --------------------------------------------------

def test_editing_course_content_keeps_student_progress(app, web):
    enrollment_id, lessons, _ = enroll(app)
    login(web, "ana@example.com")
    web.post(f"{API}/student/enrollments/{enrollment_id}/lessons/{lessons[0]}/complete")
    web.post(API + "/auth/logout")
    login(web, "admin@example.com")
    modules = web.get(API + "/courses/curso-base/author").json["modules"]
    modules[0]["lessons"][0]["title"] = "Lección 1 (corregida)"
    modules[0]["lessons"].append({"title": "Lección nueva", "type": "text", "id": "00000000-0000-0000-0000-000000000000"})
    modules.append({"title": "Módulo 2", "lessons": [{"title": "Otra", "type": "text"}]})
    saved = web.put(API + "/courses/curso-base/content", json={"modules": modules}).json["modules"]
    assert saved[0]["lessons"][0]["id"] == lessons[0] and saved[0]["lessons"][0]["title"] == "Lección 1 (corregida)"
    assert saved[0]["lessons"][1]["id"] == lessons[1]
    assert saved[0]["lessons"][2]["id"] != "00000000-0000-0000-0000-000000000000"  # unknown ids become new rows
    with app.app_context():
        assert LessonProgressModel.query.count() == 1
    # Removing a lesson deletes it (and only its progress).
    saved[0]["lessons"] = saved[0]["lessons"][1:]
    web.put(API + "/courses/curso-base/content", json={"modules": saved})
    with app.app_context():
        assert LessonProgressModel.query.count() == 0
        assert sum(len(module.lessons) for module in CourseModel.query.one().modules) == 3


# --- DEF-06: courses with history cannot be deleted ------------------------------------------

def test_courses_with_enrollments_or_payments_cannot_be_deleted(app, web):
    login(web, "admin@example.com")
    enroll(app)
    response = web.delete(API + "/courses/curso-base")
    assert response.status_code == 409 and "Ciérralo" in response.json["message"]
    with app.app_context():
        assert CourseModel.query.count() == 1
    empty = web.post(API + "/courses", json={"name": "Vacío", "trainingAreaId": area_id(app)}).json["slug"]
    assert web.delete(f"{API}/courses/{empty}").status_code == 204


def test_courses_with_only_payments_cannot_be_deleted(app, web):
    login(web, "admin@example.com")
    with app.app_context():
        student = UserModel.query.filter_by(email="luis@example.com").one()
        course = CourseModel.query.one()
        db.session.add(PaymentOrderModel(reference="TRF-1", course=course, student=student, payment_method="TRANSFER", amount=10, status="REJECTED"))
        db.session.commit()
    assert web.delete(API + "/courses/curso-base").status_code == 409


# --- DEF-07 / DEF-08: login budget -----------------------------------------------------------

def login_attempt(web, password, address="10.0.0.1", email="ana@example.com"):
    return web.post(API + "/auth/login", json={"email": email, "password": password}, environ_base={"REMOTE_ADDR": address})


def test_failed_logins_are_counted_before_the_password_check(app_factory):
    web = app_factory(RATELIMIT_ENABLED=True).test_client()
    assert [login_attempt(web, "Mala1234").status_code for _ in range(10)] == [401] * 10
    blocked = login_attempt(web, "Seguro123")
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0


def test_a_successful_login_resets_the_failed_counter(app_factory):
    web = app_factory(RATELIMIT_ENABLED=True).test_client()
    for _ in range(9):
        login_attempt(web, "Mala1234")
    assert login_attempt(web, "Seguro123").status_code == 200
    assert [login_attempt(web, "Mala1234").status_code for _ in range(10)] == [401] * 10


def test_an_attacker_cannot_lock_out_the_owner_from_another_network(app_factory):
    web = app_factory(RATELIMIT_ENABLED=True).test_client()
    for _ in range(10):
        login_attempt(web, "Mala1234", address="203.0.113.9")
    assert login_attempt(web, "Mala1234", address="203.0.113.9").status_code == 429
    assert login_attempt(web, "Seguro123", address="190.152.1.20").status_code == 200


def test_distributed_guessing_is_capped_per_account(app_factory):
    web = app_factory(RATELIMIT_ENABLED=True, RATELIMIT_LOGIN="1000 per minute").test_client()
    for attempt in range(50):
        assert login_attempt(web, "Mala1234", address=f"198.51.100.{attempt}").status_code == 401
    assert login_attempt(web, "Mala1234", address="198.51.100.200").status_code == 429
