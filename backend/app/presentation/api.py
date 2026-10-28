from dataclasses import asdict

import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename
from flask_jwt_extended import get_jwt_identity
from markupsafe import escape
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.application.services.course_service import CourseService
from app.domain.pricing import final_price
from app.extensions import client_ip, db, limiter
from app.presentation import validation
from app.infrastructure.persistence.models import CourseModel, CourseModuleModel, EnrollmentModel, ExamAttemptModel, ExamQuestionModel, FinalExamModel, LessonModel, LessonProgressModel, PaymentOrderModel, TrainingAreaModel, UserModel
from app.presentation.auth_api import role_required
from app.infrastructure.email_service import branded_html, send_html

ALLOWED_UPLOADS = {"pdf", "png", "jpg", "jpeg", "webp", "mp4", "webm"}
LESSON_TYPES = {"video", "text", "image", "pdf", "file", "interactive"}
INTERACTION_TYPES = {"multiple_choice", "true_false", "ordering", "matching"}
# Load a course with everything serialize_course touches in a few queries instead of one per lesson.
COURSE_TREE = (
    selectinload(CourseModel.training_area),
    selectinload(CourseModel.modules).selectinload(CourseModuleModel.lessons),
    selectinload(CourseModel.final_exam).selectinload(FinalExamModel.questions),
)


def serialize_lesson(lesson, public=False):
    if public and not lesson.is_preview:
        # Paid content (text, media URLs, activity answers) is only served to enrolled students.
        return {"id": str(lesson.id), "title": lesson.title, "type": lesson.lesson_type, "content": "", "mediaUrl": None, "durationMinutes": lesson.duration_minutes, "isPreview": False, "interaction": None, "position": lesson.position}
    return {"id": str(lesson.id), "title": lesson.title, "type": lesson.lesson_type, "content": lesson.content, "mediaUrl": lesson.media_url, "durationMinutes": lesson.duration_minutes, "isPreview": lesson.is_preview, "interaction": lesson.interaction_data, "position": lesson.position}


def serialize_module(module, public=False):
    return {"id": str(module.id), "title": module.title, "description": module.description, "position": module.position, "lessons": [serialize_lesson(item, public) for item in module.lessons]}


def serialize_exam(exam, include_answers=False):
    if not exam:
        return None
    questions = []
    for item in exam.questions:
        question = {"id": str(item.id), "prompt": item.prompt, "type": item.question_type, "options": item.options, "points": item.points, "position": item.position}
        if include_answers:
            question["correctAnswers"] = item.correct_answers
        questions.append(question)
    return {"id": str(exam.id), "title": exam.title, "instructions": exam.instructions, "timeLimitMinutes": exam.time_limit_minutes, "attemptsAllowed": exam.attempts_allowed, "passingScore": exam.passing_score, "questions": questions}


def serialize_course(course, detailed=False, include_answers=False, public=False):
    data = {"id": str(course.id), "slug": course.slug, "name": course.name, "shortDescription": course.short_description, "fullDescription": course.full_description, "coverUrl": course.cover_url, "modality": course.modality, "duration": course.duration, "certification": course.certification, "endorsement": course.endorsement, "price": float(course.price), "discountPercent": course.discount_percent, "finalPrice": float(final_price(course.price, course.discount_percent)), "status": course.status, "modulesCount": len(course.modules), "lessonsCount": sum(len(item.lessons) for item in course.modules), "hasFinalExam": course.final_exam is not None and len(course.final_exam.questions) > 0}
    data["trainingArea"] = {"id": str(course.training_area.id), "name": course.training_area.name}
    if detailed:
        data["modules"] = [serialize_module(item, public) for item in course.modules]
        if not public:
            data["finalExam"] = serialize_exam(course.final_exam, include_answers)
    return data


def ordered_course_lessons(course):
    return [lesson for module in course.modules for lesson in module.lessons]


def current_enrollment_progress(enrollment):
    if any(attempt.status == "PASSED" for attempt in enrollment.exam_attempts):
        return 100
    total = len(ordered_course_lessons(enrollment.course))
    return round(len(enrollment.lesson_progress) * 90 / total) if total else 90


def current_exam_status(enrollment):
    if any(attempt.status == "PASSED" for attempt in enrollment.exam_attempts):
        return "PASSED"
    if any(attempt.status == "PENDING_REVIEW" for attempt in enrollment.exam_attempts):
        return "PENDING_REVIEW"
    if enrollment.exam_attempts:
        return enrollment.exam_attempts[-1].status
    return "NOT_STARTED"


