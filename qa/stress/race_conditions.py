"""Concurrency correctness under contention: N identical requests fired at the same instant.

Each scenario checks an invariant that the row locks / unique constraints must protect on PostgreSQL.
    QA_BASE_URL=http://127.0.0.1:5055 python qa/stress/race_conditions.py
"""
import io
import os
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "blackbox"))
from conftest import ADMIN_EMAIL, ADMIN_PASSWORD, PASSWORD, Client, cedula, unique_email  # noqa: E402

PARALLEL = int(os.getenv("QA_PARALLEL", "20"))
SLUG = os.getenv("QA_SLUG", "emprendimiento-y-modelo-de-negocio")


def burst(fn, count=PARALLEL):
    """Run fn(i) count times, releasing every thread at the same moment."""
    gate = threading.Barrier(count)

    def run(index):
        gate.wait()
        return fn(index)

    with ThreadPoolExecutor(count) as pool:
        return list(pool.map(run, range(count)))


def student():
    client = Client()
    client.email = unique_email("race")
    assert client.post("/auth/register", json={"firstName": "Race", "lastName": "Condition", "email": client.email, "password": PASSWORD, "nationalId": cedula()}).status_code == 201
    return client


def admin():
    client = Client()
    client.login(ADMIN_EMAIL, ADMIN_PASSWORD, "admin")
    return client


def enrolled_student(staff):
    client = student()
    proof = {"proof": ("p.png", io.BytesIO(b"\x89PNG"), "image/png")}
    reference = client.post("/payments/transfer", data={"courseSlug": SLUG}, files=proof).json()["reference"]
    order = next(o for o in staff.get("/payments/orders?status=PENDING").json()["orders"] if o["reference"] == reference)
    staff.patch(f"/payments/orders/{order['id']}", json={"decision": "approve"})
    enrollment = next(e for e in client.get("/student/enrollments").json()["enrollments"] if e["course"]["slug"] == SLUG)
    return client, enrollment


def scenario_duplicate_registration():
    email = unique_email("dup")
    body = {"firstName": "Doble", "lastName": "Usuario", "email": email, "password": PASSWORD, "nationalId": cedula()}
    statuses = Counter(burst(lambda _i: Client().post("/auth/register", json=body).status_code))
    return statuses, statuses[201] == 1 and statuses[201] + statuses[409] == PARALLEL


def scenario_duplicate_transfer():
    client = student()

    def send(_i):
        proof = {"proof": ("p.png", io.BytesIO(b"\x89PNG"), "image/png")}
        return client.post("/payments/transfer", data={"courseSlug": SLUG}, files=proof).status_code

    statuses = Counter(burst(send))
    return statuses, statuses[201] == 1 and statuses[201] + statuses[409] == PARALLEL


def scenario_double_approval(staff):
    client = student()
    proof = {"proof": ("p.png", io.BytesIO(b"\x89PNG"), "image/png")}
    reference = client.post("/payments/transfer", data={"courseSlug": SLUG}, files=proof).json()["reference"]
    order = next(o for o in staff.get("/payments/orders?status=PENDING").json()["orders"] if o["reference"] == reference)
    statuses = Counter(burst(lambda _i: staff.patch(f"/payments/orders/{order['id']}", json={"decision": "approve"}).status_code))
    enrollments = [e for e in client.get("/student/enrollments").json()["enrollments"] if e["course"]["slug"] == SLUG]
    return statuses | {"enrollments": len(enrollments)}, statuses[200] == 1 and len(enrollments) == 1


def scenario_same_lesson_completed_concurrently(staff):
    client, enrollment = enrolled_student(staff)
    lesson = enrollment["course"]["modules"][0]["lessons"][0]["id"]
    url = f"/student/enrollments/{enrollment['id']}/lessons/{lesson}/complete"
    statuses = Counter(burst(lambda _i: client.post(url).status_code))
    after = next(e for e in client.get("/student/enrollments").json()["enrollments"] if e["id"] == enrollment["id"])
    return statuses | {"completed": len(after["completedLessonIds"])}, statuses[500] == 0 and len(after["completedLessonIds"]) == 1


def scenario_double_exam_submit(staff):
    client, enrollment = enrolled_student(staff)
    for module in enrollment["course"]["modules"]:
        for lesson in module["lessons"]:
            client.post(f"/student/enrollments/{enrollment['id']}/lessons/{lesson['id']}/complete")
    key = {q["id"]: q["correctAnswers"][0] for q in staff.get(f"/courses/{SLUG}/author").json()["finalExam"]["questions"]}
    wrong = {qid: (answer + 1) % 4 for qid, answer in key.items()}
    url = f"/exams/student/enrollments/{enrollment['id']}/submit"
    statuses = Counter(burst(lambda _i: client.post(url, json={"answers": wrong}).status_code))
    attempts = client.get(f"/exams/student/enrollments/{enrollment['id']}").json()["state"]["attemptsUsed"]
    return statuses | {"attempts": attempts}, statuses[200] == 1 and attempts == 1


def main():
    staff = admin()
    scenarios = [
        ("Registro duplicado simultáneo (mismo correo)", scenario_duplicate_registration),
        ("Transferencia duplicada simultánea (mismo curso)", scenario_duplicate_transfer),
        ("Doble aprobación simultánea de un pago", lambda: scenario_double_approval(staff)),
        ("Misma lección completada en paralelo", lambda: scenario_same_lesson_completed_concurrently(staff)),
        ("Doble envío simultáneo del examen", lambda: scenario_double_exam_submit(staff)),
    ]
    failed = 0
    for name, run in scenarios:
        observed, ok = run()
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'} | {name} | x{PARALLEL} | {dict(observed)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
