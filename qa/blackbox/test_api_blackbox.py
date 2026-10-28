"""Black-box API tests. Only the public HTTP contract is used; test names carry the technique applied."""
import io
import uuid
import xml.etree.ElementTree as ET

import pytest
import requests

from conftest import API, PASSWORD, Client, cedula, unique_email

SLUG = "liderazgo-y-gestion-de-equipos"
EVIL_ORIGIN = "https://evil.example"


# --- 1. Equivalence partitioning + boundary values: registration ------------------------------

def registration(**overrides):
    return {"firstName": "Ana", "lastName": "Torres", "email": unique_email(), "password": PASSWORD, "nationalId": cedula(), **overrides}


@pytest.mark.parametrize(
    "case, overrides, status",
    [
        ("valid minimal", {}, 201),
        ("password 7 chars (below min)", {"password": "Abcde12"}, 400),
        ("password 8 chars (min)", {"password": "Abcdef12"}, 201),
        ("password 128 chars (max)", {"password": "A1" * 64}, 201),
        ("password 129 chars (above max)", {"password": "A1" * 64 + "x"}, 400),
        ("password only letters", {"password": "SoloLetras"}, 400),
        ("password only digits", {"password": "1234567890"}, 400),
        ("first name 100 chars (max)", {"firstName": "a" * 100}, 201),
        ("first name 101 chars (above max)", {"firstName": "a" * 101}, 400),
        ("empty last name", {"lastName": "   "}, 400),
        ("email without domain", {"email": "ana@"}, 400),
        ("email with spaces", {"email": "ana torres@x.co"}, 400),
        ("phone as number type", {"phone": 999}, 400),
        ("privileged role ignored", {"role": "admin"}, 201),
        ("cédula missing", {"nationalId": ""}, 400),
        ("cédula wrong check digit", {"nationalId": "1710034066"}, 400),
        ("cédula province 25", {"nationalId": "2510034062"}, 400),
        ("cédula 9 digits", {"nationalId": "171003406"}, 400),
        ("cédula published valid example", {"nationalId": "1710034065"}, None),
        ("email reserved TLD .local", {"email": "ana@empresa.local"}, 400),
        ("email disposable provider", {"email": f"ana-{uuid.uuid4().hex[:6]}@mailinator.com"}, 400),
        ("email domain does not exist", {"email": "ana@dominio-que-no-existe-qa-9f3c.com"}, 400),
        ("email domain without MX (example.com)", {"email": "ana@example.com"}, 400),
        ("name with SQL", {"firstName": "Robert'); DROP TABLE users;--"}, 400),
        ("name with HTML", {"firstName": "<script>alert(1)</script>"}, 400),
        ("accented name", {"firstName": "José María Ñúñez"}, 201),
    ],
)
def test_ep_bva_registration(anonymous, case, overrides, status):
    response = anonymous.post("/auth/register", json=registration(**overrides))
    if status is None:  # a fixed valid cédula: 201 the first run, 409 once that cédula exists
        assert response.status_code in {201, 409}, f"{case}: {response.text}"
        return
    assert response.status_code == status, f"{case}: {response.text}"
    if status == 201:
        assert response.json()["user"]["role"] == "student"


def test_ep_registration_duplicates_are_conflicts(anonymous):
    body = registration()
    assert anonymous.post("/auth/register", json=body).status_code == 201
    assert Client().post("/auth/register", json={**body, "email": body["email"].upper()}).status_code == 409
    assert Client().post("/auth/register", json={**body, "email": unique_email()}).status_code == 409  # same cédula


# --- 2. Decision table: login --------------------------------------------------------------

