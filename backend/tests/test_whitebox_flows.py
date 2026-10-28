"""White-box flow tests: each test targets specific branches of the HTTP handlers."""
from datetime import timedelta
from io import BytesIO

import pytest
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.infrastructure.persistence.models import CourseModel, LessonModel, UserModel
from tests.conftest import area_id, cedula, enroll, login

API = "/api/v1"


# --- role-based access control ---------------------------------------------------------------

ADMIN_ONLY = [
    ("get", "/admin/dashboard"), ("get", "/admin/students"), ("post", "/courses"), ("put", "/courses/curso-base"),
    ("delete", "/courses/curso-base"), ("put", "/courses/curso-base/content"), ("put", "/courses/curso-base/exam"),
    ("get", "/courses/curso-base/author"), ("post", "/training-areas"), ("post", "/uploads"),
    ("get", "/auth/users"), ("post", "/auth/teachers"), ("get", "/payments/orders"), ("get", "/payments/admin/summary"),
]
STUDENT_ONLY = [
    ("get", "/student/enrollments"), ("get", "/exams/student/certificates"),
    ("get", "/payments/bank-details"), ("post", "/payments/card"),
]
STAFF_ONLY = [("get", "/courses/manage"), ("get", "/exams/teacher/attempts"), ("get", "/courses/curso-base/teaching")]


@pytest.mark.parametrize("method, path", ADMIN_ONLY + STUDENT_ONLY + STAFF_ONLY)
def test_anonymous_requests_need_a_session(web, method, path):
    response = getattr(web, method)(API + path, json={})
    assert response.status_code == 401
    assert response.json["error"] == "session_required"


@pytest.mark.parametrize("method, path", ADMIN_ONLY + STAFF_ONLY)
def test_students_cannot_reach_staff_endpoints(web, method, path):
    login(web, "ana@example.com")
    assert getattr(web, method)(API + path, json={}).status_code == 403


@pytest.mark.parametrize("method, path", ADMIN_ONLY)
def test_teachers_cannot_reach_admin_endpoints(web, method, path):
    login(web, "teacher@example.com")
    assert getattr(web, method)(API + path, json={}).status_code == 403


@pytest.mark.parametrize("method, path", STUDENT_ONLY)
def test_admins_cannot_act_as_students(web, method, path):
    login(web, "admin@example.com")
    assert getattr(web, method)(API + path, json={}).status_code == 403


def test_jwt_error_handlers(app, web):
    web.set_cookie("alianza_access_token", "not-a-jwt")
    assert web.get(API + "/auth/me").json["error"] == "invalid_token"
    with app.app_context():
        expired = create_access_token(identity="x", expires_delta=timedelta(seconds=-1))
    web.set_cookie("alianza_access_token", expired)
    response = web.get(API + "/auth/me")
    assert response.status_code == 401 and response.json["error"] == "token_expired"


# --- authentication branches -----------------------------------------------------------------

def test_login_branches(web):
    assert web.post(API + "/auth/login", json={"email": "nadie@example.com", "password": "x"}).status_code == 401
    assert web.post(API + "/auth/login", json={"email": "ana@example.com", "password": "Incorrecta1"}).status_code == 401
    assert web.post(API + "/auth/login", json={"email": "inactivo@example.com", "password": "Seguro123"}).json["error"] == "inactive_account"
    assert web.post(API + "/auth/login", json={"email": "ana@example.com", "password": "Seguro123", "role": "admin"}).json["error"] == "wrong_portal"
    assert web.post(API + "/auth/login", json={"email": "  ANA@EXAMPLE.COM ", "password": "Seguro123"}).status_code == 200


