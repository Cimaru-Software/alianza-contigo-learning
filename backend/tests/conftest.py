"""Shared fixtures for the white-box, regression and input-security suites."""
from tempfile import TemporaryDirectory

import pytest

from app import create_app
from app.extensions import db
from app.infrastructure.persistence.models import (
    CourseModel,
    CourseModuleModel,
    EnrollmentModel,
    ExamQuestionModel,
    FinalExamModel,
    LessonModel,
    TrainingAreaModel,
    UserModel,
)

PASSWORD = "Seguro123"


def cedula(sequence: int, province: int = 17) -> str:
    """A valid Ecuadorian cédula (Registro Civil modulo-10) built from a sequence number."""
    body = f"{province:02d}1{sequence % 1_000_000:06d}"
    total = sum((d * c - 9) if d * c > 9 else d * c for d, c in zip(map(int, body), (2, 1, 2, 1, 2, 1, 2, 1, 2)))
    return body + str((10 - total % 10) % 10)


class WhiteboxConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = ["http://localhost:5173"]
    JWT_SECRET_KEY = "test-secret-that-is-at-least-32-characters"
    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_COOKIE_CSRF_PROTECT = False
    JWT_COOKIE_SECURE = False
    JWT_ACCESS_COOKIE_NAME = "alianza_access_token"
    JWT_REFRESH_COOKIE_NAME = "alianza_refresh_token"
    EMAIL_ADDRESS = ""
    EMAIL_PASSWORD = ""
    MAIL_RECIPIENT = ""
    FRONTEND_URL = "http://localhost:5173"
    MAX_DOCUMENT_UPLOAD_MB = 25
    MAX_VIDEO_UPLOAD_MB = 500
    PAYPHONE_TOKEN = ""
    PAYPHONE_STORE_ID = ""
    RATELIMIT_ENABLED = False


@pytest.fixture
def app_factory():
    """Build seeded apps with config overrides, e.g. app_factory(RATELIMIT_ENABLED=True)."""
    with TemporaryDirectory() as uploads:
        def build(**overrides):
            config = type("Config", (WhiteboxConfig,), {"UPLOAD_FOLDER": uploads, **overrides})
            application = create_app(config)
            with application.app_context():
                db.create_all()
                seed_people_and_course()
            return application

        yield build


@pytest.fixture
def app(app_factory):
    return app_factory()


@pytest.fixture
def web(app):
    return app.test_client()


@pytest.fixture
def lenient_web(app):
    """Client that receives 500 responses instead of re-raised exceptions."""
    app.testing = False
    app.config["PROPAGATE_EXCEPTIONS"] = False
    return app.test_client()


def make_user(email, role, first_name="Ana", active=True):
    user = UserModel(first_name=first_name, last_name="Prueba", email=email, role=role, is_active=active)
    user.set_password(PASSWORD)
    db.session.add(user)
    return user


def seed_people_and_course():
    make_user("admin@example.com", "admin", "Admin")
    make_user("teacher@example.com", "teacher", "Docente")
    make_user("ana@example.com", "student", "Ana")
    make_user("luis@example.com", "student", "Luis")
    make_user("inactivo@example.com", "student", "Inactivo", active=False)
    area = TrainingAreaModel(name="Formación general")
    db.session.add(
        CourseModel(
            training_area=area,
            slug="curso-base",
            name="Curso base",
            short_description="Curso activo",
            full_description="",
            modality="Virtual",
            duration="10 horas",
            certification="Certificado",
            endorsement="Aval de prueba",
            price=100,
            discount_percent=10,
            status="ACTIVO",
            modules=[
                CourseModuleModel(
                    title="Módulo 1",
                    position=0,
                    lessons=[
                        LessonModel(title="Lección 1", lesson_type="text", content="Contenido pagado", position=0, is_preview=True),
                        LessonModel(title="Lección 2", lesson_type="video", media_url="/api/v1/uploads/v.mp4", position=1),
                    ],
                )
            ],
            final_exam=FinalExamModel(
                title="Examen final",
                passing_score=70,
                attempts_allowed=2,
                questions=[
                    ExamQuestionModel(prompt="Pregunta uno", options=["Correcta", "Incorrecta"], correct_answers=[0], points=1, position=0),
                    ExamQuestionModel(prompt="Pregunta dos", options=["Correcta", "Incorrecta"], correct_answers=[0], points=1, position=1),
                ],
            ),
        )
    )
    db.session.commit()


def login(web, email, role=None):
    response = web.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, **({"role": role} if role else {})})
    assert response.status_code == 200, response.json
    return response


def enroll(app, email="ana@example.com", slug="curso-base"):
    with app.app_context():
        student = UserModel.query.filter_by(email=email).one()
        course = CourseModel.query.filter_by(slug=slug).one()
        enrollment = EnrollmentModel(course_id=course.id, student_id=student.id)
        db.session.add(enrollment)
        db.session.commit()
        lessons = [str(lesson.id) for module in course.modules for lesson in module.lessons]
        questions = [str(question.id) for question in course.final_exam.questions] if course.final_exam else []
        return str(enrollment.id), lessons, questions


def area_id(app):
    with app.app_context():
        return str(TrainingAreaModel.query.first().id)
