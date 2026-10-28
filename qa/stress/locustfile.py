"""Load profiles for the Alianza Contigo API (Locust).

Run only against an environment you own, never production:
    locust -f qa/stress/locustfile.py --host http://127.0.0.1:5055 --headless \
        -u 200 -r 20 -t 3m --csv results/mixed PublicVisitor LearningStudent NewStudent

Profiles:
    PublicVisitor   anonymous catalog browsing (landing, catalog, course detail, SEO files)
    NewStudent      registration burst (scrypt-bound: the most CPU-expensive request)
    LearningStudent logs in once, then studies: enrollments, lessons, exam state, certificates
    AdminUser       dashboard and management screens (heavy aggregate queries)
"""
import os
import random
import uuid

from locust import HttpUser, between, events, task

ADMIN_EMAIL = os.getenv("QA_ADMIN_EMAIL", "admin@qa.local")
EMAIL_DOMAIN = os.getenv("QA_EMAIL_DOMAIN", "alianzacontigoeducacion.com")
ADMIN_PASSWORD = os.getenv("QA_ADMIN_PASSWORD", "AdminQa2026")
PASSWORD = "Seguro2026"
SLUGS = []


def cedula():
    """A random valid Ecuadorian cédula (Registro Civil modulo-10)."""
    body = f"{random.randint(1, 24):02d}{random.randrange(6)}{random.randrange(1_000_000):06d}"
    total = sum((d * c - 9) if d * c > 9 else d * c for d, c in zip(map(int, body), (2, 1, 2, 1, 2, 1, 2, 1, 2)))
    return body + str((10 - total % 10) % 10)


@events.test_start.add_listener
def load_catalog(environment, **_kwargs):
    import requests

    SLUGS.extend(course["slug"] for course in requests.get(f"{environment.host}/api/v1/courses", timeout=10).json())


class CsrfUser(HttpUser):
    abstract = True

    def send(self, method, path, name=None, **kwargs):
        if method != "GET":
            token = self.client.cookies.get("alianza_access_csrf")
            if token:
                kwargs.setdefault("headers", {})["X-CSRF-TOKEN"] = token
        return self.client.request(method, f"/api/v1{path}", name=name or path, **kwargs)


class PublicVisitor(CsrfUser):
    weight = 6
    wait_time = between(1, 4)

    @task(5)
    def catalog(self):
        self.send("GET", "/courses")

    @task(4)
    def course_detail(self):
        self.send("GET", f"/courses/{random.choice(SLUGS)}", name="/courses/[slug]")

    @task(1)
    def training_areas(self):
        self.send("GET", "/training-areas")

    @task(1)
    def seo(self):
        self.send("GET", random.choice(["/seo/sitemap.xml", "/seo/llms.txt"]), name="/seo/*")


class NewStudent(CsrfUser):
    weight = 1
    wait_time = between(2, 6)

    @task
    def register(self):
        self.client.cookies.clear()
        body = {"firstName": "Carga", "lastName": "QA", "email": f"qa-load-{uuid.uuid4().hex}@{EMAIL_DOMAIN}", "password": PASSWORD, "nationalId": cedula()}
        self.send("POST", "/auth/register", json=body)


class LearningStudent(CsrfUser):
    """Uses the accounts created by provision.py (learner-0 .. learner-N, enrolled in every course)."""

    weight = 3
    wait_time = between(2, 5)
    pool = int(os.getenv("QA_LEARNERS", "300"))

    def on_start(self):
        email = f"qa-learner-{random.randrange(self.pool)}@{EMAIL_DOMAIN}"
        self.send("POST", "/auth/login", json={"email": email, "password": PASSWORD, "role": "student"})
        self.enrollments = []

    @task(4)
    def my_courses(self):
        response = self.send("GET", "/student/enrollments")
        if response.ok:
            self.enrollments = response.json()["enrollments"]

    @task(3)
    def study_next_lesson(self):
        if not self.enrollments:
            return
        enrollment = random.choice(self.enrollments)
        done = set(enrollment["completedLessonIds"])
        lessons = [lesson["id"] for module in enrollment["course"]["modules"] for lesson in module["lessons"]]
        pending = next((lesson for lesson in lessons if lesson not in done), None)
        if pending:
            path = f"/student/enrollments/{enrollment['id']}/lessons/{pending}/complete"
            if self.send("POST", path, name="/student/enrollments/[id]/lessons/[id]/complete").ok:
                enrollment["completedLessonIds"].append(pending)

    @task(1)
    def exam_state(self):
        if self.enrollments:
            enrollment = random.choice(self.enrollments)
            self.send("GET", f"/exams/student/enrollments/{enrollment['id']}", name="/exams/student/enrollments/[id]")

    @task(2)
    def me(self):
        response = self.send("GET", "/auth/me")
        if response.status_code == 401:
            self.send("POST", "/auth/refresh")

    @task(1)
    def certificates(self):
        self.send("GET", "/exams/student/certificates")

    @task(1)
    def catalog(self):
        self.send("GET", "/courses")


class AdminUser(CsrfUser):
    weight = 1
    fixed_count = 2
    wait_time = between(3, 8)

    def on_start(self):
        self.send("POST", "/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "role": "admin"})

    @task(3)
    def dashboard(self):
        self.send("GET", "/admin/dashboard")

    @task(2)
    def students(self):
        self.send("GET", "/admin/students")

    @task(1)
    def orders(self):
        self.send("GET", "/payments/orders")

    @task(1)
    def manage(self):
        self.send("GET", "/courses/manage")