def test_register_rejects_duplicates_and_missing_fields(web):
    base = {"firstName": "Eva", "lastName": "Luna", "email": "eva@example.com", "password": "Seguro123", "nationalId": cedula(1)}
    assert web.post(API + "/auth/register", json={**base, "firstName": ""}).status_code == 400
    assert web.post(API + "/auth/register", json={**base, "password": "corta"}).status_code == 400
    assert web.post(API + "/auth/register", json={**base, "email": "ANA@example.com"}).status_code == 409
    assert web.post(API + "/auth/register", json={**base, "nationalId": ""}).status_code == 400   # cédula required
    assert web.post(API + "/auth/register", json={**base, "nationalId": "1710034066"}).status_code == 400  # bad check digit
    assert web.post(API + "/auth/register", json=base).status_code == 201
    assert web.post(API + "/auth/register", json={**base, "email": "otra@example.com"}).status_code == 409  # same cédula


def test_profile_update_and_password_change(web):
    login(web, "ana@example.com")
    response = web.patch(API + "/auth/profile", json={"firstName": " Ana María ", "lastName": "", "phone": "", "avatarKey": "gold"})
    user = response.json["user"]
    assert user["firstName"] == "Ana María" and user["lastName"] == "Prueba" and user["phone"] is None and user["avatarKey"] == "gold"
    assert web.patch(API + "/auth/profile", json={"avatarKey": "rainbow"}).json["user"]["avatarKey"] == "gold"
    assert web.patch(API + "/auth/profile", json={"firstName": "x" * 101}).status_code == 400
    assert web.post(API + "/auth/change-password", json={"currentPassword": "mala", "newPassword": "Nueva2026"}).json["error"] == "wrong_password"
    assert web.post(API + "/auth/change-password", json={"currentPassword": "Seguro123", "newPassword": "debil"}).status_code == 400
    assert web.post(API + "/auth/change-password", json={"currentPassword": "Seguro123", "newPassword": "Nueva2026"}).status_code == 200
    assert web.post(API + "/auth/login", json={"email": "ana@example.com", "password": "Nueva2026"}).status_code == 200


def test_refresh_rejected_for_deactivated_user(app, web):
    login(web, "ana@example.com")
    assert web.post(API + "/auth/refresh").status_code == 200
    with app.app_context():
        UserModel.query.filter_by(email="ana@example.com").one().is_active = False
        db.session.commit()
    assert web.post(API + "/auth/refresh").json["error"] == "session_invalid"
    assert web.get(API + "/auth/me").status_code == 401


def test_forgot_password_does_not_reveal_unknown_accounts(web, monkeypatch):
    from app.presentation import auth_api

    sent = []
    monkeypatch.setattr(auth_api, "send_html_later", lambda *args: sent.append(args))
    unknown = web.post(API + "/auth/forgot-password", json={"email": "nadie@example.com"})
    known = web.post(API + "/auth/forgot-password", json={"email": "ana@example.com"})
    assert unknown.status_code == known.status_code == 200
    assert unknown.json == known.json
    assert len(sent) == 1
    assert web.post(API + "/auth/reset-password", json={"token": "basura", "password": "Nueva2026"}).json["error"] == "invalid_token"
    assert web.post(API + "/auth/reset-password", json={"token": 42, "password": "Nueva2026"}).status_code == 400


# --- training areas --------------------------------------------------------------------------

def test_training_area_crud(app, web):
    login(web, "admin@example.com")
    assert web.post(API + "/training-areas", json={"name": ""}).status_code == 400
    assert web.post(API + "/training-areas", json={"name": "x" * 121}).status_code == 400
    assert web.post(API + "/training-areas", json={"name": "FORMACIÓN GENERAL"}).status_code == 409  # case-insensitive
    created = web.post(API + "/training-areas", json={"name": "Salud"})
    assert created.status_code == 201
    new_id = created.json["id"]
    assert web.put(API + "/training-areas/no-uuid", json={"name": "X"}).status_code == 404
    assert web.put(f"{API}/training-areas/{new_id}", json={"name": ""}).status_code == 400
    assert web.put(f"{API}/training-areas/{new_id}", json={"name": "formación general"}).status_code == 409
    assert web.put(f"{API}/training-areas/{new_id}", json={"name": "Salud ocupacional"}).json["name"] == "Salud ocupacional"
    assert web.delete(f"{API}/training-areas/{area_id(app)}").status_code == 409  # has courses
    assert web.delete(f"{API}/training-areas/{new_id}").status_code == 204
    assert web.delete(f"{API}/training-areas/{new_id}").status_code == 404
    names = [area["name"] for area in web.get(API + "/training-areas").json]
    assert names == ["Formación general"]


