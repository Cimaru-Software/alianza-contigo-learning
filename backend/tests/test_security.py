from app import create_app
from app.extensions import db
from app.infrastructure.persistence.models import CourseModel, CourseModuleModel, LessonModel, TrainingAreaModel, UserModel
from app.presentation import auth_api


class SecurityTestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = ["http://localhost:5173"]
    JWT_SECRET_KEY = "test-secret-that-is-at-least-32-characters"
    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_COOKIE_CSRF_PROTECT = False
    JWT_COOKIE_SECURE = False
    FRONTEND_URL = "http://localhost:5173"


def client(**overrides):
    config = type("Config", (SecurityTestConfig,), overrides)
    app = create_app(config)
    with app.app_context():
        db.create_all()
    return app.test_client()


def student_payload(email="ana@example.com", **extra):
    return {"firstName": "Ana", "lastName": "Torres", "email": email, "password": "Seguro123", **extra}


def test_duplicate_national_id_returns_conflict_instead_of_server_error():
    web = client()
    assert web.post("/api/v1/auth/register", json=student_payload(nationalId="0102030405")).status_code == 201
    response = web.post("/api/v1/auth/register", json=student_payload("otra@example.com", nationalId="0102030405"))
    assert response.status_code == 409


def test_register_rejects_malformed_input_without_server_error():
    web = client()
    assert web.post("/api/v1/auth/register", json=["not", "an", "object"]).status_code == 400
    assert web.post("/api/v1/auth/register", json=student_payload(firstName="A" * 101)).status_code == 400
    assert web.post("/api/v1/auth/register", json=student_payload(phone=12345)).status_code == 400
    assert web.post("/api/v1/auth/register", json=student_payload(email="no-es-correo")).status_code == 400


def test_failed_logins_for_one_account_are_rate_limited():
    web = client()
    web.post("/api/v1/auth/register", json=student_payload("victima@example.com"))
    for _ in range(10):
        response = web.post("/api/v1/auth/login", json={"email": "victima@example.com", "password": "Incorrecta1"})
        assert response.status_code == 401
    response = web.post("/api/v1/auth/login", json={"email": "victima@example.com", "password": "Incorrecta1"})
    assert response.status_code == 429
    assert response.json["error"] == "rate_limited"
    assert response.headers.get("Retry-After")


def test_successful_logins_do_not_consume_the_failed_login_quota():
    web = client()
    web.post("/api/v1/auth/register", json=student_payload("frecuente@example.com"))
    for _ in range(12):
        assert web.post("/api/v1/auth/login", json={"email": "frecuente@example.com", "password": "Seguro123"}).status_code == 200


def test_registration_limit_per_ip_is_configurable():
    web = client(RATELIMIT_REGISTER="2 per minute")
    assert web.post("/api/v1/auth/register", json=student_payload("a1@example.com")).status_code == 201
    assert web.post("/api/v1/auth/register", json=student_payload("a2@example.com")).status_code == 201
    assert web.post("/api/v1/auth/register", json=student_payload("a3@example.com")).status_code == 429


def test_health_check_is_never_rate_limited():
    web = client(RATELIMIT_DEFAULT="1 per minute")
    for _ in range(3):
        assert web.get("/api/v1/health").status_code == 200


def test_reset_link_works_once_and_revokes_previous_sessions(monkeypatch):
    web = client()
    web.post("/api/v1/auth/register", json=student_payload())
    old_refresh = web.get_cookie(web.application.config["JWT_REFRESH_COOKIE_NAME"]).value
    sent = []
    monkeypatch.setattr(auth_api, "send_html_later", lambda to, subject, html: sent.append(html))
    assert web.post("/api/v1/auth/forgot-password", json={"email": "ana@example.com"}).status_code == 200
    token = sent[0].split("token=")[1].split('"')[0]

    assert web.post("/api/v1/auth/reset-password", json={"token": token, "password": "Nueva1234"}).status_code == 200
    assert web.post("/api/v1/auth/reset-password", json={"token": token, "password": "Otra12345"}).status_code == 400

    web.set_cookie(web.application.config["JWT_REFRESH_COOKIE_NAME"], old_refresh)
    assert web.post("/api/v1/auth/refresh").status_code == 401


def test_session_tokens_cannot_be_used_as_reset_links():
    web = client()
    web.post("/api/v1/auth/register", json=student_payload())
    access = web.get_cookie(web.application.config["JWT_ACCESS_COOKIE_NAME"]).value
    assert web.post("/api/v1/auth/reset-password", json={"token": access, "password": "Nueva1234"}).status_code == 400


def test_change_password_keeps_current_session_valid():
    web = client()
    web.post("/api/v1/auth/register", json=student_payload())
    response = web.post("/api/v1/auth/change-password", json={"currentPassword": "Seguro123", "newPassword": "Nueva1234"})
    assert response.status_code == 200
    assert web.post("/api/v1/auth/refresh").status_code == 200


def test_public_course_detail_hides_paid_lesson_content():
    web = client()
    with web.application.app_context():
        course = CourseModel(training_area=TrainingAreaModel(name="General"), slug="curso", name="Curso", short_description="", modality="Virtual", duration="1h", certification="Cert", status="ACTIVO")
        module = CourseModuleModel(title="Módulo", position=0)
        module.lessons = [
            LessonModel(title="Vista previa", lesson_type="video", content="Introducción", media_url="/api/v1/uploads/intro.mp4", is_preview=True, position=0),
            LessonModel(title="Pagada", lesson_type="interactive", content="Contenido pagado", media_url="/api/v1/uploads/privado.mp4", interaction_data={"correctAnswers": [1]}, position=1),
        ]
        course.modules.append(module)
        db.session.add(course)
        db.session.commit()
    data = web.get("/api/v1/courses/curso").json
    preview, paid = data["modules"][0]["lessons"]
    assert preview["mediaUrl"] == "/api/v1/uploads/intro.mp4"
    assert paid["title"] == "Pagada"
    assert paid["content"] == "" and paid["mediaUrl"] is None and paid["interaction"] is None
    assert "finalExam" not in data
