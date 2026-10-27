from dataclasses import asdict

import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename
from flask_jwt_extended import get_jwt_identity
from markupsafe import escape
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.application.services.course_service import CourseService
from app.extensions import client_ip, db, limiter
from app.infrastructure.persistence.models import CourseModel, CourseModuleModel, EnrollmentModel, ExamAttemptModel, ExamQuestionModel, FinalExamModel, LessonModel, LessonProgressModel, PaymentOrderModel, TrainingAreaModel, UserModel
from app.presentation.auth_api import role_required
from app.infrastructure.email_service import branded_html, send_html

ALLOWED_UPLOADS = {"pdf", "png", "jpg", "jpeg", "webp", "mp4", "webm"}
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
    data = {"id": str(course.id), "slug": course.slug, "name": course.name, "shortDescription": course.short_description, "fullDescription": course.full_description, "coverUrl": course.cover_url, "modality": course.modality, "duration": course.duration, "certification": course.certification, "endorsement": course.endorsement, "price": float(course.price), "discountPercent": course.discount_percent, "finalPrice": round(float(course.price) * (100 - course.discount_percent) / 100, 2), "status": course.status, "modulesCount": len(course.modules), "lessonsCount": sum(len(item.lessons) for item in course.modules), "hasFinalExam": course.final_exam is not None and len(course.final_exam.questions) > 0}
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
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return value or f"curso-{uuid.uuid4().hex[:8]}"