def slugify(value):
    # "Gestión Pública" -> "gestion-publica": drop accents before removing what is not a-z or 0-9.
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "-", ascii_value.strip().lower()).strip("-")[:150]
    return value or f"curso-{uuid.uuid4().hex[:8]}"


def course_fields(data, *, partial):
    """Validated course attributes present in the request (all of them when partial is False)."""
    specs = {
        "name": ("name", "El nombre del curso", 180, False),
        "shortDescription": ("short_description", "La descripción corta", 500, False),
        "fullDescription": ("full_description", "La descripción completa", 20000, True),
        "coverUrl": ("cover_url", "La portada", 500, False),
        "modality": ("modality", "La modalidad", 120, False),
        "duration": ("duration", "La duración", 80, False),
        "certification": ("certification", "La certificación", 180, False),
        "endorsement": ("endorsement", "El aval", 180, False),
    }
    fields = {}
    for source, (target, label, max_length, multiline) in specs.items():
        if partial and source not in data:
            continue
        fields[target] = validation.text(data.get(source), label, max_length, required=source == "name", multiline=multiline)
    if "cover_url" in fields:
        fields["cover_url"] = validation.safe_url(fields["cover_url"], "La portada")
    if not partial or "price" in data:
        fields["price"] = validation.money(data.get("price"))
    if not partial or "discountPercent" in data:
        fields["discount_percent"] = validation.integer(data.get("discountPercent"), "El descuento", default=0, minimum=0, maximum=100)
    return fields


def interaction_fields(value, label):
    """Normalized activity data; an activity that cannot be solved is rejected when it is saved."""
    if not isinstance(value, dict) or value.get("type") not in INTERACTION_TYPES:
        raise validation.ValidationError(f"{label}: elige el tipo de actividad interactiva.")
    kind = value["type"]
    options = validation.string_list(value.get("options"), f"{label}, opciones", max_items=20, max_length=300)
    raw_pairs = value.get("pairs") or []
    if not isinstance(raw_pairs, list) or len(raw_pairs) > 20 or not all(isinstance(pair, dict) for pair in raw_pairs):
        raise validation.ValidationError(f"{label}: los pares no tienen un formato válido.")
    pairs = [{"left": validation.text(pair.get("left"), label, 300), "right": validation.text(pair.get("right"), label, 300)} for pair in raw_pairs]
    if kind == "matching":
        if len(pairs) < 2 or not all(pair["left"] and pair["right"] for pair in pairs):
            raise validation.ValidationError(f"{label}: completa al menos dos pares para relacionar.")
        correct = []
    else:
        if len(options) < 2 or not all(options):
            raise validation.ValidationError(f"{label}: completa al menos dos opciones de la actividad.")
        correct = validation.index_list(value.get("correctAnswers"), label, size=len(options)) if kind != "ordering" else [0]
    return {
        "type": kind,
        "prompt": validation.text(value.get("prompt"), f"{label}, enunciado", 2000, multiline=True),
        "options": options,
        "correctAnswers": correct,
        "pairs": pairs,
        "explanation": validation.text(value.get("explanation"), f"{label}, explicación", 2000, multiline=True),
    }


