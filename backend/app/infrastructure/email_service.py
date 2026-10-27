import os
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from html import escape

from flask import current_app

# Few workers on purpose: Gmail throttles parallel SMTP logins, and requests must not wait on SMTP.
_mail_executor = ThreadPoolExecutor(max_workers=int(os.getenv("EMAIL_WORKERS", "3")), thread_name_prefix="mail")


def branded_html(title, greeting, body, action_label=None, action_url=None):
    action = ""
    if action_label and action_url:
        action = f'''<tr><td style="padding:4px 36px 36px">
          <a href="{escape(action_url, quote=True)}" style="display:inline-block;background:#C89432;border-radius:9px;color:#071C3A;font-size:15px;font-weight:700;line-height:20px;padding:15px 24px;text-decoration:none">{escape(action_label)}</a>
        </td></tr>'''
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#F3F5F8;color:#071C3A;font-family:Arial,Helvetica,sans-serif">
      <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#F3F5F8"><tr><td align="center" style="padding:40px 16px">
        <table role="presentation" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;border-collapse:separate;background:#ffffff;border:1px solid #E6EAF0;border-radius:16px;overflow:hidden">
          <tr><td style="height:5px;background:#C89432;font-size:1px;line-height:1px">&nbsp;</td></tr>
          <tr><td style="background:#071C3A;padding:27px 36px 25px">
            <div style="color:#ffffff;font-size:21px;font-weight:800;letter-spacing:0.4px">ALIANZA<span style="color:#D9AE55">CONTIGO</span></div>
            <div style="margin-top:6px;color:#B8C7D9;font-size:10px;font-weight:700;letter-spacing:3px">EDUCACIÓN CONTINUA</div>
          </td></tr>
          <tr><td style="padding:34px 36px 12px"><div style="color:#B0822F;font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase">ALIANZA CONTIGO</div>
            <h1 style="margin:13px 0 0;color:#071C3A;font-size:26px;font-weight:700;line-height:1.25">{escape(title)}</h1></td></tr>
          <tr><td style="padding:0 36px 8px"><p style="margin:0;color:#071C3A;font-size:16px;font-weight:600;line-height:1.7">{greeting}</p></td></tr>
          <tr><td style="padding:6px 36px 28px"><div style="color:#405168;font-size:15px;line-height:1.75">{body}</div></td></tr>
          {action}
          <tr><td style="background:#F7F8FA;border-top:1px solid #E6EAF0;padding:24px 36px">
            <div style="color:#071C3A;font-size:12px;font-weight:700">Aprende · Crece · Trasciende</div>
            <div style="margin-top:9px;color:#667085;font-size:12px;line-height:1.6">¿Necesitas ayuda? <a href="mailto:nivusoftware@gmail.com" style="color:#0E315C;text-decoration:none">Escríbenos</a> o contáctanos al <a href="https://wa.me/593990448031" style="color:#0E315C;text-decoration:none">+593 99 044 8031</a>.</div>
            <div style="margin-top:12px;color:#98A2B3;font-size:11px">Alianza Contigo · Educación Continua</div>
          </td></tr>
        </table>
      </td></tr></table>
    </body></html>'''


def send_html(to, subject, html):
    if not current_app.config["EMAIL_ADDRESS"] or not current_app.config["EMAIL_PASSWORD"] or not to:
        current_app.logger.warning("Correo omitido: SMTP o destinatario no configurado")
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = current_app.config["MAIL_SENDER"]
    message["To"] = to
    message.set_content("Este correo requiere un cliente compatible con HTML.")
    message.add_alternative(html, subtype="html")
    with smtplib.SMTP(current_app.config["SMTP_SERVER"], current_app.config["SMTP_PORT"], timeout=15) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(current_app.config["EMAIL_ADDRESS"], current_app.config["EMAIL_PASSWORD"])
        smtp.send_message(message)
    return True


def _deliver(app, to, subject, html):
    with app.app_context():
        try:
            send_html(to, subject, html)
        except Exception:
            app.logger.exception("No se pudo enviar el correo %s", subject)


def send_html_later(to, subject, html):
    """Queue a best-effort email so the HTTP response does not wait for SMTP."""
    app = current_app._get_current_object()
    if app.testing or not app.config.get("EMAIL_ASYNC", True):
        _deliver(app, to, subject, html)
        return
    _mail_executor.submit(_deliver, app, to, subject, html)
