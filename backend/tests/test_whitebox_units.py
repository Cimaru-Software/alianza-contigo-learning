"""White-box unit tests: internal helpers exercised branch by branch, without HTTP."""
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from flask_jwt_extended import create_access_token

from app import config as config_module
from app.application.services.course_service import CourseService
from app.extensions import db, request_email, user_or_ip
from app.infrastructure import email_service
from app.infrastructure.persistence.models import CourseModel, PaymentOrderModel, UserModel
from app.infrastructure.persistence.repositories import SqlAlchemyCourseRepository
from app.presentation import api, auth_api, exam_api, payment_api


# --- auth_api.clean_text / password_is_valid -------------------------------------------------

@pytest.mark.parametrize(
    "value, expected",
    [(None, ""), (123, None), (["x"], None), ("  hola  ", "hola"), ("a" * 5, "a" * 5), ("a" * 6, None), ("   ", "")],
)
def test_clean_text_branches(value, expected):
    assert auth_api.clean_text(value, 5) == expected


@pytest.mark.parametrize(
    "password, valid",
    [
        ("Abcdef1", False),          # 7 chars: below lower bound
        ("Abcdefg1", True),          # 8 chars: lower bound
        ("A" + "1" * 127, True),     # 128 chars: upper bound
        ("A" + "1" * 128, False),    # 129 chars: above upper bound
        ("abcdefgh", False),         # no digit
        ("12345678", False),         # no letter
        (12345678, False),           # not a string
        (None, False),
    ],
)
def test_password_policy_boundaries(password, valid):
    assert auth_api.password_is_valid(password) is valid


# --- api.slugify -----------------------------------------------------------------------------

def test_slugify_normalizes_and_falls_back_to_random_slug():
    assert api.slugify("  Gestor Empresarial 2026 ") == "gestor-empresarial-2026"
    assert api.slugify("A -- B") == "a-b"
    fallback = api.slugify("!!!")
    assert fallback.startswith("curso-") and len(fallback) == len("curso-") + 8


# --- payment_api.final_price -----------------------------------------------------------------

@pytest.mark.parametrize(
    "price, discount, expected",
    [("100", 10, "90.00"), ("99.99", 15, "84.99"), ("80", 0, "80.00"), ("80", 100, "0.00"), ("0.01", 50, "0.01"), ("29.90", 25, "22.43"), ("59.90", 15, "50.92")],  # ROUND_HALF_UP
)
def test_final_price_rounds_to_cents(price, discount, expected):
    course = SimpleNamespace(price=Decimal(price), discount_percent=discount)
    assert payment_api.final_price(course) == Decimal(expected)


# --- progress and exam state calculations ----------------------------------------------------

def stub_enrollment(lessons=4, completed=0, attempts=(), exam=True, attempts_allowed=2, questions=1, completed_at=None):
    module = SimpleNamespace(lessons=[SimpleNamespace(id=i) for i in range(lessons)])
    final_exam = SimpleNamespace(attempts_allowed=attempts_allowed, questions=[object()] * questions) if exam else None
    course = SimpleNamespace(modules=[module], final_exam=final_exam, slug="c", name="Curso", endorsement="", certification="Cert", duration="10 h", id="abcdef12-0000")
    return SimpleNamespace(
        course=course,
        lesson_progress=[object()] * completed,
        exam_attempts=[
            SimpleNamespace(status=status, score=Decimal("80"), attempt_number=n + 1, feedback="fb", submitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc), id=n)
            for n, status in enumerate(attempts)
        ],
        completed_at=completed_at,
        student=SimpleNamespace(first_name="Ana", last_name="Torres"),
        id="123456ab-0000",
    )


@pytest.mark.parametrize(
    "lessons, completed, attempts, expected",
    [(4, 0, (), 0), (4, 2, (), 45), (4, 4, (), 90), (0, 0, (), 90), (4, 1, ("PASSED",), 100), (3, 1, (), 30)],
)
def test_current_enrollment_progress(lessons, completed, attempts, expected):
    assert api.current_enrollment_progress(stub_enrollment(lessons, completed, attempts)) == expected


@pytest.mark.parametrize(
    "attempts, expected",
    [
        ((), "NOT_STARTED"),
        (("FAILED_REVIEWED",), "FAILED_REVIEWED"),
        (("FAILED_REVIEWED", "PENDING_REVIEW"), "PENDING_REVIEW"),
        (("FAILED_REVIEWED", "PASSED"), "PASSED"),
    ],
)
def test_current_exam_status_priority(attempts, expected):
    assert api.current_exam_status(stub_enrollment(attempts=attempts)) == expected


