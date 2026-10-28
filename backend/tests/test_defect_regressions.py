"""Regression tests for the defects found in the QA pass (docs/REPORTE_PRUEBAS.md, DEF-01 to DEF-04).

They were written as xfail(strict=True) before the fixes and now guard against the defects returning.
"""
from decimal import Decimal

import pytest

from tests.conftest import area_id, enroll, login

API = "/api/v1"



# --- DEF-01: malformed JSON payloads must be a 400, never an unhandled 500 ---------------------

MALFORMED_ADMIN = [
    ("post", "/courses", {"name": "X", "discountPercent": "abc"}),
    ("post", "/courses", {"name": "X", "price": "abc"}),
    ("post", "/courses", ["no", "es", "objeto"]),
    ("put", "/courses/curso-base", {"discountPercent": "abc"}),
    ("put", "/courses/curso-base", {"name": None}),
    ("put", "/courses/curso-base/content", {"modules": [{"title": "m", "lessons": [{"durationMinutes": "abc"}]}]}),
    ("put", "/courses/curso-base/content", {"modules": ["no-es-objeto"]}),
    ("put", "/courses/curso-base/exam", {"timeLimitMinutes": "abc", "questions": [{"prompt": "p", "options": ["a", "b"], "correctAnswers": [0]}]}),
    ("post", "/training-areas", ["no-es-objeto"]),
]


@pytest.mark.parametrize("method, path, body", MALFORMED_ADMIN)
def test_admin_endpoints_reject_malformed_input_with_400(app, lenient_web, method, path, body):
    login(lenient_web, "admin@example.com")
    if path == "/courses" and isinstance(body, dict):
        body = {**body, "trainingAreaId": area_id(app)}
    assert getattr(lenient_web, method)(API + path, json=body).status_code == 400


@pytest.mark.parametrize("body", [["x"], {"name": 1, "email": "a@b.co", "phone": "1", "courseSlug": "curso-base", "message": "m"}])
def test_contact_rejects_malformed_input_with_400(lenient_web, body):
    assert lenient_web.post(API + "/contact", json=body).status_code == 400


@pytest.mark.parametrize("target", ["exam-list-body", "exam-list-answers", "card-checkout"])
def test_student_endpoints_reject_malformed_input_with_400(app, lenient_web, target):
    enrollment_id, lessons, _ = enroll(app)
    login(lenient_web, "ana@example.com")
    for lesson in lessons:
        lenient_web.post(f"{API}/student/enrollments/{enrollment_id}/lessons/{lesson}/complete")
    submit = f"{API}/exams/student/enrollments/{enrollment_id}/submit"
    response = {
        "exam-list-body": lambda: lenient_web.post(submit, json=[1]),
        "exam-list-answers": lambda: lenient_web.post(submit, json={"answers": [0, 0]}),
        "card-checkout": lambda: lenient_web.post(API + "/payments/card", json=[1]),
    }[target]()
    assert response.status_code == 400


# --- DEF-02: the displayed final price is the amount charged -----------------------------------

@pytest.mark.parametrize("price, discount", [("29.90", 25), ("59.90", 15)])
def test_catalog_price_matches_the_amount_charged(app, web, price, discount):
    from app.presentation.payment_api import final_price
    from app.infrastructure.persistence.models import CourseModel
    from app.extensions import db

    with app.app_context():
        course = CourseModel.query.filter_by(slug="curso-base").one()
        course.price, course.discount_percent = Decimal(price), discount
        db.session.commit()
        charged = final_price(course)
    shown = web.get(API + "/courses/curso-base").json["finalPrice"]
    assert Decimal(str(shown)) == charged


# --- DEF-03: business rules on course authoring ------------------------------------------------

def test_new_course_rejects_negative_price(app, web):
    login(web, "admin@example.com")
    response = web.post(API + "/courses", json={"name": "Negativo", "trainingAreaId": area_id(app), "price": -50})
    assert response.status_code == 400


def test_exam_rejects_correct_answers_outside_the_options(web):
    login(web, "admin@example.com")
    body = {"questions": [{"prompt": "P", "options": ["a", "b"], "correctAnswers": [9]}]}
    assert web.put(API + "/courses/curso-base/exam", json=body).status_code == 400


def test_course_cannot_be_renamed_to_blank(web):
    login(web, "admin@example.com")
    assert web.put(API + "/courses/curso-base", json={"name": "  "}).status_code == 400


# --- DEF-04: SEO slugs transliterate accented letters ------------------------------------------

def test_slug_transliterates_spanish_accents():
    from app.presentation.api import slugify

    assert slugify("Gestión Pública") == "gestion-publica"
