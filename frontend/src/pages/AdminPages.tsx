import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import {
  Activity,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  Edit3,
  FileBadge,
  GripVertical,
  MoreHorizontal,
  Plus,
  Save,
  Search,
  Settings,
  CircleDollarSign,
  GraduationCap,
  Loader2,
  UserCheck,
  Users,
} from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AppShell } from "@/components/layouts/AppShell";
import { adminNav } from "@/components/layouts/nav";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatsCard } from "@/components/shared/StatsCard";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { courses, getCourse } from "@/mocks/courses";
import { enrollmentsAdmin, examSubmissions, students, teachers } from "@/mocks/student";
import { api, ApiError } from "@/lib/api";
import type { Course, ExamSubmission, Student } from "@/types";

const Shell = ({
  children,
  role = "Administrador",
  user = "María Salgado",
}: {
  children: React.ReactNode;
  role?: string;
  user?: string;
}) => (
  <AppShell items={adminNav} role={role} user={user}>
    {children}
  </AppShell>
);
const status = (s: string) => (
  <Badge
    variant="secondary"
    className={
      s.includes("Activo") || s.includes("Aprobado") || s === "Activa"
        ? "bg-green-50 text-green-700"
        : s.includes("Pendiente")
          ? "bg-amber-50 text-amber-800"
          : ""
    }
  >
    {s}
  </Badge>
);

interface DashboardData {
  stats: {
    students: number;
    activeStudents: number;
    activeCourses: number;
    enrollments: number;
    revenue: number;
    completedCourses: number;
    completionRate: number;
    pendingPayments: number;
    pendingEvaluations: number;
  };
  enrollmentsByMonth: { month: string; enrollments: number }[];
  studentsByCourse: { course: string; students: number }[];
  recentActivity: {
    id: string;
    type: "enrollment" | "payment" | "student";
    text: string;
    createdAt: string;
  }[];
}

function timeAgo(value: string) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "hace unos segundos";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "ayer" : `hace ${days} días`;
}

