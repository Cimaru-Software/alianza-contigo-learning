"""Black-box fixtures: talk to a running API over HTTP only, exactly like the browser does.

Run against an environment you own (never production):
    QA_BASE_URL=http://127.0.0.1:5055 QA_ADMIN_EMAIL=admin@qa.local QA_ADMIN_PASSWORD=... pytest qa/blackbox
Test accounts use QA_EMAIL_DOMAIN (a domain with MX records); keep SMTP unconfigured in that environment.
"""
import os
import random
import uuid

import pytest
import requests

BASE_URL = os.getenv("QA_BASE_URL", "http://127.0.0.1:5055").rstrip("/")
API = f"{BASE_URL}/api/v1"
ADMIN_EMAIL = os.getenv("QA_ADMIN_EMAIL", "admin@qa.local")
ADMIN_PASSWORD = os.getenv("QA_ADMIN_PASSWORD", "AdminQa2026")
PASSWORD = "Seguro2026"
# The API rejects reserved domains (.local, .test) and, in production config, domains without MX records.
EMAIL_DOMAIN = os.getenv("QA_EMAIL_DOMAIN", "alianzacontigoeducacion.com")


class Client(requests.Session):
    """requests.Session that replays the double-submit CSRF cookie like frontend/src/lib/api.ts."""

    def request(self, method, path, csrf=True, **kwargs):
        url = path if path.startswith("http") else API + path
        if csrf and method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            cookie = "alianza_refresh_csrf" if path == "/auth/refresh" else "alianza_access_csrf"
            token = self.cookies.get(cookie)
            if token:
                kwargs.setdefault("headers", {})["X-CSRF-TOKEN"] = token
        kwargs.setdefault("timeout", 30)
        return super().request(method, url, **kwargs)

    def login(self, email, password=PASSWORD, role=None):
        response = self.post("/auth/login", json={"email": email, "password": password, **({"role": role} if role else {})})
        assert response.status_code == 200, response.text
        return response


def unique_email(prefix="qa"):
    return f"qa-{prefix}-{uuid.uuid4().hex[:10]}@{EMAIL_DOMAIN}"


def cedula():
    """A random valid Ecuadorian cédula (Registro Civil modulo-10), from 144 million combinations."""
    body = f"{random.randint(1, 24):02d}{random.randrange(6)}{random.randrange(1_000_000):06d}"
    total = sum((d * c - 9) if d * c > 9 else d * c for d, c in zip(map(int, body), (2, 1, 2, 1, 2, 1, 2, 1, 2)))
    return body + str((10 - total % 10) % 10)


@pytest.fixture(scope="session", autouse=True)
def api_is_up():
    try:
        requests.get(f"{API}/health", timeout=5).raise_for_status()
    except requests.RequestException as exc:
        pytest.exit(f"API not reachable at {API}: {exc}", returncode=2)


@pytest.fixture
def anonymous():
    return Client()


@pytest.fixture
def admin():
    client = Client()
    client.login(ADMIN_EMAIL, ADMIN_PASSWORD, "admin")
    return client


@pytest.fixture
def new_student():
    def factory(**extra):
        client = Client()
        email = unique_email("student")
        body = {"firstName": "Estudiante", "lastName": "QA", "email": email, "password": PASSWORD, "nationalId": cedula(), **extra}
        response = client.post("/auth/register", json=body)
        assert response.status_code == 201, response.text
        client.email = email
        return client

    return factory


@pytest.fixture
def new_teacher(admin):
    def factory():
        email = unique_email("teacher")
        body = {"firstName": "Docente", "lastName": "QA", "email": email, "password": PASSWORD}
        assert admin.post("/auth/teachers", json=body).status_code == 201
        client = Client()
        client.login(email, role="teacher")
        return client

    return factory