# --- course authoring ------------------------------------------------------------------------

def test_course_lifecycle_from_draft_to_active_and_deleted(app, web):
    login(web, "admin@example.com")
    area = area_id(app)
    assert web.post(API + "/courses", json={"name": " "}).status_code == 400
    assert web.post(API + "/courses", json={"name": "Nuevo", "status": "ACTIVO", "trainingAreaId": area}).status_code == 400
    assert web.post(API + "/courses", json={"name": "Nuevo", "trainingAreaId": "no-uuid"}).status_code == 400
    first = web.post(API + "/courses", json={"name": "Curso Base", "trainingAreaId": area, "discountPercent": 150})
    assert first.status_code == 201 and first.json["slug"] == "curso-base-2" and first.json["status"] == "CERRADO"
    assert first.json["discountPercent"] == 100
    slug = first.json["slug"]

    assert web.put(f"{API}/courses/{slug}", json={"trainingAreaId": "bad"}).status_code == 400
    assert web.put(f"{API}/courses/{slug}", json={"price": "abc"}).status_code == 400
    assert web.put(f"{API}/courses/{slug}", json={"price": -5}).status_code == 400
    updated = web.put(f"{API}/courses/{slug}", json={"price": "49.90", "discountPercent": -3, "modality": "Híbrido"}).json
    assert updated["price"] == 49.9 and updated["discountPercent"] == 0 and updated["modality"] == "Híbrido"
    assert web.put(f"{API}/courses/{slug}", json={"status": "ACTIVO"}).status_code == 400  # no modules / questions

    content = {"modules": [{"title": "", "lessons": [
        {"title": "Video", "type": "video", "mediaUrl": "/api/v1/uploads/v.mp4", "durationMinutes": -4, "isPreview": True},
        {"title": "Actividad", "type": "interactive", "interaction": {"type": "true_false", "options": ["Verdadero", "Falso"], "correctAnswers": [1]}},
        {"title": "Raro", "type": "flash", "interaction": {"type": "x"}},
    ]}]}
    unsolvable = {"modules": [{"title": "M", "lessons": [{"title": "A", "type": "interactive", "interaction": {"type": "true_false", "correctAnswers": [1]}}]}]}
    assert web.put(f"{API}/courses/{slug}/content", json=unsolvable).status_code == 400
    unsafe_media = {"modules": [{"title": "M", "lessons": [{"title": "V", "type": "video", "mediaUrl": "javascript:alert(1)"}]}]}
    assert web.put(f"{API}/courses/{slug}/content", json=unsafe_media).status_code == 400
    modules = web.put(f"{API}/courses/{slug}/content", json=content).json["modules"]
    lessons = modules[0]["lessons"]
    assert modules[0]["title"] == "Módulo 1"
    assert lessons[0]["durationMinutes"] == 0 and lessons[0]["isPreview"] is True
    assert lessons[1]["interaction"]["options"] == ["Verdadero", "Falso"] and lessons[1]["interaction"]["correctAnswers"] == [1]
    assert lessons[2]["type"] == "text" and lessons[2]["interaction"] is None

    assert web.put(f"{API}/courses/{slug}/exam", json={"questions": []}).status_code == 400
    assert web.put(f"{API}/courses/{slug}/exam", json={"questions": [{"prompt": "P", "options": ["a"], "correctAnswers": [0]}]}).status_code == 400
    exam = web.put(f"{API}/courses/{slug}/exam", json={"timeLimitMinutes": 0, "attemptsAllowed": 0, "passingScore": 500, "questions": [{"prompt": " P ", "options": ["a", "b"], "correctAnswers": [1], "points": 0}]}).json
    assert (exam["timeLimitMinutes"], exam["attemptsAllowed"], exam["passingScore"]) == (45, 1, 100)
    assert exam["questions"][0]["points"] == 1 and exam["questions"][0]["correctAnswers"] == [1]

    assert web.put(f"{API}/courses/{slug}", json={"status": "ACTIVO"}).json["status"] == "ACTIVO"
    assert web.put(f"{API}/courses/{slug}/content", json={"modules": []}).status_code == 400  # active needs modules

    public = web.get(f"{API}/courses/{slug}").json
    assert "finalExam" not in public
    assert public["modules"][0]["lessons"][1]["interaction"] is None  # paid activity answers stay private
    author = web.get(f"{API}/courses/{slug}/author").json
    assert author["finalExam"]["questions"][0]["correctAnswers"] == [1]
    assert web.get(API + "/courses/no-existe/author").status_code == 404

    assert web.delete(f"{API}/courses/{slug}").status_code == 204
    assert web.get(f"{API}/courses/{slug}").status_code == 404


