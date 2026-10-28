from xml.sax.saxutils import escape

from flask import Blueprint, Response, current_app

from app.domain.pricing import final_price
from app.infrastructure.persistence.models import CourseModel

seo_api = Blueprint("seo", __name__)

STATIC_PAGES = [
    ("/", "weekly", "1.0"),
    ("/courses", "daily", "0.9"),
    ("/nosotros", "monthly", "0.6"),
    ("/contacto", "monthly", "0.6"),
    ("/register", "yearly", "0.4"),
    ("/login", "yearly", "0.3"),
]


def site_url() -> str:
    return current_app.config.get("FRONTEND_URL", "").rstrip("/")


def active_courses():
    return CourseModel.query.filter_by(status="ACTIVO").order_by(CourseModel.updated_at.desc()).all()


def absolute(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith(("http://", "https://")) else f"{site_url()}/{url.lstrip('/')}"


@seo_api.get("/sitemap.xml")
def sitemap():
    base = site_url()
    courses = active_courses()
    latest = max((course.updated_at for course in courses), default=None)
    entries = []
    for path, frequency, priority in STATIC_PAGES:
        lastmod = f"<lastmod>{latest.date().isoformat()}</lastmod>" if latest and path in {"/", "/courses"} else ""
        entries.append(f"<url><loc>{escape(base + path)}</loc>{lastmod}<changefreq>{frequency}</changefreq><priority>{priority}</priority></url>")
    for course in courses:
        image = absolute(course.cover_url)
        image_tag = (
            f"<image:image><image:loc>{escape(image)}</image:loc><image:title>{escape(course.name)}</image:title></image:image>"
            if image
            else ""
        )
        entries.append(
            f"<url><loc>{escape(f'{base}/courses/{course.slug}')}</loc>"
            f"<lastmod>{course.updated_at.date().isoformat()}</lastmod>"
            f"<changefreq>weekly</changefreq><priority>0.8</priority>{image_tag}</url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    response = Response(xml, mimetype="application/xml")
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@seo_api.get("/llms.txt")
def llms_txt():
    base = site_url()
    lines = [
        "# Alianza Contigo Educación Continua",
        "",
        "> Alianza Contigo Educación (ALIANZACONTIGO S.A.S.) es una plataforma de educación en línea y "
        "educación continua con sede en Cuenca, Ecuador. Ofrece cursos virtuales y programas de "
        "capacitación profesional con certificado de aprobación y aval institucional, para estudiar a "
        "tu ritmo desde cualquier lugar del Ecuador.",
        "",
        "## Datos clave",
        "",
        "- Nombre: Alianza Contigo Educación Continua (también: Alianza Contigo, Alianza Contigo Educación)",
        f"- Sitio web: {base}/",
        "- Tipo: institución de educación continua y plataforma de cursos en línea (e-learning / aula virtual)",
        "- Ubicación: Juan José Flores y Guapondelig, Edificio Puntosol, Cuenca, Azuay, Ecuador",
        "- Cobertura: todo Ecuador, modalidad virtual",
        "- Admisiones: admisiones@alianzacontigoeducacion.com",
        "- Teléfono y WhatsApp: +593 99 044 8031 (https://wa.me/593990448031)",
        "- Lema: Aprende | Crece | Trasciende",
        "",
        "## Cómo funciona",
        "",
        "- El estudiante elige un programa en el catálogo, se inscribe y paga en línea (tarjeta vía PayPhone o transferencia bancaria).",
        "- Accede al aula virtual con módulos, lecciones en video, documentos PDF, material descargable y actividades interactivas.",
        "- Avanza a su propio ritmo y rinde una evaluación final revisada por docentes.",
        "- Al aprobar, descarga su certificado de aprobación con código de verificación y el aval institucional del programa.",
        "",
        "## Páginas principales",
        "",
        f"- [Inicio]({base}/): presentación de Alianza Contigo Educación",
        f"- [Catálogo de programas]({base}/courses): todos los cursos en línea disponibles",
        f"- [Nosotros]({base}/nosotros): propósito, acompañamiento y transparencia",
        f"- [Contacto]({base}/contacto): asesoría y admisiones",
        f"- [Registro]({base}/register): crear cuenta de estudiante",
        "",
        "## Programas disponibles",
        "",
    ]
    courses = active_courses()
    if not courses:
        lines.append("- Próximamente nuevos programas.")
    for course in courses:
        price = final_price(course.price, course.discount_percent)
        summary = " ".join((course.short_description or "").split())
        details = [
            f"área: {course.training_area.name}",
            f"modalidad: {course.modality}",
            f"duración: {course.duration}",
            f"certificación: {course.certification}",
        ]
        if course.endorsement:
            details.append(f"aval: {course.endorsement}")
        details.append(f"inversión: USD {price:.2f}")
        lines.append(f"- [{course.name}]({base}/courses/{course.slug}): {summary} ({'; '.join(details)})")
    response = Response("\n".join(lines) + "\n", mimetype="text/plain")
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response