def test_student_exam_state_can_attempt_only_when_every_condition_holds():
    assert exam_api.student_exam_state(stub_enrollment(completed=4))["canAttempt"] is True
    assert exam_api.student_exam_state(stub_enrollment(completed=3))["canAttempt"] is False            # lessons pending
    assert exam_api.student_exam_state(stub_enrollment(completed=4, exam=False))["canAttempt"] is False  # no exam
    assert exam_api.student_exam_state(stub_enrollment(completed=4, questions=0))["canAttempt"] is False  # exam empty
    assert exam_api.student_exam_state(stub_enrollment(completed=4, attempts=("PENDING_REVIEW",)))["canAttempt"] is False
    assert exam_api.student_exam_state(stub_enrollment(completed=4, attempts=("PASSED",)))["canAttempt"] is False
    exhausted = exam_api.student_exam_state(stub_enrollment(completed=4, attempts=("FAILED_REVIEWED", "FAILED_REVIEWED")))
    assert exhausted["canAttempt"] is False and exhausted["attemptsRemaining"] == 0


def test_student_exam_state_hides_score_and_feedback_by_status():
    state = exam_api.student_exam_state(stub_enrollment(completed=4, attempts=("FAILED_REVIEWED", "PASSED")))
    failed, passed = state["attempts"]
    assert failed["score"] is None and failed["feedback"] == "fb"
    assert passed["score"] == 80.0 and passed["feedback"] == ""
    assert state["passedScore"] == 80.0 and state["courseCompleted"] is True


def test_certificate_requires_passed_attempt_and_completion_date():
    assert exam_api.certificate_for(stub_enrollment(attempts=("PASSED",))) is None
    assert exam_api.certificate_for(stub_enrollment(attempts=("FAILED_REVIEWED",), completed_at=datetime(2026, 5, 1))) is None
    certificate = exam_api.certificate_for(stub_enrollment(attempts=("PASSED",), completed_at=datetime(2026, 5, 1)))
    assert certificate["code"] == "AC-2026-ABCDEF-123456"
    assert certificate["endorsement"] == "Cert"  # falls back to certification when there is no endorsement


# --- rate-limit key functions ----------------------------------------------------------------

def test_rate_limit_keys(app):
    with app.test_request_context("/", json={"email": "  ANA@Example.com "}):
        assert request_email() == "email:ana@example.com"
        assert user_or_ip().startswith("ip:")
    with app.test_request_context("/", json=["not", "a", "dict"]):
        assert request_email() == "email:"
    with app.app_context():
        token = create_access_token(identity="user-42")
    with app.test_request_context("/", headers={"Cookie": f"alianza_access_token={token}"}):
        assert user_or_ip() == "user:user-42"
    with app.test_request_context("/", headers={"Cookie": "alianza_access_token=garbage"}):
        assert user_or_ip().startswith("ip:")


# --- configuration guards --------------------------------------------------------------------

def test_production_config_refuses_missing_database_or_default_secret(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setattr(config_module.ProductionConfig, "SQLALCHEMY_DATABASE_URI", "")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        config_module.get_config()
    monkeypatch.setattr(config_module.ProductionConfig, "SQLALCHEMY_DATABASE_URI", "postgresql://x")
    monkeypatch.setattr(config_module.ProductionConfig, "JWT_SECRET_KEY", "change-this-development-secret")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        config_module.get_config()
    monkeypatch.setattr(config_module.ProductionConfig, "JWT_SECRET_KEY", "x" * 64)
    assert config_module.get_config() is config_module.ProductionConfig
    monkeypatch.setenv("FLASK_ENV", "development")
    assert config_module.get_config() is config_module.DevelopmentConfig


# --- repository + application service --------------------------------------------------------

def test_course_service_maps_rows_to_domain_entities(app):
    with app.app_context():
        service = CourseService(SqlAlchemyCourseRepository(db.session, CourseModel))
        courses = service.list_courses()
        assert [course.slug for course in courses] == ["curso-base"]
        course = service.get_course("curso-base")
        assert isinstance(course.price, float) and course.price == 100.0
        assert service.get_course("no-existe") is None


# --- email service ---------------------------------------------------------------------------

def test_branded_html_escapes_title_and_action_url():
    html = email_service.branded_html("<script>x</script>", "Hola", "Cuerpo", "Ir", 'https://x.test/?a="b"')
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html
    assert 'href="https://x.test/?a=&quot;b&quot;"' in html
    assert "background:#C89432;border-radius:9px" not in email_service.branded_html("T", "G", "B")  # no action button


def test_send_html_skips_without_smtp_and_uses_starttls_when_configured(app, monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user))

        def send_message(self, message):
            calls.append(("send", message["To"], message["Subject"]))

    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    with app.app_context():
        assert email_service.send_html("a@b.co", "Asunto", "<p>x</p>") is False
        app.config.update(EMAIL_ADDRESS="bot@x.co", EMAIL_PASSWORD="pw", MAIL_SENDER="Bot", SMTP_SERVER="smtp.x", SMTP_PORT=587)
        assert email_service.send_html("", "Asunto", "<p>x</p>") is False
        assert email_service.send_html("a@b.co", "Asunto", "<p>x</p>") is True
    assert [call[0] for call in calls] == ["connect", "starttls", "login", "send"]


