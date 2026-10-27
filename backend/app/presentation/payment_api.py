import os
import uuid
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from html import escape
from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, current_app, jsonify, redirect, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import func, select
from werkzeug.utils import secure_filename

from app.extensions import db, limiter
from app.infrastructure.email_service import branded_html, send_html_later
from app.infrastructure.persistence.models import CourseModel, EnrollmentModel, PaymentOrderModel, UserModel
from app.presentation.auth_api import role_required

payment_api = Blueprint("payments", __name__)
PROOF_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}


def current_user():
    return db.session.get(UserModel, uuid.UUID(get_jwt_identity()))


def final_price(course):
    return (course.price * Decimal(100 - course.discount_percent) / Decimal(100)).quantize(Decimal("0.01"))


def serialize_order(order):
    return {"id": str(order.id), "reference": order.reference, "courseName": order.course.name, "courseSlug": order.course.slug, "studentName": f"{order.student.first_name} {order.student.last_name}", "studentEmail": order.student.email, "paymentMethod": order.payment_method, "provider": order.provider, "providerTransactionId": order.provider_transaction_id, "currency": order.currency, "amount": float(order.amount), "status": order.status, "proofUrl": order.proof_url, "rejectionComment": order.rejection_comment, "createdAt": order.created_at.isoformat(), "paidAt": order.paid_at.isoformat() if order.paid_at else None}


def lock_student(student_id):
    """Serialize checkouts and enrollments of one student so concurrent requests cannot duplicate them."""
    db.session.execute(select(UserModel.id).where(UserModel.id == student_id).with_for_update())


def ensure_available(course_slug, student):
    lock_student(student.id)
    course = CourseModel.query.filter_by(slug=course_slug, status="ACTIVO").first()
    if not course:
        return None, (jsonify({"message": "Este curso no está disponible."}), 404)
    if EnrollmentModel.query.filter_by(course_id=course.id, student_id=student.id).first():
        return None, (jsonify({"message": "Ya tienes acceso a este curso."}), 409)
    pending = PaymentOrderModel.query.filter_by(course_id=course.id, student_id=student.id, payment_method="TRANSFER", status="PENDING").first()
    if pending:
        return None, (jsonify({"message": "Ya tienes una transferencia pendiente de validación."}), 409)
    return course, None


def enroll(course, student):
    lock_student(student.id)
    enrollment = EnrollmentModel.query.filter_by(course_id=course.id, student_id=student.id).first()
    if not enrollment:
        enrollment = EnrollmentModel(course_id=course.id, student_id=student.id)
        db.session.add(enrollment)
    return enrollment


def clean(value):
    return escape(str(value or ""))


@payment_api.get("/bank-details")
@role_required("student")
def bank_details():
    return jsonify({"bank": current_app.config["BANK_NAME"], "accountType": current_app.config["BANK_ACCOUNT_TYPE"], "accountNumber": current_app.config["BANK_ACCOUNT_NUMBER"], "holder": current_app.config["BANK_ACCOUNT_HOLDER"], "holderId": current_app.config["BANK_ACCOUNT_ID"]})


@payment_api.post("/card")
@limiter.limit("20 per hour")
@role_required("student")
def card_checkout():
    student = current_user()
    data = request.get_json(silent=True) or {}
    course, failure = ensure_available(data.get("courseSlug"), student)
    if failure:
        return failure
    token = current_app.config.get("PAYPHONE_TOKEN")
    store_id = current_app.config.get("PAYPHONE_STORE_ID")
    if not token or not store_id:
        return jsonify({"message": "El pago con tarjeta no está disponible en este momento."}), 503
    amount = final_price(course)
    cents = int(amount * 100)
    if cents <= 0:
        return jsonify({"message": "El monto del curso no permite un pago con tarjeta."}), 400
    order = PaymentOrderModel(reference=f"CARD-{uuid.uuid4().hex.upper()}", course=course, student=student, payment_method="PAYPHONE", provider="PAYPHONE", currency="USD", amount=amount, status="PENDING")
    db.session.add(order)
    db.session.commit()
    response = jsonify({"token": token, "storeId": store_id, "clientTransactionId": order.reference, "reference": f"Inscripción {course.name} · {order.reference}", "amount": cents, "amountWithoutTax": cents, "currency": "USD", "email": student.email})
    response.headers["Cache-Control"] = "no-store"
    return response, 201