def test_closed_courses_are_hidden_from_public_catalog(app, web):
    with app.app_context():
        CourseModel.query.filter_by(slug="curso-base").one().status = "CERRADO"
        db.session.commit()
    assert web.get(API + "/courses").json == []
    assert web.get(API + "/courses/curso-base").status_code == 404
    login(web, "teacher@example.com")
    assert [course["slug"] for course in web.get(API + "/courses/manage").json] == ["curso-base"]


# --- uploads ---------------------------------------------------------------------------------

def test_upload_validation_and_serving(app, web):
    login(web, "admin@example.com")
    assert web.post(API + "/uploads", data={}, content_type="multipart/form-data").status_code == 400
    bad = web.post(API + "/uploads", data={"file": (BytesIO(b"<svg/>"), "logo.svg")}, content_type="multipart/form-data")
    assert bad.status_code == 400
    ok = web.post(API + "/uploads", data={"file": (BytesIO(b"%PDF-1.4"), "../../guía final.pdf")}, content_type="multipart/form-data")
    assert ok.status_code == 201
    url = ok.json["url"]
    assert "/../" not in url and url.endswith("-guia_final.pdf")
    assert web.get(url).data == b"%PDF-1.4"
    app.config["MAX_DOCUMENT_UPLOAD_MB"] = 0
    too_big = web.post(API + "/uploads", data={"file": (BytesIO(b"x" * 10), "a.pdf")}, content_type="multipart/form-data")
    assert too_big.status_code == 413


def test_global_upload_ceiling_returns_json_413(app, web):
    login(web, "admin@example.com")
    app.config["MAX_CONTENT_LENGTH"] = 10
    response = web.post(API + "/uploads", data={"file": (BytesIO(b"x" * 100), "a.pdf")}, content_type="multipart/form-data")
    assert response.status_code == 413 and "tamaño máximo" in response.json["message"]


# --- sequential learning ---------------------------------------------------------------------

def complete(web, enrollment_id, lesson_id, **body):
    return web.post(f"{API}/student/enrollments/{enrollment_id}/lessons/{lesson_id}/complete", json=body)


def test_lessons_unlock_strictly_in_order(app, web):
    enrollment_id, lessons, _ = enroll(app)
    login(web, "ana@example.com")
    assert complete(web, "bad", lessons[0]).status_code == 404
    assert complete(web, enrollment_id, "00000000-0000-0000-0000-000000000000").status_code == 404
    assert complete(web, enrollment_id, lessons[1]).status_code == 409   # skipping ahead
    first = complete(web, enrollment_id, lessons[0]).json
    assert first["progressPercent"] == 45
    assert complete(web, enrollment_id, lessons[0]).json["progressPercent"] == 45  # idempotent
    assert complete(web, enrollment_id, lessons[1]).json["progressPercent"] == 90
    enrollments = web.get(API + "/student/enrollments").json["enrollments"]
    assert enrollments[0]["progressPercent"] == 90 and enrollments[0]["examStatus"] == "NOT_STARTED"
    assert enrollments[0]["course"]["modules"][0]["lessons"][1]["mediaUrl"] == "/api/v1/uploads/v.mp4"  # enrolled sees media


