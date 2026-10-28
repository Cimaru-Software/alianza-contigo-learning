"""Create N students enrolled in every active course, for the LearningStudent load profile.

Runs inside the backend application context against the QA database (DATABASE_URL), never production:
    cd backend && PYTHONPATH=. DATABASE_URL=... python ../qa/stress/provision.py 300
"""
import os
import sys

from app import create_app
from app.extensions import db
from app.infrastructure.persistence.models import CourseModel, EnrollmentModel, UserModel

PASSWORD = "Seguro2026"
EMAIL_DOMAIN = os.getenv("QA_EMAIL_DOMAIN", "alianzacontigoeducacion.com")


def provision(count):
    template = UserModel(first_name="x", last_name="x", email="x", role="student")
    template.set_password(PASSWORD)  # hash once; every learner shares it
    courses = CourseModel.query.filter_by(status="ACTIVO").all()
    created = 0
    for index in range(count):
        email = f"qa-learner-{index}@{EMAIL_DOMAIN}"
        if UserModel.query.filter_by(email=email).first():
            continue
        student = UserModel(first_name="Alumno", last_name=str(index), email=email, role="student", password_hash=template.password_hash)
        db.session.add(student)
        db.session.flush()
        db.session.add_all(EnrollmentModel(course_id=course.id, student_id=student.id) for course in courses)
        created += 1
    db.session.commit()
    return created, len(courses)


if __name__ == "__main__":
    with create_app().app_context():
        created, courses = provision(int(sys.argv[1]) if len(sys.argv) > 1 else 300)
        print(f"{created} learners created, each enrolled in {courses} courses")