def content_modules(value):
    """Validated modules and lessons, keeping each item's id so save_content can update it in place."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 100:
        raise validation.ValidationError("Los módulos no tienen un formato válido.")
    modules = []
    for module_index, module in enumerate(value):
        label = f"Módulo {module_index + 1}"
        raw_lessons = module.get("lessons") if isinstance(module, dict) else None
        if raw_lessons is None:
            raw_lessons = []
        if not isinstance(module, dict) or not isinstance(raw_lessons, list) or len(raw_lessons) > 200:
            raise validation.ValidationError(f"{label}: el formato no es válido.")
        lessons = []
        for lesson_index, lesson in enumerate(raw_lessons):
            lesson_label = f"{label}, lección {lesson_index + 1}"
            if not isinstance(lesson, dict):
                raise validation.ValidationError(f"{lesson_label}: el formato no es válido.")
            kind = lesson.get("type") if lesson.get("type") in LESSON_TYPES else "text"
            lessons.append({
                "id": str(lesson.get("id") or ""),
                "title": validation.text(lesson.get("title"), lesson_label, 200),
                "lesson_type": kind,
                "content": validation.text(lesson.get("content"), f"{lesson_label}, contenido", 100_000, multiline=True),
                "media_url": validation.safe_url(lesson.get("mediaUrl"), f"{lesson_label}, archivo") or None,
                "duration_minutes": validation.integer(lesson.get("durationMinutes"), f"{lesson_label}, duración", default=0, minimum=0, maximum=1440),
                "is_preview": lesson.get("isPreview") is True,
                "interaction_data": interaction_fields(lesson.get("interaction"), lesson_label) if kind == "interactive" else None,
            })
        modules.append({
            "id": str(module.get("id") or ""),
            "title": validation.text(module.get("title"), label, 200),
            "description": validation.text(module.get("description"), f"{label}, descripción", 5000, multiline=True),
            "lessons": lessons,
        })
    return modules


def training_area_name(data):
    return validation.text(data.get("name"), "El nombre del área de formación", 120, required=True)


def create_api_blueprint(course_service: CourseService) -> Blueprint:
    api = Blueprint("api", __name__)

    @api.get("/health")
    @limiter.exempt
    def health():
        # Checks the database too, so the container healthcheck reports a lost connection.
        try:
            db.session.execute(select(1))
        except Exception:
            current_app.logger.exception("Health check: la base de datos no responde")
            return jsonify({"status": "degraded", "service": "alianza-contigo-api", "database": "unavailable"}), 503
        return jsonify({"status": "ok", "service": "alianza-contigo-api"})

    @api.post("/contact")
    @limiter.limit("10 per hour", key_func=client_ip)
    def contact():
        data = validation.json_object()
        name = validation.person_name(data.get("name"), "El nombre")
        email = validation.email(data.get("email"))
        phone = validation.phone(data.get("phone"))
        course_slug = validation.text(data.get("courseSlug"), "El programa", 160, required=True)
        message = validation.text(data.get("message"), "El mensaje", 3000, required=True, multiline=True)
        if not phone:
            return jsonify({"message": "Completa todos los campos del formulario."}), 400

        course = CourseModel.query.filter_by(slug=course_slug, status="ACTIVO").first()
        if course is None:
            return jsonify({"message": "Selecciona un programa disponible."}), 400

        recipient = current_app.config.get("MAIL_RECIPIENT")
        if not recipient:
            current_app.logger.error("MAIL_RECIPIENT no está configurado")
            return jsonify({"message": "El canal de contacto no está configurado. Inténtalo más tarde."}), 503

        safe_name = escape(name)
        safe_email = escape(email)
        safe_phone = escape(phone)
        safe_course = escape(course.name)
        safe_message = escape(message).replace("\n", "<br>")
        html = branded_html(
            "Nueva consulta de un futuro estudiante",
            f"<strong>{safe_name}</strong> quiere conocer más sobre un programa de Alianza Contigo.",
            f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;border-collapse:collapse">
                <tr><td style="padding:10px 0;color:#667085;width:150px">Programa de interés</td><td style="padding:10px 0;font-weight:700;color:#071C3A">{safe_course}</td></tr>
                <tr><td style="padding:10px 0;color:#667085">Nombre completo</td><td style="padding:10px 0;color:#071C3A">{safe_name}</td></tr>
                <tr><td style="padding:10px 0;color:#667085">Correo electrónico</td><td style="padding:10px 0"><a href="mailto:{safe_email}" style="color:#0E315C">{safe_email}</a></td></tr>
                <tr><td style="padding:10px 0;color:#667085">Teléfono</td><td style="padding:10px 0;color:#071C3A">{safe_phone}</td></tr>
              </table>
              <div style="background:#F7F8FA;border-radius:8px;padding:18px 20px"><strong style="display:block;margin-bottom:8px;color:#071C3A">¿Qué está buscando?</strong>{safe_message}</div>''',
        )
        try:
            if not send_html(recipient, f"Consulta web: {course.name} — {name}", html):
                return jsonify({"message": "No pudimos enviar tu consulta. Inténtalo más tarde."}), 503
        except Exception:
            current_app.logger.exception("No se pudo enviar la consulta de contacto")
            return jsonify({"message": "No pudimos enviar tu consulta. Inténtalo más tarde."}), 502

        return jsonify({"message": "Tu consulta fue enviada correctamente."}), 201

    @api.get("/admin/dashboard")
    @role_required("admin")
    def admin_dashboard():
        students_count = UserModel.query.filter_by(role="student").count()
        active_students = UserModel.query.filter_by(role="student", is_active=True).count()
        active_courses = CourseModel.query.filter_by(status="ACTIVO").count()
        enrollments_count = EnrollmentModel.query.count()
        completed_count = EnrollmentModel.query.filter(EnrollmentModel.completed_at.isnot(None)).count()
        revenue = db.session.query(func.coalesce(func.sum(PaymentOrderModel.amount), 0)).filter(PaymentOrderModel.status == "APPROVED").scalar()
        pending_payments = PaymentOrderModel.query.filter_by(status="PENDING", payment_method="TRANSFER").count()
        pending_evaluations = ExamAttemptModel.query.filter_by(status="PENDING_REVIEW").count()

        now = datetime.now(timezone.utc)
        month_keys = []
        year, month = now.year, now.month
        for offset in range(5, -1, -1):
            target_month = month - offset
            target_year = year
            while target_month <= 0:
                target_month += 12
                target_year -= 1
            month_keys.append((target_year, target_month))
        monthly_counts = {key: 0 for key in month_keys}
        for enrolled_at, in db.session.query(EnrollmentModel.enrolled_at).all():
            key = (enrolled_at.year, enrolled_at.month)
            if key in monthly_counts:
                monthly_counts[key] += 1
        month_names = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        enrollments_by_month = [
            {"month": f"{month_names[item_month - 1]} {str(item_year)[-2:]}", "enrollments": monthly_counts[(item_year, item_month)]}
            for item_year, item_month in month_keys
        ]

        students_by_course = [
            {"course": name, "students": students}
            for name, students in db.session.query(CourseModel.name, func.count(EnrollmentModel.id))
            .outerjoin(EnrollmentModel, EnrollmentModel.course_id == CourseModel.id)
            .group_by(CourseModel.id, CourseModel.name)
            .order_by(CourseModel.name.asc())
        ]

        activity = []
        recent_enrollments = EnrollmentModel.query.options(selectinload(EnrollmentModel.student), selectinload(EnrollmentModel.course))
        for enrollment in recent_enrollments.order_by(EnrollmentModel.enrolled_at.desc()).limit(5):
            activity.append(
                {
                    "id": f"enrollment-{enrollment.id}",
                    "type": "enrollment",
                    "text": f"{enrollment.student.first_name} {enrollment.student.last_name} se matriculó en {enrollment.course.name}",
                    "createdAt": enrollment.enrolled_at.isoformat(),
                }
            )
        for order in PaymentOrderModel.query.options(selectinload(PaymentOrderModel.course)).order_by(PaymentOrderModel.created_at.desc()).limit(5):
            labels = {"PENDING": "Pago pendiente", "APPROVED": "Pago aprobado", "REJECTED": "Pago rechazado"}
            activity.append(
                {
                    "id": f"payment-{order.id}",
                    "type": "payment",
                    "text": f"{labels.get(order.status, 'Pago')} de ${float(order.amount):,.2f} - {order.course.name}",
                    "createdAt": order.created_at.isoformat(),
                }
            )
        for student in UserModel.query.filter_by(role="student").order_by(UserModel.created_at.desc()).limit(5):
            activity.append(
                {
                    "id": f"student-{student.id}",
                    "type": "student",
                    "text": f"Nuevo estudiante registrado: {student.first_name} {student.last_name}",
                    "createdAt": student.created_at.isoformat(),
                }
            )
        activity.sort(key=lambda item: item["createdAt"], reverse=True)

        return jsonify(
            {
                "stats": {
                    "students": students_count,
                    "activeStudents": active_students,
                    "activeCourses": active_courses,
                    "enrollments": enrollments_count,
                    "revenue": float(revenue),
                    "completedCourses": completed_count,
                    "completionRate": round(completed_count * 100 / enrollments_count) if enrollments_count else 0,
                    "pendingPayments": pending_payments,
                    "pendingEvaluations": pending_evaluations,
                },
                "enrollmentsByMonth": enrollments_by_month,
                "studentsByCourse": students_by_course,
                "recentActivity": activity[:8],
            }
        )

    @api.get("/courses")
    def list_courses():
        rows = CourseModel.query.options(*COURSE_TREE).filter_by(status="ACTIVO").order_by(CourseModel.updated_at.desc()).all()
        return jsonify([serialize_course(row) for row in rows])

    @api.get("/training-areas")
    def list_training_areas():
        rows = TrainingAreaModel.query.order_by(TrainingAreaModel.name.asc()).all()
        return jsonify([{"id": str(row.id), "name": row.name, "coursesCount": len(row.courses)} for row in rows])

    @api.post("/training-areas")
    @role_required("admin")
    def create_training_area():
        name = training_area_name(validation.json_object())
        if TrainingAreaModel.query.filter(db.func.lower(TrainingAreaModel.name) == name.lower()).first():
            return jsonify({"message": "Ya existe un área de formación con ese nombre."}), 409
        area = TrainingAreaModel(name=name)
        db.session.add(area)
        db.session.commit()
        return jsonify({"id": str(area.id), "name": area.name, "coursesCount": 0}), 201

    @api.put("/training-areas/<area_id>")
    @role_required("admin")
    def update_training_area(area_id):
        try:
            area = db.session.get(TrainingAreaModel, uuid.UUID(area_id))
        except ValueError:
            area = None
        if area is None:
            return jsonify({"message": "Área de formación no encontrada."}), 404
        name = training_area_name(validation.json_object())
        duplicate = TrainingAreaModel.query.filter(db.func.lower(TrainingAreaModel.name) == name.lower(), TrainingAreaModel.id != area.id).first()
        if duplicate:
            return jsonify({"message": "Ya existe un área de formación con ese nombre."}), 409
        area.name = name
        db.session.commit()
        return jsonify({"id": str(area.id), "name": area.name, "coursesCount": len(area.courses)})

    @api.delete("/training-areas/<area_id>")
    @role_required("admin")
    def delete_training_area(area_id):
        try:
            area = db.session.get(TrainingAreaModel, uuid.UUID(area_id))
        except ValueError:
            area = None
        if area is None:
            return jsonify({"message": "Área de formación no encontrada."}), 404
        if area.courses:
            return jsonify({"message": "No puedes eliminar un área que tiene cursos asignados."}), 409
        db.session.delete(area)
        db.session.commit()
        return "", 204

    @api.get("/courses/manage")
    @role_required("admin", "teacher")
    def manage_courses():
        rows = CourseModel.query.options(*COURSE_TREE).order_by(CourseModel.updated_at.desc()).all()
        return jsonify([serialize_course(row) for row in rows])

    @api.get("/courses/<slug>")
    def get_course(slug: str):
        course = CourseModel.query.options(*COURSE_TREE).filter_by(slug=slug, status="ACTIVO").first()
        if course is None:
            return jsonify({"error": "course_not_found", "message": "Programa no encontrado"}), 404
        return jsonify(serialize_course(course, detailed=True, public=True))

    @api.get("/courses/<slug>/author")
    @role_required("admin")
    def get_course_for_author(slug: str):
        course = CourseModel.query.filter_by(slug=slug).first()
        if course is None:
            return jsonify({"error": "course_not_found", "message": "Programa no encontrado"}), 404
        return jsonify(serialize_course(course, detailed=True, include_answers=True))

    @api.post("/courses")
    @role_required("admin")
    def create_course():
        data = validation.json_object()
        fields = course_fields(data, partial=False)
        if data.get("status") == "ACTIVO":
            return jsonify({"message": "Primero crea el curso, agrega al menos un módulo y configura su examen final antes de activarlo."}), 400
        area = db.session.get(TrainingAreaModel, validation.uuid_or_none(data.get("trainingAreaId"))) if validation.uuid_or_none(data.get("trainingAreaId")) else None
        if area is None:
            return jsonify({"message": "Selecciona un área de formación válida."}), 400
        slug = slugify(fields["name"])
        base = slug
        counter = 2
        while CourseModel.query.filter_by(slug=slug).first():
            slug = f"{base}-{counter}"
            counter += 1
        defaults = {"modality": "Virtual", "duration": "A tu ritmo", "certification": "Certificado de aprobación"}
        for key, value in defaults.items():
            fields[key] = fields[key] or value
        fields["cover_url"] = fields["cover_url"] or None
        course = CourseModel(training_area=area, slug=slug, status="CERRADO", **fields)
        db.session.add(course)
        db.session.flush()
        course.final_exam = FinalExamModel(title="Evaluación final", instructions="Completa la evaluación para finalizar el curso.")
        db.session.commit()
        return jsonify(serialize_course(course, True, True)), 201

    @api.put("/courses/<slug>")
    @role_required("admin")
    def update_course(slug):
        course = CourseModel.query.filter_by(slug=slug).first_or_404()
        data = validation.json_object()
        fields = course_fields(data, partial=True)
        if "trainingAreaId" in data:
            area_uuid = validation.uuid_or_none(data["trainingAreaId"])
            area = db.session.get(TrainingAreaModel, area_uuid) if area_uuid else None
            if area is None:
                return jsonify({"message": "Selecciona un área de formación válida."}), 400
            course.training_area = area
        if "cover_url" in fields:
            fields["cover_url"] = fields["cover_url"] or None
        for target, value in fields.items():
            setattr(course, target, value)
        if data.get("status") in {"ACTIVO", "CERRADO"}:
            if data["status"] == "ACTIVO" and (not course.modules or not course.final_exam or not course.final_exam.questions):
                return jsonify({"message": "Para activar el curso necesitas al menos un módulo y una pregunta en el examen final."}), 400
            course.status = data["status"]
        db.session.commit()
        return jsonify(serialize_course(course, True, True))

    @api.delete("/courses/<slug>")
    @role_required("admin")
    def delete_course(slug):
        course = CourseModel.query.filter_by(slug=slug).first_or_404()
        # Enrollments and payments are academic and accounting records: never delete them with the course.
        has_history = (
            EnrollmentModel.query.filter_by(course_id=course.id).first() is not None
            or PaymentOrderModel.query.filter_by(course_id=course.id).first() is not None
        )
        if has_history:
            return jsonify({"message": "Este curso tiene estudiantes o pagos registrados y no se puede eliminar. Ciérralo para retirarlo del catálogo."}), 409
        db.session.delete(course)
        db.session.commit()
        return "", 204

    @api.put("/courses/<slug>/content")
    @role_required("admin")
    def save_content(slug):
        course = CourseModel.query.filter_by(slug=slug).first_or_404()
        modules = content_modules(validation.json_object().get("modules"))
        if course.status == "ACTIVO" and not modules:
            return jsonify({"message": "Un curso activo debe conservar al menos un módulo."}), 400
        # Update rows in place by id: recreating them would cascade-delete every student's lesson progress.
        # Ids that do not belong to this course are treated as new items.
        existing_modules = {str(module.id): module for module in course.modules}
        existing_lessons = {str(lesson.id): lesson for module in course.modules for lesson in module.lessons}
        kept_modules = []
        for module_index, module_data in enumerate(modules):
            module = existing_modules.pop(module_data["id"], None) or CourseModuleModel()
            module.title = module_data["title"] or f"Módulo {module_index + 1}"
            module.description = module_data["description"]
            module.position = module_index
            lessons = []
            for lesson_index, lesson_data in enumerate(module_data["lessons"]):
                lesson = existing_lessons.pop(lesson_data["id"], None) or LessonModel()
                for key, value in lesson_data.items():
                    if key != "id":
                        setattr(lesson, key, value)
                lesson.title = lesson.title or f"Lección {lesson_index + 1}"
                lesson.position = lesson_index
                lessons.append(lesson)
            module.lessons = lessons
            kept_modules.append(module)
        course.modules = kept_modules  # modules and lessons left out are deleted (delete-orphan)
        db.session.commit()
        return jsonify(serialize_course(course, True, True))

    @api.put("/courses/<slug>/exam")
    @role_required("admin")
    def save_exam(slug):
        course = CourseModel.query.filter_by(slug=slug).first_or_404()
        data = validation.json_object()
        raw_questions = data.get("questions")
        if not raw_questions or not isinstance(raw_questions, list):
            return jsonify({"message": "El examen final debe tener al menos una pregunta."}), 400
        if len(raw_questions) > 200:
            return jsonify({"message": "El examen admite hasta 200 preguntas."}), 400
        questions = []
        for index, item in enumerate(raw_questions):
            label = f"Pregunta {index + 1}"
            if not isinstance(item, dict):
                raise validation.ValidationError(f"{label}: el formato no es válido.")
            prompt = validation.text(item.get("prompt"), label, 2000, multiline=True)
            options = validation.string_list(item.get("options"), f"{label}, opciones", max_items=10, max_length=500)
            if not prompt or len(options) < 2 or not all(options):
                return jsonify({"message": f"Completa la pregunta {index + 1}, sus opciones y respuesta correcta."}), 400
            correct = validation.index_list(item.get("correctAnswers"), label, size=len(options))
            points = validation.integer(item.get("points") or None, f"{label}, puntaje", default=1, minimum=1, maximum=100)
            questions.append(ExamQuestionModel(prompt=prompt, question_type="single_choice", options=options, correct_answers=correct, points=points, position=index))
        exam = course.final_exam or FinalExamModel(course=course)
        exam.title = validation.text(data.get("title"), "El título del examen", 200) or "Evaluación final"
        exam.instructions = validation.text(data.get("instructions"), "Las instrucciones", 5000, multiline=True)
        exam.time_limit_minutes = validation.integer(data.get("timeLimitMinutes") or None, "El tiempo límite", default=45, minimum=1, maximum=600)
        exam.attempts_allowed = validation.integer(data.get("attemptsAllowed") or None, "Los intentos", default=1, minimum=1, maximum=20)
        exam.passing_score = validation.integer(data.get("passingScore") or None, "El puntaje mínimo", default=70, minimum=1, maximum=100)
        exam.questions = questions
        db.session.commit()
        return jsonify(serialize_exam(exam, True))

    @api.post("/uploads")
    @limiter.limit("120 per hour")
    @role_required("admin")
    def upload_file():
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            return jsonify({"message": "Selecciona un archivo."}), 400
        extension = uploaded.filename.rsplit(".", 1)[-1].lower() if "." in uploaded.filename else ""
        if extension not in ALLOWED_UPLOADS:
            return jsonify({"message": "Formato no permitido. Usa PDF, imagen, MP4 o WebM."}), 400
        is_video = extension in {"mp4", "webm"}
        max_mb = current_app.config[
            "MAX_VIDEO_UPLOAD_MB" if is_video else "MAX_DOCUMENT_UPLOAD_MB"
        ]
        if request.content_length and request.content_length > max_mb * 1024 * 1024:
            return jsonify({"message": f"El archivo supera el límite de {max_mb} MB."}), 413
        os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
        filename = f"{uuid.uuid4().hex}-{secure_filename(uploaded.filename)}"
        uploaded.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))
        return jsonify({"url": f"/api/v1/uploads/{filename}"}), 201

    @api.get("/uploads/<filename>")
    def uploaded_file(filename):
        return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)

    @api.get("/courses/<slug>/teaching")
    @role_required("teacher", "admin")
    def teaching_course(slug):
        course = CourseModel.query.filter_by(slug=slug).first_or_404()
        enrollments = EnrollmentModel.query.filter_by(course_id=course.id).order_by(EnrollmentModel.enrolled_at.desc()).all()
        return jsonify({"course": serialize_course(course), "students": [{"enrollmentId": str(item.id), "studentId": str(item.student.id), "name": f"{item.student.first_name} {item.student.last_name}", "email": item.student.email, "progressPercent": current_enrollment_progress(item), "examSubmittedAt": item.exam_submitted_at.isoformat() if item.exam_submitted_at else None, "examScore": float(item.exam_score) if item.exam_score is not None else None, "examStatus": current_exam_status(item), "teacherFeedback": item.teacher_feedback} for item in enrollments]})

    @api.patch("/enrollments/<enrollment_id>/grade")
    @role_required("teacher", "admin")
    def grade_enrollment(enrollment_id):
        return jsonify({"message": "Las calificaciones se calculan automáticamente. Usa la revisión del intento para registrar retroalimentación."}), 410

    @api.get("/student/enrollments")
    @role_required("student")
    def student_enrollments():
        student_id = uuid.UUID(get_jwt_identity())
        rows = (
            EnrollmentModel.query.options(
                selectinload(EnrollmentModel.course).options(*COURSE_TREE),
                selectinload(EnrollmentModel.lesson_progress),
                selectinload(EnrollmentModel.exam_attempts),
            )
            .filter_by(student_id=student_id)
            .order_by(EnrollmentModel.enrolled_at.desc())
            .all()
        )
        return jsonify({"enrollments": [{"id": str(item.id), "course": serialize_course(item.course, detailed=True), "progressPercent": current_enrollment_progress(item), "completedLessonIds": [str(progress.lesson_id) for progress in item.lesson_progress], "examScore": float(item.exam_score) if item.exam_score is not None else None, "examStatus": current_exam_status(item), "completedAt": item.completed_at.isoformat() if item.completed_at else None, "enrolledAt": item.enrolled_at.isoformat()} for item in rows]})

    @api.post("/student/enrollments/<enrollment_id>/lessons/<lesson_id>/complete")
    @limiter.limit("120 per minute")
    @role_required("student")
    def complete_lesson(enrollment_id, lesson_id):
        try:
            enrollment_uuid = uuid.UUID(enrollment_id)
            lesson_uuid = uuid.UUID(lesson_id)
        except ValueError:
            return jsonify({"message": "La lección no es válida."}), 404
        # Locked so two quick clicks cannot insert the same lesson progress twice.
        enrollment = db.session.get(EnrollmentModel, enrollment_uuid, with_for_update=True)
        if not enrollment or enrollment.student_id != uuid.UUID(get_jwt_identity()):
            return jsonify({"message": "No tienes acceso a esta matrícula."}), 404
        ordered = ordered_course_lessons(enrollment.course)
        ordered_ids = [lesson.id for lesson in ordered]
        if lesson_uuid not in ordered_ids:
            return jsonify({"message": "La lección no pertenece a este curso."}), 404
        completed_ids = {progress.lesson_id for progress in enrollment.lesson_progress}
        if lesson_uuid not in completed_ids:
            lesson = next(item for item in ordered if item.id == lesson_uuid)
            if lesson.lesson_type == "interactive":
                activity = lesson.interaction_data or {}
                answer = validation.json_object().get("interactionAnswer")
                activity_type = activity.get("type")
                if activity_type in {"multiple_choice", "true_false"}:
                    expected = (activity.get("correctAnswers") or [None])[0]
                    correct = answer == expected
                elif activity_type == "ordering":
                    correct = answer == list(range(len(activity.get("options") or [])))
                elif activity_type == "matching":
                    correct = answer == list(range(len(activity.get("pairs") or [])))
                else:
                    correct = False
                if not correct:
                    return jsonify({"message": "Resuelve correctamente la actividad antes de continuar."}), 422
            first_pending = next((item_id for item_id in ordered_ids if item_id not in completed_ids), None)
            if first_pending != lesson_uuid:
                return jsonify({"message": "Completa primero el contenido anterior para desbloquear esta lección."}), 409
            db.session.add(LessonProgressModel(enrollment_id=enrollment.id, lesson_id=lesson_uuid))
            completed_ids.add(lesson_uuid)
        enrollment.progress_percent = round(len(completed_ids) * 90 / len(ordered_ids)) if ordered_ids else 90
        db.session.commit()
        return jsonify({"message": "Lección completada.", "progressPercent": enrollment.progress_percent, "completedLessonIds": [str(item_id) for item_id in completed_ids]})

    @api.get("/admin/students")
    @role_required("admin")
    def admin_students():
        students = UserModel.query.filter_by(role="student").order_by(UserModel.created_at.desc()).all()
        counts = dict(db.session.query(EnrollmentModel.student_id, func.count(EnrollmentModel.id)).group_by(EnrollmentModel.student_id).all())
        return jsonify({"students": [{**student.to_dict(), "createdAt": student.created_at.isoformat(), "coursesCount": counts.get(student.id, 0)} for student in students]})

    @api.get("/admin/students/<student_id>")
    @role_required("admin")
    def admin_student_detail(student_id):
        try:
            student_uuid = uuid.UUID(student_id)
        except ValueError:
            return jsonify({"message": "Estudiante no encontrado."}), 404
        student = db.session.get(UserModel, student_uuid)
        if not student or student.role != "student":
            return jsonify({"message": "Estudiante no encontrado."}), 404
        rows = EnrollmentModel.query.filter_by(student_id=student.id).order_by(EnrollmentModel.enrolled_at.desc()).all()
        return jsonify({"student": {**student.to_dict(), "createdAt": student.created_at.isoformat()}, "enrollments": [{"id": str(item.id), "course": serialize_course(item.course), "progressPercent": current_enrollment_progress(item), "examScore": float(item.exam_score) if item.exam_score is not None else None, "enrolledAt": item.enrolled_at.isoformat()} for item in rows]})

    return api