def test_students_cannot_touch_other_students_enrollments(app, web):
    enrollment_id, lessons, _ = enroll(app, "luis@example.com")
    login(web, "ana@example.com")
    assert complete(web, enrollment_id, lessons[0]).status_code == 404
    assert web.get(f"{API}/exams/student/enrollments/{enrollment_id}").status_code == 404
    assert web.post(f"{API}/exams/student/enrollments/{enrollment_id}/submit", json={}).status_code == 404
    assert web.get(f"{API}/exams/student/certificates/{enrollment_id}/pdf").status_code == 404


@pytest.mark.parametrize(
    "interaction, wrong, right",
    [
        ({"type": "multiple_choice", "options": ["a", "b"], "correctAnswers": [1]}, 0, 1),
        ({"type": "true_false", "correctAnswers": [0]}, 1, 0),
        ({"type": "ordering", "options": ["a", "b", "c"]}, [2, 1, 0], [0, 1, 2]),
        ({"type": "matching", "pairs": [{"left": "a", "right": "1"}, {"left": "b", "right": "2"}]}, [1, 0], [0, 1]),
        ({"type": "desconocido"}, 0, None),
    ],
)
def test_interactive_lessons_require_the_correct_answer(app, web, interaction, wrong, right):
    with app.app_context():
        lesson = LessonModel.query.filter_by(title="Lección 1").one()
        lesson.lesson_type = "interactive"
        lesson.interaction_data = interaction
        db.session.commit()
    enrollment_id, lessons, _ = enroll(app)
    login(web, "ana@example.com")
    assert complete(web, enrollment_id, lessons[0], interactionAnswer=wrong).status_code == 422
    if right is not None:
        assert complete(web, enrollment_id, lessons[0], interactionAnswer=right).status_code == 200


# --- final exam, teacher review and certificate ----------------------------------------------

def submit(web, enrollment_id, answers):
    return web.post(f"{API}/exams/student/enrollments/{enrollment_id}/submit", json={"answers": answers})