def test_decision_table_login(admin, new_student):
    student = new_student()
    rows = [
        # (email exists, password ok, requested portal) -> expected status / error
        ({"email": unique_email(), "password": PASSWORD}, 401, "invalid_credentials"),
        ({"email": student.email, "password": "Incorrecta9"}, 401, "invalid_credentials"),
        ({"email": student.email, "password": PASSWORD, "role": "admin"}, 403, "wrong_portal"),
        ({"email": student.email, "password": PASSWORD, "role": "student"}, 200, None),
        ({"email": student.email.upper(), "password": PASSWORD}, 200, None),
    ]
    for body, status, error in rows:
        response = Client().post("/auth/login", json=body)
        assert response.status_code == status, body
        if error:
            assert response.json()["error"] == error
    unknown = Client().post("/auth/login", json=rows[0][0]).json()
    wrong = Client().post("/auth/login", json=rows[1][0]).json()
    assert unknown == wrong  # no account enumeration through the message


# --- 3. Session security -------------------------------------------------------------------

def test_session_cookies_are_httponly_and_csrf_is_enforced(new_student):
    student = new_student()
    cookies = {cookie.name: cookie for cookie in student.cookies}
    assert cookies["alianza_access_token"].has_nonstandard_attr("HttpOnly")
    assert not cookies["alianza_access_csrf"].has_nonstandard_attr("HttpOnly")  # readable by the SPA on purpose
    response = student.patch("/auth/profile", json={"firstName": "Sin CSRF"}, csrf=False)
    assert response.status_code == 401
    assert student.patch("/auth/profile", json={"firstName": "Con CSRF"}).status_code == 200


def test_logout_and_refresh(new_student):
    student = new_student()
    assert student.post("/auth/refresh").status_code == 200
    assert student.post("/auth/logout").status_code == 200
    assert student.get("/auth/me").status_code == 401


def test_password_change_revokes_other_devices(new_student):
    laptop = new_student()
    phone = Client()
    phone.login(laptop.email)
    assert laptop.post("/auth/change-password", json={"currentPassword": PASSWORD, "newPassword": "OtraClave2026"}).status_code == 200
    assert phone.post("/auth/refresh").status_code == 401
    assert laptop.get("/auth/me").status_code == 200


# --- 4. Authorization matrix ---------------------------------------------------------------

MATRIX = [
    # path, method, allowed roles
    ("/admin/dashboard", "get", {"admin"}),
    ("/admin/students", "get", {"admin"}),
    ("/auth/users", "get", {"admin"}),
    ("/payments/orders", "get", {"admin"}),
    ("/payments/admin/summary", "get", {"admin"}),
    ("/courses/manage", "get", {"admin", "teacher"}),
    ("/exams/teacher/attempts", "get", {"admin", "teacher"}),
    (f"/courses/{SLUG}/teaching", "get", {"admin", "teacher"}),
    (f"/courses/{SLUG}/author", "get", {"admin"}),
    ("/student/enrollments", "get", {"student"}),
    ("/exams/student/certificates", "get", {"student"}),
    ("/payments/bank-details", "get", {"student"}),
]


def test_authorization_matrix(anonymous, admin, new_student, new_teacher):
    sessions = {"anonymous": anonymous, "student": new_student(), "teacher": new_teacher(), "admin": admin}
    failures = []
    for path, method, allowed in MATRIX:
        for role, client in sessions.items():
            status = getattr(client, method)(path).status_code
            expected = 200 if role in allowed else (401 if role == "anonymous" else 403)
            if status != expected:
                failures.append(f"{role} {method.upper()} {path}: {status} != {expected}")
    assert not failures, failures


# --- 5. Information disclosure on the public catalog ------------------------------------------

def test_public_catalog_never_leaks_paid_content_or_answers(anonymous):
    courses = anonymous.get("/courses").json()
    assert {course["slug"] for course in courses} >= {SLUG}
    for course in courses:
        detail = anonymous.get(f"/courses/{course['slug']}").json()
        assert "finalExam" not in detail
        for module in detail["modules"]:
            for lesson in module["lessons"]:
                if not lesson["isPreview"]:
                    assert lesson["content"] == "" and lesson["mediaUrl"] is None and lesson["interaction"] is None
    assert anonymous.get("/courses/no-existe").status_code == 404


# --- 6. State transition: purchase -> learning -> exam -> review -> certificate ---------------