def test_background_delivery_swallows_smtp_failures(app, monkeypatch):
    def explode(*_args):
        raise OSError("smtp down")

    monkeypatch.setattr(email_service, "send_html", explode)
    with app.app_context():
        email_service.send_html_later("a@b.co", "Asunto", "<p>x</p>")  # must not raise


# --- PayPhone confirmation (every branch of confirm_payphone_order) --------------------------

class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *_args):
        return self.body.encode()


def payphone_order(app, status="PENDING", provider_tx=None):
    with app.app_context():
        student = UserModel.query.filter_by(email="ana@example.com").one()
        course = CourseModel.query.filter_by(slug="curso-base").one()
        order = PaymentOrderModel(reference="CARD-REF", course=course, student=student, payment_method="PAYPHONE", provider="PAYPHONE", amount=Decimal("90.00"), status=status, provider_transaction_id=provider_tx)
        db.session.add(order)
        db.session.commit()
        return order.id


def run_confirm(app, order_id, transaction_id="77"):
    with app.app_context():
        order = db.session.get(PaymentOrderModel, order_id)
        return payment_api.confirm_payphone_order(order, transaction_id), order.status


def confirmation(**overrides):
    body = {"clientTransactionId": "CARD-REF", "transactionId": 77, "statusCode": 3, "transactionStatus": "Approved", "currency": "USD", "amount": 9000}
    body.update(overrides)
    return json.dumps(body)


def test_payphone_already_processed_orders_are_idempotent(app):
    order_id = payphone_order(app, "APPROVED", "77")
    assert run_confirm(app, order_id, "77")[0] == "approved"
    assert run_confirm(app, order_id, "78")[0] == "error"


def test_payphone_already_rejected_orders_are_idempotent(app):
    order_id = payphone_order(app, "REJECTED", "77")
    assert run_confirm(app, order_id, "77")[0] == "rejected"
    assert run_confirm(app, order_id, "78")[0] == "error"


def test_payphone_without_token_is_an_error(app):
    order_id = payphone_order(app)
    assert run_confirm(app, order_id) == ("error", "PENDING")


@pytest.mark.parametrize(
    "response, expected_status",
    [
        (URLError("down"), "PENDING"),
        ("[1, 2]", "PENDING"),                                                # not a JSON object
        ("not json", "PENDING"),
        (confirmation(clientTransactionId="OTHER"), "PENDING"),              # inconsistent reference
        (confirmation(currency="EUR"), "PENDING"),                            # wrong currency
        (confirmation(amount=100), "PENDING"),                                # wrong amount
        (confirmation(statusCode=1, transactionStatus="Pending"), "PENDING"),  # unknown state
    ],
)
def test_payphone_never_approves_suspicious_confirmations(app, monkeypatch, response, expected_status):
    app.config["PAYPHONE_TOKEN"] = "token"
    order_id = payphone_order(app)

    def fake_urlopen(_request, timeout):
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)

    monkeypatch.setattr(payment_api, "urlopen", fake_urlopen)
    assert run_confirm(app, order_id) == ("error", expected_status)


def test_payphone_cancellation_rejects_and_approval_enrolls(app, monkeypatch):
    app.config["PAYPHONE_TOKEN"] = "token"
    cancelled = payphone_order(app)
    monkeypatch.setattr(payment_api, "urlopen", lambda _r, timeout: FakeResponse(confirmation(statusCode=2, transactionStatus="Canceled", message="Fondos insuficientes")))
    assert run_confirm(app, cancelled) == ("rejected", "REJECTED")
    with app.app_context():
        assert db.session.get(PaymentOrderModel, cancelled).rejection_comment == "Fondos insuficientes"
        db.session.delete(db.session.get(PaymentOrderModel, cancelled))
        db.session.commit()
    approved = payphone_order(app)
    monkeypatch.setattr(payment_api, "urlopen", lambda _r, timeout: FakeResponse(confirmation()))
    assert run_confirm(app, approved) == ("approved", "APPROVED")
