import type { Course, Module } from "@/types";
import gestorImg from "@/assets/course-gestor.jpg";
import adminImg from "@/assets/course-admin.jpg";
import inmoImg from "@/assets/course-inmobiliario.jpg";
import visitadorImg from "@/assets/course-visitador.jpg";
import artesanoImg from "@/assets/course-artesano.jpg";

const baseModules = (): Module[] => [
  {
    id: "m1",
    title: "Módulo 1",
    subtitle: "Introducción",
    lessons: [
      {
        id: "l1",
        title: "Bienvenida al programa",
        type: "video",
        duration: "08:24",
        state: "completed",
        description: "Presentación general del programa, metodología y expectativas.",
      },
      {
        id: "l2",
        title: "Fundamentos empresariales",
        type: "video",
        duration: "14:05",
        state: "completed",
        description: "Conceptos base sobre organizaciones y su entorno.",
      },
      {
        id: "l3",
        title: "Guía de estudio (PDF)",
        type: "pdf",
        duration: "6 pág.",
        state: "completed",
        description: "Documento descargable con la ruta de aprendizaje.",
      },
    ],
  },
  {
    id: "m2",
    title: "Módulo 2",
    subtitle: "Fundamentos",
    lessons: [
      {
        id: "l4",
        title: "Conceptos administrativos",
        type: "video",
        duration: "18:12",
        state: "completed",
        description: "Planificación, organización, dirección y control.",
      },
      {
        id: "l5",
        title: "Gestión empresarial",
        type: "video",
        duration: "21:40",
        state: "current",
        description:
          "Cómo articular procesos, personas y reProgramas para alcanzar los objetivos estratégicos de la organización.",
      },
      {
        id: "l6",
        title: "Planificación estratégica",
        type: "video",
        duration: "16:55",
        state: "pending",
        description: "Herramientas para definir objetivos y medir resultados.",
      },
    ],
  },
  {
    id: "m3",
    title: "Módulo 3",
    subtitle: "Aplicación práctica",
    lessons: [
      {
        id: "l7",
        title: "Caso práctico integrador",
        type: "document",
        duration: "45 min",
        state: "pending",
        description: "Aplica lo aprendido a un caso empresarial real.",
      },
      {
        id: "l8",
        title: "Plantillas de trabajo",
        type: "resource",
        duration: "3 archivos",
        state: "pending",
        description: "Material descargable de apoyo.",
      },
    ],
  },
  {
    id: "m4",
    title: "Módulo 4",
    subtitle: "Evaluación y certificación",
    lessons: [
      {
        id: "l9",
        title: "Evaluación final",
        type: "exam",
        duration: "45:00",
        state: "locked",
        description: "20 preguntas. Disponible al completar las lecciones requeridas.",
      },
    ],
  },
];

const MOCK_TRAINING_AREA = { id: "formacion-general", name: "Formación general" };

export const courses: Course[] = [
  {
    id: "c1",
    trainingArea: MOCK_TRAINING_AREA,
    slug: "gestor-empresarial",
    name: "Gestor Empresarial",
    shortDescription:
      "Desarrolla competencias para gestionar organizaciones, procesos administrativos y estrategias empresariales.",
    fullDescription:
      "Programa de educación continua orientado a profesionales que buscan liderar equipos y procesos. Combina fundamentos administrativos, herramientas de gestión y casos prácticos aplicables desde el primer módulo.",
    endorsements: ["Aval SENESCYT"],
    image: gestorImg,
    modality: "Virtual · Asincrónico",
    duration: "120 horas",
    modules: baseModules(),
    certification: "Certificado de Gestor Empresarial",
    status: "Activo",
    studentsCount: 164,
    price: "Consultar valor",
  },
  {
    id: "c2",
    trainingArea: MOCK_TRAINING_AREA,
    slug: "administracion-de-empresas",
    name: "Administración de Empresas",
    shortDescription:
      "Fortalece tus conocimientos en planificación, administración, organización y gestión empresarial.",
    fullDescription:
      "Un recorrido completo por las áreas funcionales de la empresa: talento humano, operaciones, finanzas y estrategia, con enfoque práctico y evaluaciones por módulo.",
    endorsements: ["Aval SENESCYT"],
    image: adminImg,
    modality: "Virtual · Tutoría semanal",
    duration: "140 horas",
    modules: baseModules(),
    certification: "Certificado en Administración de Empresas",
    status: "Activo",
    studentsCount: 138,
    price: "Consultar valor",
  },
  {
    id: "c3",
    trainingArea: MOCK_TRAINING_AREA,
    slug: "agente-inmobiliario",
    name: "Agente Inmobiliario",
    shortDescription:
      "Prepárate profesionalmente para desarrollar actividades dentro del sector inmobiliario.",
    fullDescription:
      "Formación integral en comercialización de bienes raíces: marco legal, avalúos, negociación, captación de clientes y ética profesional.",
    endorsements: ["Aval SENESCYT"],
    image: inmoImg,
    modality: "Virtual · Asincrónico",
    duration: "100 horas",
    modules: baseModules(),
    certification: "Certificado de Agente Inmobiliario",
    status: "Activo",
    studentsCount: 121,
    price: "Consultar valor",
  },
  {
    id: "c4",
    trainingArea: MOCK_TRAINING_AREA,
    slug: "visitador-medico",
    name: "Visitador Médico",
    shortDescription:
      "Obtén conocimientos comerciales, farmacológicos y comunicacionales para desarrollarte profesionalmente en el sector.",
    fullDescription:
      "Programa diseñado junto a profesionales del sector farmacéutico: fundamentos de farmacología, técnicas de visita, comunicación efectiva y gestión de territorio.",
    endorsements: ["Aval Ministerio del Trabajo"],
    image: visitadorImg,
    modality: "Virtual · Asincrónico",
    duration: "90 horas",
    modules: baseModules(),
    certification: "Certificado de Visitador Médico",
    status: "Activo",
    studentsCount: 108,
    price: "Consultar valor",
  },
  {
    id: "c5",
    trainingArea: MOCK_TRAINING_AREA,
    slug: "certificacion-artesano",
    name: "Certificación como Artesano",
    shortDescription: "Obtén formación y orientación para alcanzar tu certificación como artesano.",
    fullDescription:
      "Acompañamiento formativo y orientación en el proceso de calificación artesanal, incluyendo requisitos, documentación y buenas prácticas del oficio.",
    endorsements: ["Cámara de Artesanos", "MIPRO"],
    image: artesanoImg,
    modality: "Semipresencial",
    duration: "80 horas",
    modules: baseModules(),
    certification: "Calificación Artesanal",
    status: "Activo",
    studentsCount: 93,
    price: "Consultar valor",
  },
];

export const getCourse = (slug: string) => courses.find((c) => c.slug === slug);