def payphone_result(transaction_id, client_tx_id):
    query = urlencode({"id": transaction_id, "clientTransactionId": client_tx_id})
    return redirect(f'{current_app.config["FRONTEND_URL"].rstrip("/")}/pagar?{query}', code=302)


@payment_api.post("/payphone/confirm")
@limiter.limit("30 per hour")
@role_required("student")
def payphone_confirm():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"message": "Datos de confirmación inválidos."}), 400
    client_tx_id = str(data.get("clientTransactionId", ""))
    transaction_id = str(data.get("id", ""))
    # Locked so a repeated confirmation (refresh, double click) waits for the first one to finish.
    order = PaymentOrderModel.query.filter_by(reference=client_tx_id, provider="PAYPHONE", student_id=current_user().id).with_for_update().first()
    if not order or not transaction_id.isdecimal() or int(transaction_id) <= 0:
        return jsonify({"message": "No encontramos esta transacción PayPhone."}), 400
    status = confirm_payphone_order(order, transaction_id)
    paid_at = order.paid_at
    if paid_at and paid_at.tzinfo is None:
        paid_at = paid_at.replace(tzinfo=timezone.utc)
    messages = {
        "approved": "Pago aprobado. Ya tienes acceso al curso.",
        "rejected": order.rejection_comment or "PayPhone canceló o rechazó la transacción.",
        "error": "No pudimos confirmar el pago con PayPhone. Contacta a soporte si recibiste un cobro.",
    }
    return jsonify({"status": status, "message": messages[status], "reference": order.reference, "courseName": order.course.name, "courseSlug": order.course.slug, "amount": float(order.amount), "currency": order.currency, "providerTransactionId": order.provider_transaction_id, "paidAt": paid_at.isoformat() if paid_at else None, "redirect": f"/app/classroom/{order.course.slug}" if status == "approved" else None}), 200 if status != "error" else 502


@payment_api.get("/payphone/return")
def payphone_return():
    """Compatibility return URL for applications configured with the backend URL."""
    client_tx_id = request.args.get("clientTransactionId", "")
    transaction_id = request.args.get("id", "")
    return payphone_result(transaction_id, client_tx_id)


def confirm_payphone_order(order, transaction_id):
    if order.status == "APPROVED":
        return "approved" if order.provider_transaction_id == transaction_id else "error"
    if order.status == "REJECTED":
        return "rejected" if order.provider_transaction_id == transaction_id else "error"
    token = current_app.config.get("PAYPHONE_TOKEN")
    if not token:
        current_app.logger.error("PayPhone no está configurado para confirmar pagos")
        return "error"
    payload = json.dumps({"id": int(transaction_id), "clientTxId": order.reference}).encode("utf-8")
    confirmation_request = Request(
        "https://paymentbox.payphonetodoesposible.com/api/confirm",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(confirmation_request, timeout=15) as response:
            confirmation = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError):
        current_app.logger.exception("No se pudo confirmar la transacción PayPhone %s", order.reference)
        return "error"
    if not isinstance(confirmation, dict):
        current_app.logger.error("Respuesta PayPhone inválida para %s", order.reference)
        return "error"
    if str(confirmation.get("clientTransactionId")) != order.reference or str(confirmation.get("transactionId")) != transaction_id:
        current_app.logger.error("Respuesta PayPhone inconsistente para %s", order.reference)
        return "error"
    if confirmation.get("statusCode") == 3 and confirmation.get("transactionStatus") == "Approved":
        if confirmation.get("currency") != "USD" or confirmation.get("amount") != int(order.amount * 100):
            current_app.logger.error("Monto o moneda PayPhone inconsistente para %s", order.reference)
            return "error"
        order.status = "APPROVED"
        order.provider_transaction_id = transaction_id
        order.paid_at = datetime.now(timezone.utc)
        order.reviewed_at = order.paid_at
        enroll(order.course, order.student)
        db.session.commit()
        send_html_later(order.student.email, "Tu inscripción está activa — Alianza Contigo", branded_html("¡Pago aprobado!", f"Hola {clean(order.student.first_name)},", f"Tu pago de <strong>${order.amount}</strong> para <strong>{clean(order.course.name)}</strong> fue aprobado. Ya puedes comenzar a estudiar.", "Ir a mi curso", f'{current_app.config["FRONTEND_URL"]}/app/classroom/{order.course.slug}'))
        return "approved"
    if confirmation.get("statusCode") == 2 or confirmation.get("transactionStatus") == "Canceled":
        order.status = "REJECTED"
        order.provider_transaction_id = transaction_id
        order.rejection_comment = str(confirmation.get("message") or "PayPhone canceló o rechazó la transacción.")[:500]
        order.reviewed_at = datetime.now(timezone.utc)
        db.session.commit()
        return "rejected"
    current_app.logger.error("Estado PayPhone desconocido para %s", order.reference)
    return "error"