def test_exam_review_retry_and_certificate(app, web):
    enrollment_id, lessons, questions = enroll(app)
    login(web, "ana@example.com")
    state = web.get(f"{API}/exams/student/enrollments/{enrollment_id}").json
    assert state["state"]["canAttempt"] is False and "correctAnswers" not in state["exam"]["questions"][0]
    assert submit(web, enrollment_id, {}).status_code == 409   # lessons pending
    for lesson in lessons:
        complete(web, enrollment_id, lesson)
    assert submit(web, enrollment_id, {questions[0]: 0}).status_code == 400          # missing answer
    assert submit(web, enrollment_id, {questions[0]: 0, questions[1]: 7}).status_code == 400   # out of range
    assert submit(web, enrollment_id, {questions[0]: 0, questions[1]: "x"}).status_code == 400  # not a number

    failed = submit(web, enrollment_id, {questions[0]: 0, questions[1]: 1})  # 50 < 70
    assert failed.json["status"] == "PENDING_REVIEW"
    assert submit(web, enrollment_id, {questions[0]: 0, questions[1]: 0}).status_code == 409  # waiting for review
    assert web.get(API + "/exams/student/certificates").json["certificates"] == []

    web.post(API + "/auth/logout")
    login(web, "teacher@example.com")
    pending = web.get(API + "/exams/teacher/attempts").json["attempts"]
    assert len(pending) == 1 and pending[0]["score"] == 50.0
    attempt_id = pending[0]["id"]
    assert web.get(API + "/exams/teacher/attempts/no-uuid").status_code == 404
    assert "questions" in web.get(f"{API}/exams/teacher/attempts/{attempt_id}").json
    assert web.patch(f"{API}/exams/teacher/attempts/{attempt_id}/review", json={"feedback": "  "}).status_code == 400
    reviewed = web.patch(f"{API}/exams/teacher/attempts/{attempt_id}/review", json={"feedback": "Repasa el módulo 1"})
    assert reviewed.json["attemptsRemaining"] == 1
    assert web.patch(f"{API}/exams/teacher/attempts/{attempt_id}/review", json={"feedback": "otra"}).status_code == 400
    teaching = web.get(API + "/courses/curso-base/teaching").json["students"][0]
    assert teaching["examStatus"] == "FAILED_REVIEWED" and teaching["teacherFeedback"] == "Repasa el módulo 1"
    assert web.patch(f"{API}/enrollments/{enrollment_id}/grade", json={}).status_code == 410

    web.post(API + "/auth/logout")
    login(web, "ana@example.com")
    passed = submit(web, enrollment_id, {questions[0]: 0, questions[1]: 0})
    assert passed.json == {"passed": True, "score": 100.0, "courseCompleted": True, "message": "¡Aprobaste el examen final!"}
    assert submit(web, enrollment_id, {questions[0]: 0, questions[1]: 0}).status_code == 409  # already passed
    certificates = web.get(API + "/exams/student/certificates").json["certificates"]
    assert len(certificates) == 1 and certificates[0]["score"] == 100.0
    pdf = web.get(f"{API}/exams/student/certificates/{enrollment_id}/pdf")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf" and pdf.data.startswith(b"%PDF")

    web.post(API + "/auth/logout")
    login(web, "teacher@example.com")
    assert len(web.get(API + "/exams/teacher/attempts?status=PASSED").json["attempts"]) == 1
    assert len(web.get(API + "/exams/teacher/attempts?status=ALL").json["attempts"]) == 2


def test_exam_not_configured_returns_404(app, web):
    with app.app_context():
        db.session.delete(CourseModel.query.filter_by(slug="curso-base").one().final_exam)
        db.session.commit()
    enrollment_id, _, _ = enroll(app)
    login(web, "ana@example.com")
    assert web.get(f"{API}/exams/student/enrollments/{enrollment_id}").status_code == 404


# --- admin reporting -------------------------------------------------------------------------

def test_admin_dashboard_and_student_detail(app, web):
    enroll(app)
    login(web, "admin@example.com")
    stats = web.get(API + "/admin/dashboard").json
    assert stats["stats"]["students"] == 3 and stats["stats"]["activeStudents"] == 2
    assert stats["stats"]["enrollments"] == 1 and len(stats["enrollmentsByMonth"]) == 6
    assert stats["enrollmentsByMonth"][-1]["enrollments"] == 1
    students = web.get(API + "/admin/students").json["students"]
    ana = next(student for student in students if student["email"] == "ana@example.com")
    assert ana["coursesCount"] == 1
    assert web.get(f"{API}/admin/students/{ana['id']}").json["enrollments"][0]["progressPercent"] == 0
    assert web.get(API + "/admin/students/no-uuid").status_code == 404
    with app.app_context():
        teacher_id = str(UserModel.query.filter_by(role="teacher").one().id)
    assert web.get(f"{API}/admin/students/{teacher_id}").status_code == 404


# --- CLI commands ----------------------------------------------------------------------------

def test_create_admin_cli(app, monkeypatch):
    runner = app.test_cli_runner()
    monkeypatch.setenv("ADMIN_EMAIL", "")
    assert runner.invoke(args=["create-admin"]).exit_code != 0
    monkeypatch.setenv("ADMIN_EMAIL", "Root@Example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Clave2026")
    assert "created" in runner.invoke(args=["create-admin"]).output
    assert "already exists" in runner.invoke(args=["create-admin"]).output
    with app.app_context():
        assert UserModel.query.filter_by(email="root@example.com").one().role == "admin"
    assert "3 demonstration courses ready" in runner.invoke(args=["seed-demo-courses"]).output