export function AdminDashboard() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<DashboardData>("/admin/dashboard")
      .then(setDashboard)
      .catch((reason) =>
        toast.error(
          reason instanceof ApiError ? reason.message : "No pudimos cargar el dashboard.",
        ),
      )
      .finally(() => setLoading(false));
  }, []);

  return (
    <Shell>
      <PageHeader
        title="Panel administrativo"
        description="Resumen operativo de Alianza Contigo."
      />
      {loading ? (
        <div className="surface-card grid min-h-80 place-items-center">
          <Loader2 className="h-8 w-8 animate-spin text-gold" />
        </div>
      ) : dashboard ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatsCard
              label="Estudiantes registrados"
              value={dashboard.stats.students.toLocaleString("es-EC")}
              trend={`${dashboard.stats.activeStudents} cuentas activas`}
              icon={Users}
            />
            <StatsCard
              label="Programas activos"
              value={dashboard.stats.activeCourses.toLocaleString("es-EC")}
              trend="Disponibles en el catálogo"
              icon={BookOpen}
            />
            <StatsCard
              label="Matrículas aprobadas"
              value={dashboard.stats.enrollments.toLocaleString("es-EC")}
              trend={`${dashboard.stats.completedCourses} Programas completados`}
              icon={GraduationCap}
            />
            <StatsCard
              label="Ingresos recibidos"
              value={dashboard.stats.revenue.toLocaleString("es-EC", {
                style: "currency",
                currency: "USD",
              })}
              trend="Pagos aprobados"
              icon={CircleDollarSign}
            />
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-3">
            <div className="surface-card p-5">
              <p className="text-sm text-muted-foreground">Tasa de culminación</p>
              <p className="mt-2 text-2xl font-semibold text-navy">
                {dashboard.stats.completionRate}%
              </p>
            </div>
            <div className="surface-card p-5">
              <p className="text-sm text-muted-foreground">Pagos por validar</p>
              <p className="mt-2 text-2xl font-semibold text-amber-700">
                {dashboard.stats.pendingPayments}
              </p>
            </div>
            <div className="surface-card p-5">
              <p className="text-sm text-muted-foreground">Evaluaciones por revisar</p>
              <p className="mt-2 text-2xl font-semibold text-amber-700">
                {dashboard.stats.pendingEvaluations}
              </p>
            </div>
          </div>

          <div className="mt-8 grid gap-6 xl:grid-cols-2">
            <Chart
              title="Matrículas de los últimos 6 meses"
              data={dashboard.enrollmentsByMonth}
              dataKey="enrollments"
              nameKey="month"
            />
            <Chart
              title="Estudiantes por curso"
              data={dashboard.studentsByCourse}
              dataKey="students"
              nameKey="course"
            />
          </div>
          <section className="surface-card mt-6 p-6">
            <h2 className="font-display text-lg font-semibold text-navy">Actividad reciente</h2>
            {dashboard.recentActivity.length ? (
              <div className="mt-4 divide-y divide-border">
                {dashboard.recentActivity.map((item) => (
                  <div key={item.id} className="flex gap-3 py-3">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent text-gold">
                      <Activity className="h-4 w-4" />
                    </span>
                    <div>
                      <p className="text-sm text-navy">{item.text}</p>
                      <p className="text-xs text-muted-foreground">{timeAgo(item.createdAt)}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-4 text-sm text-muted-foreground">Aún no hay actividad registrada.</p>
            )}
          </section>
        </>
      ) : (
        <div className="surface-card p-8 text-center text-sm text-muted-foreground">
          No se pudo cargar la información administrativa.
        </div>
      )}
    </Shell>
  );
}
function Chart({
  title,
  data,
  dataKey,
  nameKey,
}: {
  title: string;
  data: object[];
  dataKey: string;
  nameKey: string;
}) {
  return (
    <section className="surface-card p-5">
      <h2 className="font-display font-semibold text-navy">{title}</h2>
      <div className="mt-5 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey={nameKey} fontSize={11} />
            <YAxis fontSize={11} />
            <Tooltip />
            <Bar dataKey={dataKey} fill="#C89432" radius={[5, 5, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

const courseCols: Column<Course>[] = [
  {
    key: "course",
    header: "Curso",
    render: (c) => (
      <div>
        <p className="font-medium text-navy">{c.name}</p>
        <p className="text-xs text-muted-foreground">{c.duration}</p>
      </div>
    ),
  },
  { key: "students", header: "Estudiantes", render: (c) => c.studentsCount },
  { key: "state", header: "Estado", render: (c) => status(c.status) },
  {
    key: "aval",
    header: "Aval",
    render: (c) => <span className="text-xs">{c.endorsements.join(", ")}</span>,
  },
  {
    key: "actions",
    header: "Acciones",
    render: (c) => (
      <div className="flex gap-2">
        <Button asChild size="sm" variant="outline">
          <Link to={`/admin/courses/${c.slug}/edit`}>
            <Edit3 />
            Editar
          </Link>
        </Button>
        <Button asChild size="sm">
          <Link to={`/admin/courses/${c.slug}/content`}>Contenido</Link>
        </Button>
      </div>
    ),
  },
];
export function AdminCourses() {
  return (
    <Shell>
      <PageHeader
        title="Gestión de Programas"
        description="Administra el catálogo, contenido y evaluaciones."
        actions={
          <Button asChild variant="gold">
            <Link to="/admin/courses/new">
              <Plus />
              Crear curso
            </Link>
          </Button>
        }
      />
      <DataTable rows={courses} columns={courseCols} />
    </Shell>
  );
}

export function CourseForm() {
  const { slug } = useParams();
  const course = slug ? getCourse(slug) : undefined;
  return (
    <Shell>
      <PageHeader
        title={course ? `Editar ${course.name}` : "Crear curso"}
        description="Completa la información por etapas. Los cambios son demostrativos."
      />
      <Tabs defaultValue="general">
        <TabsList className="mb-5">
          <TabsTrigger value="general">1. Información general</TabsTrigger>
          <TabsTrigger value="cert">2. Certificación</TabsTrigger>
          <TabsTrigger value="content">3. Contenido</TabsTrigger>
        </TabsList>
        <TabsContent value="general">
          <FormPanel>
            <Field label="Nombre">
              <Input defaultValue={course?.name} />
            </Field>
            <Field label="Descripción corta">
              <Input defaultValue={course?.shortDescription} />
            </Field>
            <Field label="Descripción completa" wide>
              <Textarea defaultValue={course?.fullDescription} />
            </Field>
            <Field label="Imagen">
              <Input type="file" />
            </Field>
            <Field label="Precio">
              <Input defaultValue={course?.price ?? "Consultar valor"} />
            </Field>
            <Field label="Estado">
              <Select defaultValue={course?.status ?? "Borrador"}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Activo">Activo</SelectItem>
                  <SelectItem value="Borrador">Borrador</SelectItem>
                  <SelectItem value="Inactivo">Inactivo</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          </FormPanel>
        </TabsContent>
        <TabsContent value="cert">
          <FormPanel>
            <Field label="Organismo que avala">
              <Input defaultValue={course?.endorsements[0]} />
            </Field>
            <Field label="Nombre de certificación">
              <Input defaultValue={course?.certification} />
            </Field>
            <Field label="Logo del organismo">
              <Input type="file" />
            </Field>
          </FormPanel>
        </TabsContent>
        <TabsContent value="content">
          <ModuleBuilder />
        </TabsContent>
      </Tabs>
      <Button
        variant="gold"
        className="mt-6"
        onClick={() => toast.success("Curso guardado en el prototipo")}
      >
        <Save />
        Guardar curso
      </Button>
    </Shell>
  );
}
const FormPanel = ({ children }: { children: React.ReactNode }) => (
  <div className="surface-card grid gap-5 p-6 md:grid-cols-2">{children}</div>
);
const Field = ({
  label,
  children,
  wide = false,
}: {
  label: string;
  children: React.ReactNode;
  wide?: boolean;
}) => (
  <div className={wide ? "space-y-2 md:col-span-2" : "space-y-2"}>
    <Label>{label}</Label>
    {children}
  </div>
);
function ModuleBuilder() {
  const [modules, setModules] = useState([
    "Introducción",
    "Fundamentos",
    "Aplicación práctica",
    "Evaluación y certificación",
  ]);
  return (
    <div className="space-y-3">
      {modules.map((m, i) => (
        <section key={`${m}-${i}`} className="surface-card flex items-center gap-3 p-4">
          <GripVertical className="text-muted-foreground" />
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-xs font-semibold text-gold">
            {i + 1}
          </span>
          <Input defaultValue={m} />
          <Button variant="outline" size="sm">
            <Plus />
            Agregar lección
          </Button>
        </section>
      ))}
      <Button variant="outline" onClick={() => setModules([...modules, "Nuevo módulo"])}>
        <Plus />
        Agregar módulo
      </Button>
    </div>
  );
}

export function CourseContent() {
  const { slug = "" } = useParams();
  const course = getCourse(slug);
  if (!course) return <Navigate to="/admin/courses" />;
  return (
    <Shell>
      <PageHeader
        title={`Contenido · ${course.name}`}
        description="Reordena módulos y agrega lecciones de video, PDF, documento, texto o recurso."
        actions={
          <Button asChild>
            <Link to={`/admin/courses/${slug}/evaluation`}>
              <ClipboardCheck />
              Evaluación final
            </Link>
          </Button>
        }
      />
      <ModuleBuilder />
    </Shell>
  );
}
export function EvaluationBuilder() {
  return (
    <Shell>
      <PageHeader
        title="Constructor de evaluación"
        description="Configura reglas, preguntas, respuestas y puntajes."
        actions={
          <Button variant="gold">
            <Plus />
            Agregar pregunta
          </Button>
        }
      />
      <FormPanel>
        <Field label="Nombre">
          <Input defaultValue="Evaluación final" />
        </Field>
        <Field label="Tiempo límite">
          <Input defaultValue="45 minutos" />
        </Field>
        <Field label="Número de intentos">
          <Input type="number" defaultValue="1" />
        </Field>
        <Field label="Puntaje de aprobación">
          <Input type="number" defaultValue="70" />
        </Field>
      </FormPanel>
      <div className="mt-6 space-y-3">
        {[
          "¿Cuál es una función del proceso administrativo?",
          "Selecciona los elementos de una planificación estratégica.",
          "La gestión empresarial articula personas y reProgramas.",
        ].map((q, i) => (
          <section key={q} className="surface-card flex items-center gap-4 p-4">
            <GripVertical className="text-muted-foreground" />
            <span className="font-semibold text-gold">{i + 1}</span>
            <p className="min-w-0 flex-1 text-sm text-navy">{q}</p>
            <Button variant="ghost" size="icon">
              <MoreHorizontal />
            </Button>
          </section>
        ))}
      </div>
    </Shell>
  );
}

const studentCols: Column<Student>[] = [
  {
    key: "name",
    header: "Nombre",
    render: (s) => (
      <div>
        <p className="font-medium text-navy">{s.name}</p>
        <p className="text-xs text-muted-foreground">{s.email}</p>
      </div>
    ),
  },
  { key: "id", header: "Cédula", render: (s) => s.idCard },
  { key: "courses", header: "Programas", render: (s) => s.coursesEnrolled },
  { key: "status", header: "Estado", render: (s) => status(s.status) },
  { key: "date", header: "Registro", render: (s) => s.registeredAt },
  {
    key: "action",
    header: "Acción",
    render: (s) => (
      <Button asChild variant="outline" size="sm">
        <Link to={`/admin/students/${s.id}`}>Ver perfil</Link>
      </Button>
    ),
  },
];
export function StudentsPage() {
  const [q, setQ] = useState("");
  const rows = students.filter(
    (s) => s.name.toLowerCase().includes(q.toLowerCase()) || s.idCard.includes(q),
  );
  return (
    <Shell>
      <PageHeader
        title="Gestión de estudiantes"
        description="Consulta datos, progreso, evaluaciones y certificados."
      />
      <div className="relative mb-5 max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar estudiante o cédula"
          className="pl-9"
        />
      </div>
      <DataTable rows={rows} columns={studentCols} />
    </Shell>
  );
}
export function StudentDetail() {
  const { id } = useParams();
  const s = students.find((x) => x.id === id);
  if (!s) return <Navigate to="/admin/students" />;
  return (
    <Shell>
      <PageHeader title={s.name} description={`${s.idCard} · ${s.email}`} />
      <div className="grid gap-5 md:grid-cols-3">
        <StatsCard label="Programas adquiridos" value={String(s.coursesEnrolled)} icon={BookOpen} />
        <StatsCard label="Progreso promedio" value="68%" icon={Activity} />
        <StatsCard label="Certificados" value="1" icon={FileBadge} />
      </div>
      <section className="surface-card mt-6 p-6">
        <h2 className="font-display font-semibold text-navy">Historial académico</h2>
        <p className="mt-3 text-sm text-muted-foreground">
          Programas, evaluaciones y certificados del estudiante se mostrarán aquí al conectar la
          API.
        </p>
      </section>
    </Shell>
  );
}

const evalCols: Column<ExamSubmission>[] = [
  { key: "student", header: "Estudiante", render: (e) => e.studentName },
  { key: "course", header: "Curso", render: (e) => e.courseName },
  { key: "date", header: "Fecha", render: (e) => e.date },
  { key: "status", header: "Estado", render: (e) => status(e.status) },
  { key: "score", header: "Calificación", render: (e) => e.score ?? "—" },
  {
    key: "action",
    header: "Acción",
    render: (e) => (
      <Button asChild size="sm">
        <Link to={`/admin/evaluations/${e.id}`}>Revisar evaluación</Link>
      </Button>
    ),
  },
];
export function EvaluationsPage() {
  return (
    <Shell>
      <PageHeader
        title="Bandeja de evaluaciones"
        description="Revisa entregas y publica calificaciones."
      />
      <DataTable rows={examSubmissions} columns={evalCols} />
    </Shell>
  );
}
export function EvaluationReview() {
  const { id } = useParams();
  const exam = examSubmissions.find((e) => e.id === id) ?? examSubmissions[0]!;
  return (
    <Shell role="Docente" user="Ing. Ricardo Ponce">
      <PageHeader
        title="Revisión de evaluación"
        description={`${exam.studentName} · ${exam.courseName} · ${exam.date}`}
      />
      <div className="space-y-4">
        {[
          "¿Cuál es una función del proceso administrativo?",
          "¿Qué elementos pertenecen a la planificación estratégica?",
          "La gestión empresarial articula procesos, personas y reProgramas.",
        ].map((q, i) => (
          <section key={q} className="surface-card p-5">
            <div className="flex justify-between gap-4">
              <h2 className="font-medium text-navy">
                {i + 1}. {q}
              </h2>
              <Input type="number" defaultValue="5" className="w-20" aria-label="Puntaje" />
            </div>
            <p className="mt-3 rounded-lg bg-muted p-3 text-sm text-muted-foreground">
              Respuesta del estudiante:{" "}
              {i === 1 ? "Misión, objetivos y análisis FODA" : "Planificación"}
            </p>
          </section>
        ))}
      </div>
      <section className="surface-card mt-5 p-5">
        <Label>Comentarios del docente</Label>
        <Textarea
          className="mt-2"
          placeholder="Escribe una retroalimentación clara para el estudiante..."
        />
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => toast.success("Calificación guardada")}>
            <Save />
            Guardar calificación
          </Button>
          <Button
            variant="gold"
            onClick={() => toast.success("Curso aprobado y certificado habilitado")}
          >
            <CheckCircle2 />
            Aprobar curso
          </Button>
        </div>
      </section>
    </Shell>
  );
}

export function EnrollmentsPage() {
  return (
    <Shell>
      <PageHeader
        title="Gestión de inscripciones"
        description="Asigna manualmente un curso a un estudiante."
      />
      <section className="surface-card mb-6 grid gap-4 p-6 md:grid-cols-2 xl:grid-cols-4">
        <Field label="Buscar estudiante">
          <Input placeholder="Nombre o cédula" />
        </Field>
        <Field label="Seleccionar curso">
          <Select>
            <SelectTrigger>
              <SelectValue placeholder="Elige un curso" />
            </SelectTrigger>
            <SelectContent>
              {courses.map((c) => (
                <SelectItem key={c.id} value={c.slug}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Fecha">
          <Input type="date" />
        </Field>
        <Field label="Estado">
          <Select defaultValue="Activa">
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Activa">Activa</SelectItem>
              <SelectItem value="Pendiente">Pendiente</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Button
          variant="gold"
          className="md:col-span-2 xl:col-span-4"
          onClick={() => toast.success("Estudiante matriculado en el prototipo")}
        >
          <UserCheck />
          Matricular estudiante
        </Button>
      </section>
      <DataTable
        rows={enrollmentsAdmin}
        columns={[
          { key: "student", header: "Estudiante", render: (r) => r.student },
          { key: "course", header: "Curso", render: (r) => r.course },
          { key: "date", header: "Fecha", render: (r) => r.date },
          { key: "status", header: "Estado", render: (r) => status(r.status) },
        ]}
      />
    </Shell>
  );
}

export function GenericAdminPage({ type }: { type: "teachers" | "certificates" | "settings" }) {
  const info =
    type === "teachers"
      ? [
          "Docentes",
          "Administra perfiles docentes y Programas asignados.",
          teachers.map((t) => `${t.name} · ${t.area}`),
        ]
      : type === "certificates"
        ? [
            "Certificados",
            "Emisión, verificación y descarga de certificados.",
            [
              "312 certificados emitidos",
              "8 pendientes de verificación",
              "Código único por certificado",
            ],
          ]
        : [
            "Configuración",
            "Ajustes institucionales y parámetros del prototipo.",
            ["Identidad institucional", "Reglas de evaluación", "Notificaciones"],
          ];
  return (
    <Shell>
      <PageHeader title={String(info[0])} description={String(info[1])} />
      <div className="space-y-3">
        {(info[2] as string[]).map((x) => (
          <section key={x} className="surface-card flex items-center justify-between p-5">
            <span className="text-sm font-medium text-navy">{x}</span>
            <Button variant="outline" size="sm">
              Gestionar
            </Button>
          </section>
        ))}
      </div>
    </Shell>
  );
}
