from decimal import Decimal

from app.extensions import db
from app.infrastructure.persistence.models import (
    CourseModel,
    CourseModuleModel,
    EnrollmentModel,
    ExamQuestionModel,
    FinalExamModel,
    LessonModel,
    TrainingAreaModel,
)


DEMO_COURSES = [
    {
        "slug": "liderazgo-y-gestion-de-equipos",
        "name": "Liderazgo y Gestión de Equipos",
        "short_description": "Desarrolla habilidades para liderar, comunicar y movilizar equipos hacia resultados sostenibles.",
        "full_description": "Un programa práctico para fortalecer el liderazgo personal, la comunicación efectiva y la gestión de equipos en entornos profesionales.",
        "duration": "24 horas",
        "price": "89.00",
        "modules": [
            ("Fundamentos del liderazgo", "Comprende tu estilo de liderazgo y su impacto.", [
                ("El rol del líder actual", "El liderazgo combina dirección, confianza y responsabilidad. Identifica las necesidades del equipo antes de elegir cómo intervenir."),
                ("Estilos de liderazgo", "Reconoce cuándo aplicar un estilo directivo, participativo o delegativo según la madurez y el contexto del equipo."),
            ]),
            ("Equipos de alto desempeño", "Aplica comunicación, feedback y seguimiento.", [
                ("Comunicación y escucha activa", "Practica preguntas abiertas, escucha sin interrupciones y confirma acuerdos con acciones y fechas claras."),
                ("Feedback que moviliza", "Describe hechos observables, explica el impacto y acuerda el siguiente comportamiento esperado."),
            ]),
        ],
        "questions": [
            ("¿Qué caracteriza a la escucha activa?", ["Interrumpir para aconsejar", "Confirmar lo comprendido", "Evitar preguntas", "Hablar más que el equipo"], 1),
            ("¿Cuándo es apropiado delegar?", ["Cuando no hay claridad", "Cuando la persona tiene capacidad y autonomía", "Siempre que exista presión", "Solo en tareas urgentes"], 1),
            ("Un feedback efectivo debe centrarse en:", ["La personalidad", "Rumores del equipo", "Hechos observables", "Suposiciones"], 2),
            ("El liderazgo situacional adapta el estilo según:", ["La preferencia del líder", "La madurez y el contexto", "El cargo formal", "La antigüedad"], 1),
            ("Un acuerdo de equipo útil incluye:", ["Acciones y fechas", "Ideas generales", "Solo responsables", "Ningún seguimiento"], 0),
        ],
    },
    {
        "slug": "servicio-al-cliente-y-experiencia",
        "name": "Servicio al Cliente y Experiencia",
        "short_description": "Convierte cada interacción en una experiencia clara, empática y orientada a soluciones.",
        "full_description": "Aprende a comprender necesidades, manejar conversaciones difíciles y diseñar respuestas que generen confianza y fidelidad.",
        "duration": "20 horas",
        "price": "79.00",
        "modules": [
            ("Cultura de servicio", "Conecta necesidades del cliente con respuestas de valor.", [
                ("Momentos de verdad", "Cada contacto influye en la percepción del cliente. Identifica expectativas y elimina fricciones evitables."),
                ("Comunicación empática", "Escucha, valida la situación y comunica alternativas con lenguaje claro y respetuoso."),
            ]),
            ("Resolución y fidelización", "Resuelve reclamos y aprende de ellos.", [
                ("Manejo de reclamos", "Recibe el reclamo sin discutir, aclara los hechos, propone una solución y confirma la satisfacción."),
                ("Seguimiento de la experiencia", "Registra causas, mide recurrencia y convierte los hallazgos en mejoras del proceso."),
            ]),
        ],
        "questions": [
            ("¿Qué es un momento de verdad?", ["Una reunión interna", "Un contacto que influye en la percepción", "Una campaña", "Un reporte mensual"], 1),
            ("El primer paso ante un reclamo es:", ["Defender a la empresa", "Escuchar y aclarar", "Transferir la llamada", "Ofrecer descuentos"], 1),
            ("La comunicación empática implica:", ["Prometer todo", "Validar la situación", "Evitar explicar", "Usar lenguaje técnico"], 1),
            ("El seguimiento permite:", ["Ocultar errores", "Identificar causas recurrentes", "Cerrar canales", "Reducir información"], 1),
            ("Una solución clara debe incluir:", ["Responsable y plazo", "Solo una disculpa", "Condiciones ambiguas", "Ningún registro"], 0),
        ],
    },
    {
        "slug": "emprendimiento-y-modelo-de-negocio",
        "name": "Emprendimiento y Modelo de Negocio",
        "short_description": "Transforma una idea en una propuesta de valor viable, medible y enfocada en clientes reales.",
        "full_description": "Construye las bases de un emprendimiento mediante validación de problemas, propuesta de valor y planificación financiera esencial.",
        "duration": "30 horas",
        "price": "99.00",
        "modules": [
            ("Del problema a la propuesta", "Valida una necesidad antes de construir la solución.", [
                ("Descubrimiento del cliente", "Formula hipótesis, entrevista clientes potenciales y busca evidencia de problemas frecuentes y relevantes."),
                ("Propuesta de valor", "Define para quién creas valor, qué problema resuelves y por qué tu alternativa resulta diferente."),
            ]),
            ("Viabilidad del negocio", "Conecta ingresos, costos y experimentos.", [
                ("Modelo de ingresos y costos", "Distingue costos fijos y variables, define fuentes de ingreso y calcula un punto de equilibrio inicial."),
                ("Experimentos de validación", "Diseña una prueba pequeña con una métrica y un criterio de decisión antes de invertir a gran escala."),
            ]),
        ],
        "questions": [
            ("Antes de construir una solución conviene:", ["Invertir a gran escala", "Validar el problema", "Contratar más personal", "Definir el logotipo"], 1),
            ("Una propuesta de valor define:", ["Solo el precio", "Cliente, problema y diferenciación", "Únicamente el producto", "La estructura legal"], 1),
            ("Un costo variable cambia según:", ["El volumen de operación", "El nombre del negocio", "La visión", "El organigrama"], 0),
            ("Un experimento útil necesita:", ["Una métrica y criterio de decisión", "Mucho presupuesto", "Resultados garantizados", "Duración indefinida"], 0),
            ("El punto de equilibrio ocurre cuando:", ["No existen costos", "Ingresos igualan costos", "Se duplica el equipo", "La publicidad termina"], 1),
        ],
    },
]