def create_api_blueprint(course_service: CourseService) -> Blueprint:
    api = Blueprint("api", __name__)

    @api.get("/health")
    @limiter.exempt
    def health():
        return jsonify({"status": "ok", "service": "alianza-contigo-api"})

    @api.post("/contact")
    @limiter.limit("10 per hour", key_func=client_ip)
    def contact():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        phone = (data.get("phone") or "").strip()
        course_slug = (data.get("courseSlug") or "").strip()
        message = (data.get("message") or "").strip()

        if not all((name, email, phone, course_slug, message)):
            return jsonify({"message": "Completa todos los campos del formulario."}), 400
        if len(name) > 160 or len(email) > 254 or len(phone) > 40 or len(message) > 3000:
            return jsonify({"message": "Uno de los campos supera la longitud permitida."}), 400
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            return jsonify({"message": "Ingresa un correo electrónico válido."}), 400

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
        approved_orders = PaymentOrderModel.query.filter_by(status="APPROVED").all()
        revenue = sum((order.amount or Decimal("0") for order in approved_orders), Decimal("0"))
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

        students_by_course = []
        for course in CourseModel.query.order_by(CourseModel.name.asc()).all():
            students_by_course.append(
                {
                    "course": course.name,
                    "students": EnrollmentModel.query.filter_by(course_id=course.id).count(),
                }
            )

        activity = []
        for enrollment in EnrollmentModel.query.order_by(EnrollmentModel.enrolled_at.desc()).limit(5):
            activity.append(
                {
                    "id": f"enrollment-{enrollment.id}",
                    "type": "enrollment",
                    "text": f"{enrollment.student.first_name} {enrollment.student.last_name} se matriculó en {enrollment.course.name}",
                    "createdAt": enrollment.enrolled_at.isoformat(),
                }
            )
        for order in PaymentOrderModel.query.order_by(PaymentOrderModel.created_at.desc()).limit(5):
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
        name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
        if not name:
            return jsonify({"message": "El nombre del área de formación es obligatorio."}), 400
        if len(name) > 120:
            return jsonify({"message": "El nombre no puede superar los 120 caracteres."}), 400
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
        name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
        if not name or len(name) > 120:
            return jsonify({"message": "Ingresa un nombre válido de hasta 120 caracteres."}), 400
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
        data = request.get_json(silent=True) or {}
        if not (data.get("name") or "").strip():
            return jsonify({"message": "El nombre del curso es obligatorio."}), 400
        if data.get("status") == "ACTIVO":
            return jsonify({"message": "Primero crea el curso, agrega al menos un módulo y configura su examen final antes de activarlo."}), 400
        try:
            area = db.session.get(TrainingAreaModel, uuid.UUID(data.get("trainingAreaId"))) if data.get("trainingAreaId") else None
        except (ValueError, TypeError):
            area = None
        if area is None:
            return jsonify({"message": "Selecciona un área de formación válida."}), 400
        slug = slugify(data["name"])
        base = slug
        counter = 2
        while CourseModel.query.filter_by(slug=slug).first():
            slug = f"{base}-{counter}"
            counter += 1
        course = CourseModel(training_area=area, slug=slug, name=data["name"].strip(), short_description=(data.get("shortDescription") or "").strip(), full_description=data.get("fullDescription") or "", cover_url=data.get("coverUrl") or None, modality=data.get("modality") or "Virtual", duration=data.get("duration") or "A tu ritmo", certification=data.get("certification") or "Certificado de aprobación", endorsement=data.get("endorsement") or "", price=Decimal(str(data.get("price") or 0)), discount_percent=max(0, min(100, int(data.get("discountPercent") or 0))), status=data.get("status") if data.get("status") in {"ACTIVO", "CERRADO"} else "CERRADO")
        db.session.add(course)
        db.session.flush()
        course.final_exam = FinalExamModel(title="Evaluación final", instructions="Completa la evaluación para finalizar el curso.")
        db.session.commit()
        return jsonify(serialize_course(course, True, True)), 201

    @api.put("/courses/<slug>")
    @role_required("admin")
    def update_course(slug):
        course = CourseModel.query.filter_by(slug=slug).first_or_404()
        data = request.get_json(silent=True) or {}
        if "trainingAreaId" in data:
            try:
                area = db.session.get(TrainingAreaModel, uuid.UUID(data["trainingAreaId"]))
            except (ValueError, TypeError):
                area = None
            if area is None:
                return jsonify({"message": "Selecciona un área de formación válida."}), 400
            course.training_area = area
        for source, target in [("name", "name"), ("shortDescription", "short_description"), ("fullDescription", "full_description"), ("coverUrl", "cover_url"), ("modality", "modality"), ("duration", "duration"), ("certification", "certification"), ("endorsement", "endorsement")]:
            if source in data:
                setattr(course, target, data[source])
        if "price" in data:
            try:
                course.price = max(Decimal("0"), Decimal(str(data["price"])))
            except InvalidOperation:
                return jsonify({"message": "El precio no es válido."}), 400
        if "discountPercent" in data:
            course.discount_percent = max(0, min(100, int(data["discountPercent"])))
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
        db.session.delete(course)
        db.session.commit()
        return "", 204

    @api.put("/courses/<slug>/content")
    @role_required("admin")
    def save_content(slug):
        course = CourseModel.query.filter_by(slug=slug).first_or_404()
        modules = (request.get_json(silent=True) or {}).get("modules", [])
        if course.status == "ACTIVO" and not modules:
            return jsonify({"message": "Un curso activo debe conservar al menos un módulo."}), 400
        course.modules.clear()
        for module_index, module_data in enumerate(modules):
            module = CourseModuleModel(title=(module_data.get("title") or f"Módulo {module_index + 1}").strip(), description=module_data.get("description") or "", position=module_index)
            for lesson_index, lesson_data in enumerate(module_data.get("lessons", [])):
                lesson_type = lesson_data.get("type") if lesson_data.get("type") in {"video", "text", "image", "pdf", "file", "interactive"} else "text"
                module.lessons.append(LessonModel(title=(lesson_data.get("title") or f"Lección {lesson_index + 1}").strip(), lesson_type=lesson_type, content=lesson_data.get("content") or "", media_url=lesson_data.get("mediaUrl") or None, duration_minutes=max(0, int(lesson_data.get("durationMinutes") or 0)), is_preview=bool(lesson_data.get("isPreview")), interaction_data=lesson_data.get("interaction") if lesson_type == "interactive" else None, position=lesson_index))
            course.modules.append(module)
        db.session.commit()
        return jsonify(serialize_course(course, True, True))

    @api.put("/courses/<slug>/exam")
    @role_required("admin")
    def save_exam(slug):
        course = CourseModel.query.filter_by(slug=slug).first_or_404()
        data = request.get_json(silent=True) or {}
        if not data.get("questions"):
            return jsonify({"message": "El examen final debe tener al menos una pregunta."}), 400
        exam = course.final_exam or FinalExamModel(course=course)
        exam.title = data.get("title") or "Evaluación final"
        exam.instructions = data.get("instructions") or ""
        exam.time_limit_minutes = max(1, int(data.get("timeLimitMinutes") or 45))
        exam.attempts_allowed = max(1, int(data.get("attemptsAllowed") or 1))
        exam.passing_score = max(1, min(100, int(data.get("passingScore") or 70)))
        exam.questions.clear()
        for index, item in enumerate(data["questions"]):
            if not (item.get("prompt") or "").strip() or len(item.get("options") or []) < 2 or not item.get("correctAnswers"):
                return jsonify({"message": f"Completa la pregunta {index + 1}, sus opciones y respuesta correcta."}), 400
            exam.questions.append(ExamQuestionModel(prompt=item["prompt"].strip(), question_type="single_choice", options=item["options"], correct_answers=item["correctAnswers"], points=max(1, int(item.get("points") or 1)), position=index))
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
                answer = (request.get_json(silent=True) or {}).get("interactionAnswer")
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
