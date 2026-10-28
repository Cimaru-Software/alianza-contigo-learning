import hashlib
import os
import threading
import uuid
from datetime import datetime, timezone
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

# scrypt needs ~32 MB per hash; cap parallel hashes so a burst of sign-ups cannot exhaust RAM.
_password_hashing = threading.BoundedSemaphore(int(os.getenv("PASSWORD_HASH_CONCURRENCY", "4")))
_dummy_password_hash = None


def check_dummy_password(password: str) -> bool:
    """Spend the same time as a real check so login timing does not reveal registered emails."""
    global _dummy_password_hash
    with _password_hashing:
        if _dummy_password_hash is None:
            _dummy_password_hash = generate_password_hash(uuid.uuid4().hex, method="scrypt")
        check_password_hash(_dummy_password_hash, password)
    return False


class TrainingAreaModel(db.Model):
    __tablename__ = "training_areas"

    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(120), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    courses = db.relationship("CourseModel", back_populates="training_area")


class CourseModel(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    training_area_id = db.Column(db.Uuid, db.ForeignKey("training_areas.id", ondelete="RESTRICT"), nullable=False, index=True)
    slug = db.Column(db.String(160), nullable=False, unique=True, index=True)
    name = db.Column(db.String(180), nullable=False)
    short_description = db.Column(db.Text, nullable=False)
    full_description = db.Column(db.Text, nullable=False, default="")
    cover_url = db.Column(db.String(500), nullable=True)
    modality = db.Column(db.String(120), nullable=False)
    duration = db.Column(db.String(80), nullable=False)
    certification = db.Column(db.String(180), nullable=False)
    endorsement = db.Column(db.String(180), nullable=False, default="")
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount_percent = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(30), nullable=False, default="Activo")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    modules = db.relationship("CourseModuleModel", back_populates="course", cascade="all, delete-orphan", order_by="CourseModuleModel.position")
    final_exam = db.relationship("FinalExamModel", back_populates="course", cascade="all, delete-orphan", uselist=False)
    training_area = db.relationship("TrainingAreaModel", back_populates="courses")