def seed_demo_courses():
    training_area = TrainingAreaModel.query.filter_by(name="Formación general").first()
    if training_area is None:
        training_area = TrainingAreaModel(name="Formación general")
        db.session.add(training_area)
        db.session.flush()
    for spec in DEMO_COURSES:
        course = CourseModel.query.filter_by(slug=spec["slug"]).first()
        if course is None:
            course = CourseModel(slug=spec["slug"])
            db.session.add(course)
        elif EnrollmentModel.query.filter_by(course_id=course.id).first():
            # Rebuilding modules would delete the lesson progress of the enrolled students.
            continue
        course.name = spec["name"]
        course.training_area = training_area
        course.short_description = spec["short_description"]
        course.full_description = spec["full_description"]
        course.modality = "Virtual · A tu ritmo"
        course.duration = spec["duration"]
        course.certification = "Certificado digital de aprobación"
        course.endorsement = "Alianza Contigo Educación Continua"
        course.price = Decimal(spec["price"])
        course.discount_percent = 0
        course.status = "ACTIVO"
        course.modules.clear()
        course.final_exam = None
        db.session.flush()

        for module_position, (title, description, lessons) in enumerate(spec["modules"]):
            module = CourseModuleModel(title=title, description=description, position=module_position)
            course.modules.append(module)
            for lesson_position, (lesson_title, content) in enumerate(lessons):
                module.lessons.append(LessonModel(
                    title=lesson_title,
                    lesson_type="text",
                    content=content,
                    duration_minutes=15,
                    is_preview=module_position == 0 and lesson_position == 0,
                    position=lesson_position,
                ))

        exam = FinalExamModel(
            title=f"Evaluación final · {spec['name']}",
            instructions="Selecciona la respuesta correcta. Necesitas 70/100 para aprobar.",
            time_limit_minutes=30,
            attempts_allowed=2,
            passing_score=70,
        )
        course.final_exam = exam
        for position, (prompt, options, correct_index) in enumerate(spec["questions"]):
            exam.questions.append(ExamQuestionModel(
                prompt=prompt,
                question_type="single_choice",
                options=options,
                correct_answers=[correct_index],
                points=20,
                position=position,
            ))

    db.session.commit()
    return len(DEMO_COURSES)
