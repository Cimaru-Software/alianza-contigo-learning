import { Link } from "react-router-dom";
import { BookOpen, CheckCircle2, Clock3, Users } from "lucide-react";
import { AppShell } from "@/components/layouts/AppShell";
import { teacherNav } from "@/components/layouts/nav";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";

export function TeacherDashboard() {
  return (
    <AppShell items={teacherNav} role="Profesor">
      <PageHeader
        title="Panel docente"
        description="Acompaña el aprendizaje y mantén tus revisiones al día."
      />
      <section className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {(
          [
            ["Programas activos", "3", BookOpen],
            ["Estudiantes", "84", Users],
            ["Por revisar", "7", Clock3],
            ["Revisadas este mes", "36", CheckCircle2],
          ] as const
        ).map(([label, value, Icon]) => (
          <article key={String(label)} className="surface-card p-5">
            <Icon className="h-5 w-5 text-gold" />
            <p className="mt-5 text-2xl font-semibold text-navy">{String(value)}</p>
            <p className="mt-1 text-sm text-muted-foreground">{String(label)}</p>
          </article>
        ))}
      </section>
      <section className="mt-6 surface-card p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-navy">Próximas revisiones</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Actividades que requieren tu atención.
            </p>
          </div>
          <Button asChild>
            <Link to="/profesor/Programas">Ver mis Programas</Link>
          </Button>
        </div>
        <div className="mt-5 divide-y">
          {[
            "Evaluación final · Gestor de Seguridad",
            "Actividad 3 · Visitador Médico",
            "Proyecto final · Administración",
          ].map((name, i) => (
            <div key={name} className="flex items-center gap-4 py-4">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted text-sm font-semibold text-navy">
                {i + 1}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-navy">{name}</p>
                <p className="text-xs text-muted-foreground">{3 + i} entregas pendientes</p>
              </div>
              <span className="text-xs font-medium text-amber-700">Pendiente</span>
            </div>
          ))}
        </div>
      </section>
    </AppShell>
  );
}

export function TeacherSection({ type }: { type: "courses" | "students" }) {
  const content = {
    courses: ["Mis Programas", "Consulta los programas que tienes asignados.", BookOpen],
    students: ["Mis estudiantes", "Consulta progreso y participación de tus grupos.", Users],
  }[type];
  const Icon = content[2] as typeof BookOpen;
  return (
    <AppShell items={teacherNav} role="Profesor">
      <PageHeader title={content[0] as string} description={content[1] as string} />
      <div className="mt-6 surface-card flex min-h-72 flex-col items-center justify-center p-8 text-center">
        <Icon className="h-9 w-9 text-gold" />
        <h2 className="mt-4 font-semibold text-navy">Todo listo para empezar</h2>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          Este espacio mostrará la información académica asignada por administración.
        </p>
      </div>
    </AppShell>
  );
}