@payment_api.post("/transfer")
@limiter.limit("10 per hour")
@role_required("student")
def transfer_checkout():
    max_mb = current_app.config.get("MAX_DOCUMENT_UPLOAD_MB", 25)
    if request.content_length and request.content_length > max_mb * 1024 * 1024:
        return jsonify({"message": f"El comprobante supera el límite de {max_mb} MB."}), 413
    request.max_content_length = max_mb * 1024 * 1024
    student = current_user()
    course, failure = ensure_available(request.form.get("courseSlug"), student)
    if failure:
        return failure
    proof = request.files.get("proof")
    if not proof or not proof.filename:
        return jsonify({"message": "Carga el comprobante de transferencia."}), 400
    extension = proof.filename.rsplit(".", 1)[-1].lower() if "." in proof.filename else ""
    if extension not in PROOF_EXTENSIONS:
        return jsonify({"message": "El comprobante debe ser PDF, JPG, PNG o WebP."}), 400
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    filename = f"proof-{uuid.uuid4().hex}-{secure_filename(proof.filename)}"
    proof.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))
    order = PaymentOrderModel(reference=f"TRF-{uuid.uuid4().hex[:10].upper()}", course=course, student=student, payment_method="TRANSFER", provider="BANK_TRANSFER", currency="USD", amount=final_price(course), status="PENDING", proof_url=f"/api/v1/uploads/{filename}")
    db.session.add(order)
    db.session.commit()
    send_html_later(current_app.config["MAIL_RECIPIENT"], f"Transferencia por validar · {order.reference}", branded_html("Nuevo comprobante por validar", "Hola equipo administrativo,", f"<strong>{clean(student.first_name)} {clean(student.last_name)}</strong> registró una transferencia de <strong>${order.amount}</strong> para <strong>{clean(course.name)}</strong>.<br>Referencia: {order.reference}", "Validar comprobante", f'{current_app.config["FRONTEND_URL"]}/admin/enrollments'))
    send_html_later(student.email, "Reserva registrada — Alianza Contigo", branded_html("Recibimos tu comprobante", f"Hola {clean(student.first_name)},", f"Registramos tu reserva para <strong>{clean(course.name)}</strong>. Administración validará el pago en un plazo máximo de 24 horas. Te notificaremos cuando puedas empezar a estudiar.<br>Referencia: {order.reference}"))
    return jsonify({"message": "Comprobante recibido. Validaremos tu pago en un plazo máximo de 24 horas.", "reference": order.reference}), 201