class CourseModuleModel(db.Model):
    __tablename__ = "course_modules"
    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    course_id = db.Column(db.Uuid, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    position = db.Column(db.Integer, nullable=False, default=0)
    course = db.relationship("CourseModel", back_populates="modules")
    lessons = db.relationship("LessonModel", back_populates="module", cascade="all, delete-orphan", order_by="LessonModel.position")


class LessonModel(db.Model):
    __tablename__ = "lessons"
    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    module_id = db.Column(db.Uuid, db.ForeignKey("course_modules.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    lesson_type = db.Column(db.String(30), nullable=False, default="text")
    content = db.Column(db.Text, nullable=False, default="")
    media_url = db.Column(db.String(500), nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=False, default=0)
    is_preview = db.Column(db.Boolean, nullable=False, default=False)
    interaction_data = db.Column(db.JSON, nullable=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    module = db.relationship("CourseModuleModel", back_populates="lessons")
    # Explicit so deleting a lesson removes its progress on any database, not only via PostgreSQL's FK cascade.
    progress = db.relationship("LessonProgressModel", back_populates="lesson", cascade="all, delete-orphan")


class FinalExamModel(db.Model):
    __tablename__ = "final_exams"
    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    course_id = db.Column(db.Uuid, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, unique=True)
    title = db.Column(db.String(200), nullable=False, default="Evaluación final")
    instructions = db.Column(db.Text, nullable=False, default="")
    time_limit_minutes = db.Column(db.Integer, nullable=False, default=45)
    attempts_allowed = db.Column(db.Integer, nullable=False, default=1)
    passing_score = db.Column(db.Integer, nullable=False, default=70)
    course = db.relationship("CourseModel", back_populates="final_exam")
    questions = db.relationship("ExamQuestionModel", back_populates="exam", cascade="all, delete-orphan", order_by="ExamQuestionModel.position")


class ExamQuestionModel(db.Model):
    __tablename__ = "exam_questions"
    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    exam_id = db.Column(db.Uuid, db.ForeignKey("final_exams.id", ondelete="CASCADE"), nullable=False, index=True)
    prompt = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(30), nullable=False, default="single_choice")
    options = db.Column(db.JSON, nullable=False, default=list)
    correct_answers = db.Column(db.JSON, nullable=False, default=list)
    points = db.Column(db.Integer, nullable=False, default=1)
    position = db.Column(db.Integer, nullable=False, default=0)
    exam = db.relationship("FinalExamModel", back_populates="questions")


class EnrollmentModel(db.Model):
    __tablename__ = "enrollments"
    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    course_id = db.Column(db.Uuid, db.ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True)
    student_id = db.Column(db.Uuid, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    progress_percent = db.Column(db.Integer, nullable=False, default=0)
    exam_submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    exam_score = db.Column(db.Numeric(5, 2), nullable=True)
    teacher_feedback = db.Column(db.Text, nullable=False, default="")
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    enrolled_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    course = db.relationship("CourseModel")
    student = db.relationship("UserModel")
    lesson_progress = db.relationship("LessonProgressModel", back_populates="enrollment", cascade="all, delete-orphan")
    exam_attempts = db.relationship("ExamAttemptModel", back_populates="enrollment", cascade="all, delete-orphan", order_by="ExamAttemptModel.attempt_number")
    __table_args__ = (db.UniqueConstraint("course_id", "student_id", name="uq_enrollment_course_student"),)


class LessonProgressModel(db.Model):
    __tablename__ = "lesson_progress"
    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(db.Uuid, db.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    lesson_id = db.Column(db.Uuid, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    enrollment = db.relationship("EnrollmentModel", back_populates="lesson_progress")
    lesson = db.relationship("LessonModel", back_populates="progress")
    __table_args__ = (db.UniqueConstraint("enrollment_id", "lesson_id", name="uq_lesson_progress_enrollment_lesson"),)


class ExamAttemptModel(db.Model):
    __tablename__ = "exam_attempts"
    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(db.Uuid, db.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number = db.Column(db.Integer, nullable=False)
    answers = db.Column(db.JSON, nullable=False, default=dict)
    questions_snapshot = db.Column(db.JSON, nullable=False, default=list)
    score = db.Column(db.Numeric(5, 2), nullable=False)
    passed = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(30), nullable=False, index=True)
    feedback = db.Column(db.Text, nullable=False, default="")
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewed_by_id = db.Column(db.Uuid, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    enrollment = db.relationship("EnrollmentModel", back_populates="exam_attempts")
    reviewed_by = db.relationship("UserModel", foreign_keys=[reviewed_by_id])
    __table_args__ = (db.UniqueConstraint("enrollment_id", "attempt_number", name="uq_exam_attempt_enrollment_number"),)


class PaymentOrderModel(db.Model):
    __tablename__ = "payment_orders"
    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    reference = db.Column(db.String(40), nullable=False, unique=True, index=True)
    course_id = db.Column(db.Uuid, db.ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True)
    student_id = db.Column(db.Uuid, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_method = db.Column(db.String(20), nullable=False)
    provider = db.Column(db.String(30), nullable=False, default="MANUAL")
    provider_transaction_id = db.Column(db.String(100), nullable=True)
    currency = db.Column(db.String(3), nullable=False, default="USD")
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="PENDING", index=True)
    proof_url = db.Column(db.String(500), nullable=True)
    rejection_comment = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    course = db.relationship("CourseModel")
    student = db.relationship("UserModel", foreign_keys=[student_id])
    __table_args__ = (
        db.UniqueConstraint(
            "provider", "provider_transaction_id", name="uq_payment_provider_transaction"
        ),
    )


class UserModel(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    national_id = db.Column(db.String(30), nullable=True, unique=True)
    phone = db.Column(db.String(30), nullable=True)
    avatar_key = db.Column(db.String(30), nullable=False, default="navy")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password: str) -> None:
        with _password_hashing:
            self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password: str) -> bool:
        with _password_hashing:
            return check_password_hash(self.password_hash, password)

    def password_fingerprint(self) -> str:
        """Changes whenever the password changes; used to expire reset links and old sessions."""
        return hashlib.sha256(self.password_hash.encode()).hexdigest()[:16]

    def to_dict(self):
        return {
            "id": str(self.id), "firstName": self.first_name, "lastName": self.last_name,
            "name": f"{self.first_name} {self.last_name}", "email": self.email,
            "role": self.role, "phone": self.phone, "nationalId": self.national_id,
            "isActive": self.is_active, "avatarKey": self.avatar_key,
        }