def transfer(student, slug=SLUG):
    proof = {"proof": ("comprobante.png", io.BytesIO(b"\x89PNG fake"), "image/png")}
    return student.post("/payments/transfer", data={"courseSlug": slug}, files=proof)


def approve_pending(admin, reference):
    order = next(order for order in admin.get("/payments/orders?status=PENDING").json()["orders"] if order["reference"] == reference)
    response = admin.patch(f"/payments/orders/{order['id']}", json={"decision": "approve"})
    assert response.status_code == 200 and response.json()["status"] == "APPROVED"
    return order


def enrolled_course(student, slug=SLUG):
    return next(item for item in student.get("/student/enrollments").json()["enrollments"] if item["course"]["slug"] == slug)


def test_state_transition_full_student_journey(admin, new_student, new_teacher):
    student = new_student()
    assert student.get("/student/enrollments").json()["enrollments"] == []

    # PENDING purchase: a second transfer for the same course is refused while the first is pending.
    created = transfer(student)
    assert created.status_code == 201
    assert transfer(student).status_code == 409
    bad_extension = student.post("/payments/transfer", data={"courseSlug": SLUG}, files={"proof": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")})
    assert bad_extension.status_code in {400, 409}
    assert admin.patch(f"/payments/orders/{uuid.uuid4()}", json={"decision": "approve"}).status_code == 400

    approve_pending(admin, created.json()["reference"])
    assert transfer(student).status_code == 409  # already enrolled

    # LEARNING: lessons unlock in order.
    enrollment = enrolled_course(student)
    lessons = [lesson["id"] for module in enrollment["course"]["modules"] for lesson in module["lessons"]]
    base = f"/student/enrollments/{enrollment['id']}"
    assert student.post(f"{base}/lessons/{lessons[1]}/complete").status_code == 409
    exam_url = f"/exams/student/enrollments/{enrollment['id']}"
    assert student.get(exam_url).json()["state"]["canAttempt"] is False
    for lesson in lessons:
        assert student.post(f"{base}/lessons/{lesson}/complete").status_code == 200
    assert enrolled_course(student)["progressPercent"] == 90

    # EXAM attempt 1 fails -> PENDING_REVIEW.
    exam = student.get(exam_url).json()
    assert exam["state"]["canAttempt"] is True
    assert all("correctAnswers" not in question for question in exam["exam"]["questions"])
    key = {q["id"]: q["correctAnswers"][0] for q in admin.get(f"/courses/{SLUG}/author").json()["finalExam"]["questions"]}
    wrong = {qid: (answer + 1) % 4 for qid, answer in key.items()}
    assert student.post(f"{exam_url}/submit", json={"answers": wrong}).json()["status"] == "PENDING_REVIEW"
    assert student.post(f"{exam_url}/submit", json={"answers": key}).status_code == 409

    # REVIEW by a teacher enables attempt 2.
    teacher = new_teacher()
    attempt = next(a for a in teacher.get("/exams/teacher/attempts").json()["attempts"] if a["studentEmail"] == student.email)
    assert attempt["score"] == 0.0
    review = teacher.patch(f"/exams/teacher/attempts/{attempt['id']}/review", json={"feedback": "Repasa los módulos."})
    assert review.json()["attemptsRemaining"] == 1

    # PASSED -> certificate.
    passed = student.post(f"{exam_url}/submit", json={"answers": key}).json()
    assert passed["passed"] is True and passed["score"] == 100.0
    certificate = student.get("/exams/student/certificates").json()["certificates"][0]
    assert certificate["code"].startswith("AC-")
    pdf = student.get(f"/exams/student/certificates/{enrollment['id']}/pdf")
    assert pdf.status_code == 200 and pdf.headers["Content-Type"] == "application/pdf" and pdf.content[:4] == b"%PDF"
    assert enrolled_course(student)["progressPercent"] == 100

    # Another student cannot download it.
    assert new_student().get(f"/exams/student/certificates/{enrollment['id']}/pdf").status_code == 404


def test_rejected_transfer_allows_a_new_one(admin, new_student):
    student = new_student()
    reference = transfer(student).json()["reference"]
    order = next(o for o in admin.get("/payments/orders?status=PENDING").json()["orders"] if o["reference"] == reference)
    assert admin.patch(f"/payments/orders/{order['id']}", json={"decision": "reject"}).status_code == 400  # needs reason
    assert admin.patch(f"/payments/orders/{order['id']}", json={"decision": "maybe"}).status_code == 400
    assert admin.patch(f"/payments/orders/{order['id']}", json={"decision": "reject", "comment": "Ilegible"}).json()["status"] == "REJECTED"
    assert transfer(student).status_code == 201


def test_card_checkout_without_payphone_credentials_is_unavailable(new_student):
    assert new_student().post("/payments/card", json={"courseSlug": SLUG}).status_code == 503


# --- 7. Input robustness on the live stack ---------------------------------------------------

def test_upload_path_traversal_is_blocked(anonymous):
    for path in ["/uploads/..%2f..%2fetc%2fpasswd", "/uploads/../../wsgi.py", "/uploads/%2e%2e/%2e%2e/etc/passwd"]:
        assert anonymous.get(path).status_code == 404


@pytest.mark.parametrize("body", [["array"], {"name": 1, "email": "a@b.co", "phone": "1", "courseSlug": SLUG, "message": "m"}])
def test_contact_with_malformed_body_is_a_client_error(anonymous, body):
    assert anonymous.post("/contact", json=body).status_code == 400


@pytest.mark.parametrize(
    "body",
    [{}, {"name": "A", "email": "no-email", "phone": "1", "courseSlug": SLUG, "message": "m"},
     {"name": "A", "email": "a@b.co", "phone": "1", "courseSlug": "inexistente", "message": "m"},
     {"name": "A" * 161, "email": "a@b.co", "phone": "1", "courseSlug": SLUG, "message": "m"}],
)
def test_contact_validation(anonymous, body):
    assert anonymous.post("/contact", json=body).status_code == 400


# --- 8. Abuse protection (Redis-backed limits shared by all workers) --------------------------

def test_failed_logins_lock_the_account_for_15_minutes(new_student):
    email = new_student().email
    statuses = [Client().post("/auth/login", json={"email": email, "password": "Incorrecta9"}).status_code for _ in range(11)]
    assert statuses[:10] == [401] * 10 and statuses[10] == 429
    blocked = Client().post("/auth/login", json={"email": email, "password": PASSWORD})
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0


def test_forgot_password_is_limited_per_email(new_student):
    email = new_student().email
    statuses = [Client().post("/auth/forgot-password", json={"email": email}).status_code for _ in range(4)]
    assert statuses == [200, 200, 200, 429]


# --- 9. CORS ---------------------------------------------------------------------------------

def test_cors_only_trusts_the_frontend_origin():
    allowed = requests.options(f"{API}/auth/me", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert allowed.headers.get("Access-Control-Allow-Credentials") == "true"
    evil = requests.options(f"{API}/auth/me", headers={"Origin": EVIL_ORIGIN, "Access-Control-Request-Method": "GET"})
    assert "Access-Control-Allow-Origin" not in evil.headers


# --- 10. SEO endpoints -----------------------------------------------------------------------

def test_sitemap_is_valid_xml_with_active_courses(anonymous):
    response = anonymous.get("/seo/sitemap.xml")
    assert response.headers["Content-Type"].startswith("application/xml")
    locs = [element.text for element in ET.fromstring(response.content).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert any(loc.endswith(f"/courses/{SLUG}") for loc in locs)
    assert "Alianza Contigo" in anonymous.get("/seo/llms.txt").text


# --- 11. Data integrity on PostgreSQL --------------------------------------------------------

def draft_course(admin, name):
    area = admin.get("/training-areas").json()[0]["id"]
    slug = admin.post("/courses", json={"name": name, "trainingAreaId": area, "price": 30}).json()["slug"]
    content = {"modules": [{"title": "M1", "lessons": [{"title": "L1", "type": "text"}, {"title": "L2", "type": "text"}]}]}
    assert admin.put(f"/courses/{slug}/content", json=content).status_code == 200
    exam = {"questions": [{"prompt": "P", "options": ["a", "b"], "correctAnswers": [0]}]}
    assert admin.put(f"/courses/{slug}/exam", json=exam).status_code == 200
    assert admin.put(f"/courses/{slug}", json={"status": "ACTIVO"}).status_code == 200
    return slug


def test_editing_content_keeps_student_progress(admin, new_student):
    slug = draft_course(admin, f"QA progreso {uuid.uuid4().hex[:6]}")
    student = new_student()
    approve_pending(admin, transfer(student, slug).json()["reference"])
    enrollment = enrolled_course(student, slug)
    first_lesson = enrollment["course"]["modules"][0]["lessons"][0]["id"]
    student.post(f"/student/enrollments/{enrollment['id']}/lessons/{first_lesson}/complete")
    assert enrolled_course(student, slug)["progressPercent"] == 45

    modules = admin.get(f"/courses/{slug}/author").json()["modules"]
    modules[0]["lessons"][1]["title"] = "L2 (corregida)"  # a typo fix
    assert admin.put(f"/courses/{slug}/content", json={"modules": modules}).status_code == 200
    assert enrolled_course(student, slug)["progressPercent"] == 45


def test_deleting_a_course_keeps_financial_records(admin, new_student):
    slug = draft_course(admin, f"QA borrar {uuid.uuid4().hex[:6]}")
    reference = transfer(new_student(), slug).json()["reference"]
    approve_pending(admin, reference)
    assert admin.delete(f"/courses/{slug}").status_code == 409  # closing it is the way to retire it
    references = {order["reference"] for order in admin.get("/payments/orders").json()["orders"]}
    assert reference in references
    empty = draft_course(admin, f"QA vacio {uuid.uuid4().hex[:6]}")
    assert admin.delete(f"/courses/{empty}").status_code == 204


# --- 12. SQL injection and hostile input ------------------------------------------------------

SQL_PAYLOADS = ["' OR '1'='1", "' OR 1=1 --", "admin'--", "'; DROP TABLE users; --", "' UNION SELECT password_hash FROM users --"]


@pytest.mark.parametrize("payload", SQL_PAYLOADS)
def test_sql_injection_is_inert(anonymous, admin, payload):
    assert anonymous.post("/auth/login", json={"email": payload, "password": payload}).status_code == 401
    # Names only allow letters and ' - . (so "O'Brien-Pérez" works); whatever is accepted is stored literally.
    registered = Client().post("/auth/register", json=registration(firstName=payload))
    assert registered.status_code in {201, 400}
    if registered.status_code == 201:
        assert registered.json()["user"]["firstName"] == payload
    assert anonymous.get(f"/courses/{payload}").status_code == 404
    assert len(admin.get("/auth/users", params={"role": payload}).json()["users"]) == len(admin.get("/auth/users").json()["users"])
    area = admin.post("/training-areas", json={"name": f"{payload} {uuid.uuid4().hex[:4]}"})
    assert area.status_code == 201 and area.json()["name"].startswith(payload)  # stored literally
    assert admin.delete(f"/training-areas/{area.json()['id']}").status_code == 204
    assert anonymous.get("/courses").status_code == 200  # tables intact


def test_control_characters_never_reach_postgresql(anonymous):
    assert anonymous.get("/courses/curso%00x").status_code == 400
    assert anonymous.get("/courses", params={"q": "a\x00b"}).status_code == 400
    assert anonymous.post("/auth/login", json={"email": "a\x00@x.com", "password": "x"}).status_code == 401
    assert anonymous.post("/auth/register", json=registration(lastName="Torres\x00")).status_code == 400


def test_unknown_routes_answer_json(anonymous):
    response = anonymous.get("/no-existe")
    assert response.status_code == 404 and response.headers["Content-Type"].startswith("application/json")