@payment_api.get("/orders")
@role_required("admin")
def list_orders():
    status = request.args.get("status")
    query = PaymentOrderModel.query
    if status in {"PENDING", "APPROVED", "REJECTED"}:
        query = query.filter_by(status=status)
    if status == "PENDING":
        query = query.filter_by(payment_method="TRANSFER")
    return jsonify({"orders": [serialize_order(order) for order in query.order_by(PaymentOrderModel.created_at.desc()).all()]})


@payment_api.get("/admin/summary")
@role_required("admin")
def payment_summary():
    def total_for(status):
        value = (
            db.session.query(func.coalesce(func.sum(PaymentOrderModel.amount), 0))
            .filter(PaymentOrderModel.status == status)
            .scalar()
        )
        return float(value)

    counts = {
        status: PaymentOrderModel.query.filter_by(status=status).count()
        for status in ("PENDING", "APPROVED", "REJECTED")
    }
    methods = (
        db.session.query(
            PaymentOrderModel.payment_method,
            func.count(PaymentOrderModel.id),
            func.coalesce(func.sum(PaymentOrderModel.amount), 0),
        )
        .filter(PaymentOrderModel.status == "APPROVED")
        .group_by(PaymentOrderModel.payment_method)
        .all()
    )
    payphone_configured = bool(
        current_app.config.get("PAYPHONE_STORE_ID") and current_app.config.get("PAYPHONE_TOKEN")
    )
    return jsonify(
        {
            "receivedTotal": total_for("APPROVED"),
            "pendingTotal": float(db.session.query(func.coalesce(func.sum(PaymentOrderModel.amount), 0)).filter(PaymentOrderModel.status == "PENDING", PaymentOrderModel.payment_method == "TRANSFER").scalar()),
            "approvedCount": counts["APPROVED"],
            "pendingCount": PaymentOrderModel.query.filter_by(status="PENDING", payment_method="TRANSFER").count(),
            "rejectedCount": counts["REJECTED"],
            "byMethod": [
                {"method": method, "count": count, "total": float(total)}
                for method, count, total in methods
            ],
            "payphone": {
                "configured": payphone_configured,
                "status": "READY" if payphone_configured else "PENDING_CONFIGURATION",
            },
        }
    )


@payment_api.patch("/orders/<order_id>")
@role_required("admin")
def review_order(order_id):
    try:
        order = db.session.get(PaymentOrderModel, uuid.UUID(order_id), with_for_update=True)
    except ValueError:
        order = None
    if not order or order.status != "PENDING" or order.payment_method != "TRANSFER":
        return jsonify({"message": "Este pedido ya fue procesado o no existe."}), 400
    data = request.get_json(silent=True) or {}
    decision = data.get("decision")
    if decision == "approve":
        order.status = "APPROVED"
        order.paid_at = datetime.now(timezone.utc)
        enroll(order.course, order.student)
        subject = "Pago aprobado — Ya puedes comenzar"
        html = branded_html("¡Tu pago fue aprobado!", f"Hola {clean(order.student.first_name)},", f"Tu transferencia para <strong>{clean(order.course.name)}</strong> fue validada. El curso ya está disponible en tu portal.", "Comenzar curso", f'{current_app.config["FRONTEND_URL"]}/app/classroom/{order.course.slug}')
    elif decision == "reject":
        comment = (data.get("comment") or "").strip()
        if not comment:
            return jsonify({"message": "Escribe el motivo del rechazo."}), 400
        order.status = "REJECTED"
        order.rejection_comment = comment
        subject = "Comprobante rechazado — Alianza Contigo"
        html = branded_html("No pudimos validar tu comprobante", f"Hola {clean(order.student.first_name)},", f"El comprobante para <strong>{clean(order.course.name)}</strong> fue rechazado.<br><br><strong>Motivo:</strong> {clean(comment)}<br><br>Puedes realizar una nueva transferencia y cargar un comprobante legible.")
    else:
        return jsonify({"message": "Decisión no válida."}), 400
    order.reviewed_at = datetime.now(timezone.utc)
    db.session.commit()
    send_html_later(order.student.email, subject, html)
    return jsonify(serialize_order(order))
