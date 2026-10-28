import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import {
  BookOpen,
  BrainCircuit,
  ArrowLeft,
  ArrowRight,
  Award,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Eye,
  EyeOff,
  FileText,
  Image as ImageIcon,
  LockKeyhole,
  Loader2,
  PlayCircle,
  Save,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/layouts/AppShell";
import { studentNav } from "@/components/layouts/nav";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatsCard } from "@/components/shared/StatsCard";
import { CourseProgressCard } from "@/components/shared/CourseProgressCard";
import { UserAvatar } from "@/components/shared/UserAvatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth, type AuthUser } from "@/contexts/AuthContext";
import { api, ApiError } from "@/lib/api";
import { firstError, personNameError, phoneError } from "@/lib/validation";
import { toPublicCourse } from "@/hooks/use-public-courses";
import type { Course, Enrollment } from "@/types";
import type { LessonDraft, LmsCourse } from "@/types/lms";
import { cn } from "@/lib/utils";

interface StudentEnrollmentResponse {
  enrollments: Array<{
    id: string;
    course: LmsCourse;
    progressPercent: number;
    completedLessonIds: string[];
    examStatus: "NOT_STARTED" | "PENDING_REVIEW" | "FAILED_REVIEWED" | "PASSED";
    completedAt: string | null;
    examScore: number | null;
    enrolledAt: string;
  }>;
}

interface RealEnrollment {
  id: string;
  course: Course;
  source: LmsCourse;
  enrollment: Enrollment;
  examScore: number | null;
  enrolledAt: string;
  completedLessonIds: string[];
  examStatus: "NOT_STARTED" | "PENDING_REVIEW" | "FAILED_REVIEWED" | "PASSED";
  courseCompleted: boolean;
}

const Shell = ({ children }: { children: React.ReactNode }) => (
  <AppShell items={studentNav}>{children}</AppShell>
);

function useStudentEnrollments() {
  const [items, setItems] = useState<RealEnrollment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    api<StudentEnrollmentResponse>("/student/enrollments")
      .then(({ enrollments }) =>
        setItems(
          enrollments.map((item) => {
            const lessonsTotal =
              item.course.modules?.reduce((total, module) => total + module.lessons.length, 0) ?? 0;
            const progress = Math.max(0, Math.min(100, item.progressPercent));
            return {
              id: item.id,
              course: toPublicCourse(item.course),
              source: item.course,
              examScore: item.examScore,
              enrolledAt: item.enrolledAt,
              completedLessonIds: item.completedLessonIds || [],
              examStatus: item.examStatus || "NOT_STARTED",
              courseCompleted: item.examStatus === "PASSED" || Boolean(item.completedAt),
              enrollment: {
                courseSlug: item.course.slug,
                progress,
                lessonsTotal,
                lessonsCompleted: Math.round((lessonsTotal * progress) / 100),
                status: progress >= 100 ? "Completado" : progress > 0 ? "En progreso" : "Pendiente",
              },
            };
          }),
        ),
      )
      .catch((reason) =>
        setError(reason instanceof ApiError ? reason.message : "No pudimos cargar tus Programas."),
      )
      .finally(() => setLoading(false));
  }, []);
  return { items, loading, error };
}

function EmptyCourses({ error }: { error?: string }) {
  return (
    <div className="surface-card px-6 py-14 text-center">
      <span className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-gold/10 text-gold">
        <BookOpen />
      </span>
      <h2 className="mt-4 font-display text-xl font-semibold text-navy">
        {error ? "No pudimos cargar tus Programas" : "Aún no tienes Programas activos"}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        {error || "Explora la academia, elige un programa y completa tu inscripción para empezar."}
      </p>
      {!error && (
        <Button asChild variant="gold" className="mt-6">
          <Link to="/courses">Explorar Programas</Link>
        </Button>
      )}
    </div>
  );
}

export function RealStudentDashboard() {
  const { user } = useAuth();
  const { items, loading, error } = useStudentEnrollments();
  const completed = items.filter((item) => item.enrollment.status === "Completado").length;
  const average = items.length
    ? Math.round(items.reduce((sum, item) => sum + item.enrollment.progress, 0) / items.length)
    : 0;
  return (
    <Shell>
      <PageHeader
        title={`Hola, ${user?.firstName ?? "estudiante"} 👋`}
        description="Tus programas, avances y próximos logros en un solo lugar."
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatsCard label="Programas adquiridos" value={String(items.length)} icon={BookOpen} />
        <StatsCard label="En progreso" value={String(items.length - completed)} icon={PlayCircle} />
        <StatsCard label="Completados" value={String(completed)} icon={CheckCircle2} />
        <StatsCard label="Avance promedio" value={`${average}%`} icon={Clock3} />
      </div>
      <section className="mt-10">
        <div className="mb-5 flex items-center justify-between gap-4">
          <div>
            <h2 className="font-display text-xl font-semibold text-navy">Continúa aprendiendo</h2>
            <p className="mt-1 text-sm text-muted-foreground">Accede al contenido ya habilitado.</p>
          </div>
          <Button asChild variant="outline">
            <Link to="/app/courses">Ver todos</Link>
          </Button>
        </div>
        {loading ? (
          <div className="surface-card h-48 animate-pulse bg-muted" />
        ) : items.length ? (
          <div className="grid gap-5 xl:grid-cols-2">
            {items.slice(0, 4).map((item) => (
              <CourseProgressCard key={item.id} course={item.course} enrollment={item.enrollment} />
            ))}
          </div>
        ) : (
          <EmptyCourses error={error} />
        )}
      </section>
    </Shell>
  );
}

export function RealMyCoursesPage() {
  const { items, loading, error } = useStudentEnrollments();
  const [filter, setFilter] = useState("Todos");
  const filtered = items.filter((item) => filter === "Todos" || item.enrollment.status === filter);
  return (
    <Shell>
      <PageHeader
        title="Mis Programas"
        description="Programas con pago aprobado y acceso habilitado."
      />
      <div className="mb-6 flex flex-wrap gap-2">
        {["Todos", "En progreso", "Completado", "Pendiente"].map((item) => (
          <Button
            key={item}
            variant={filter === item ? "navy" : "outline"}
            size="sm"
            onClick={() => setFilter(item)}
          >
            {item}
          </Button>
        ))}
      </div>
      {loading ? (
        <div className="surface-card h-48 animate-pulse bg-muted" />
      ) : filtered.length ? (
        <div className="grid gap-5 xl:grid-cols-2">
          {filtered.map((item) => (
            <CourseProgressCard key={item.id} course={item.course} enrollment={item.enrollment} />
          ))}
        </div>
      ) : (
        <EmptyCourses error={error} />
      )}
    </Shell>
  );
}

function InteractiveActivity({
  lesson,
  onSolved,
}: {
  lesson: LessonDraft;
  onSolved: (answer: number | number[]) => void;
}) {
  const activity = lesson.interaction;
  const [choice, setChoice] = useState<number | null>(null);
  const [order, setOrder] = useState<number[]>(
    () => activity?.options.map((_, i) => i).reverse() || [],
  );
  const [matches, setMatches] = useState<number[]>(() => activity?.pairs.map(() => -1) || []);
  const [result, setResult] = useState<"idle" | "wrong" | "correct">("idle");
  if (!activity)
    return <p className="text-sm text-muted-foreground">Esta actividad aún no está configurada.</p>;
  const check = () => {
    const correct =
      activity.type === "matching"
        ? matches.every((value, index) => value === index)
        : activity.type === "ordering"
          ? order.every((value, index) => value === index)
          : choice === activity.correctAnswers[0];
    setResult(correct ? "correct" : "wrong");
    if (correct)
      onSolved(
        activity.type === "matching" ? matches : activity.type === "ordering" ? order : choice!,
      );
  };
  const move = (index: number, direction: number) => {
    const target = index + direction;
    if (target < 0 || target >= order.length) return;
    const next = [...order];
    [next[index], next[target]] = [next[target]!, next[index]!];
    setOrder(next);
    setResult("idle");
  };
  return (
    <div className="surface-card overflow-hidden border-gold/30">
      <div className="bg-navy p-6 text-white">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-gold">
          <BrainCircuit className="h-4 w-4" /> Repaso interactivo
        </p>
        <h3 className="mt-3 text-xl font-semibold">{activity.prompt || lesson.title}</h3>
        <p className="mt-2 text-sm text-white/65">
          {activity.type === "ordering"
            ? "Organiza los elementos en la secuencia correcta."
            : activity.type === "matching"
              ? "Relaciona cada concepto con su respuesta."
              : "Selecciona la respuesta correcta."}
        </p>
      </div>
      <div className="space-y-3 p-6">
        {(activity.type === "multiple_choice" || activity.type === "true_false") &&
          activity.options.map((option, index) => (
            <button
              key={index}
              onClick={() => {
                setChoice(index);
                setResult("idle");
              }}
              className={cn(
                "flex w-full items-center gap-3 rounded-xl border p-4 text-left transition",
                choice === index
                  ? "border-gold bg-gold/10 text-navy"
                  : "border-border hover:border-gold/50",
              )}
            >
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-muted text-xs font-bold">
                {String.fromCharCode(65 + index)}
              </span>
              {option}
            </button>
          ))}
        {activity.type === "ordering" &&
          order.map((optionIndex, index) => (
            <div
              key={optionIndex}
              className="flex items-center gap-3 rounded-xl border border-border p-3"
            >
              <span className="grid h-7 w-7 place-items-center rounded bg-gold/15 text-xs font-bold text-gold">
                {index + 1}
              </span>
              <span className="flex-1 text-sm">{activity.options[optionIndex]}</span>
              <Button
                size="icon"
                variant="ghost"
                disabled={index === 0}
                onClick={() => move(index, -1)}
              >
                <ArrowLeft className="h-4 w-4 rotate-90" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                disabled={index === order.length - 1}
                onClick={() => move(index, 1)}
              >
                <ArrowRight className="h-4 w-4 rotate-90" />
              </Button>
            </div>
          ))}
        {activity.type === "matching" &&
          activity.pairs.map((pair, index) => (
            <div key={index} className="grid items-center gap-2 sm:grid-cols-[1fr_auto_1fr]">
              <div className="rounded-lg bg-muted p-3 text-sm font-medium text-navy">
                {pair.left}
              </div>
              <span className="text-center text-gold">↔</span>
              <select
                className="h-11 rounded-lg border border-input bg-white px-3 text-sm"
                value={matches[index]}
                onChange={(e) => {
                  setMatches(
                    matches.map((value, i) => (i === index ? Number(e.target.value) : value)),
                  );
                  setResult("idle");
                }}
              >
                <option value={-1}>Elige una relación…</option>
                {[...activity.pairs].reverse().map((item) => {
                  const original = activity.pairs.indexOf(item);
                  return (
                    <option key={original} value={original}>
                      {item.right}
                    </option>
                  );
                })}
              </select>
            </div>
          ))}
        {result === "wrong" && (
          <div className="rounded-lg bg-red-50 p-3 text-sm font-medium text-red-700">
            Aún no es correcto. Revisa el contenido e inténtalo nuevamente.
          </div>
        )}
        {result === "correct" && (
          <div className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-800">
            <strong>¡Excelente, respuesta correcta!</strong>
            {activity.explanation && <p className="mt-1">{activity.explanation}</p>}
          </div>
        )}
        <Button variant="gold" disabled={result === "correct"} onClick={check}>
          <CheckCircle2 /> Comprobar respuesta
        </Button>
      </div>
    </div>
  );
}

function LessonViewer({
  lesson,
  onVideoEnded,
  onInteractionSolved,
}: {
  lesson: LessonDraft;
  onVideoEnded: () => void;
  onInteractionSolved: (answer: number | number[]) => void;
}) {
  const media = lesson.mediaUrl || "";
  if (lesson.type === "interactive")
    return <InteractiveActivity key={lesson.id} lesson={lesson} onSolved={onInteractionSolved} />;
  if (lesson.type === "video") {
    return media ? (
      <div className="overflow-hidden rounded-xl bg-navy">
        <video controls className="aspect-video w-full" src={media} onEnded={onVideoEnded}>
          Tu navegador no puede reproducir este video.
        </video>
      </div>
    ) : (
      <div className="grid aspect-video place-items-center rounded-xl bg-navy text-white/70">
        Video pendiente de carga
      </div>
    );
  }
  if (lesson.type === "image") {
    return media ? (
      <img
        src={media}
        alt={lesson.title}
        className="max-h-[620px] w-full rounded-xl object-contain"
      />
    ) : null;
  }
  if (lesson.type === "pdf" || lesson.type === "file") {
    return (
      <div className="surface-card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4">
          <div className="flex items-center gap-3">
            <FileText className="h-6 w-6 text-gold" />
            <div>
              <p className="text-sm font-semibold text-navy">{lesson.title}</p>
              <p className="text-xs text-muted-foreground">Documento PDF integrado</p>
            </div>
          </div>
          {media && (
            <Button asChild size="sm" variant="outline">
              <a href={media} download>
                Descargar PDF
              </a>
            </Button>
          )}
        </div>
        {media ? (
          <iframe
            src={media}
            title={`Documento ${lesson.title}`}
            className="h-[68vh] min-h-[520px] w-full bg-white"
          />
        ) : (
          <div className="grid min-h-72 place-items-center text-sm text-muted-foreground">
            Documento pendiente de carga
          </div>
        )}
      </div>
    );
  }
  return null;
}

function CourseProgressGauge({
  value,
  completed,
  total,
}: {
  value: number;
  completed: number;
  total: number;
}) {
  const normalized = Math.min(100, Math.max(0, value));
  const color = normalized < 40 ? "#DC2626" : normalized < 75 ? "#D97706" : "#16A34A";
  const radius = 48;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="relative h-32 w-32 shrink-0" aria-label={`Avance del curso ${normalized}%`}>
      <svg className="h-full w-full -rotate-90" viewBox="0 0 120 120" role="img">
        <circle cx="60" cy="60" r={radius} fill="none" stroke="#E5E7EB" strokeWidth="9" />
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - normalized / 100)}
          className="transition-[stroke-dashoffset,stroke] duration-500 ease-out"
        />
      </svg>
      <div className="absolute inset-0 grid place-content-center text-center">
        <strong className="text-2xl font-semibold" style={{ color }}>
          {normalized}%
        </strong>
        <span className="mt-0.5 max-w-20 text-[10px] leading-3 text-muted-foreground">
          {completed} de {total} lecciones
        </span>
      </div>
    </div>
  );
}

export function RealClassroomPage() {
  const { slug = "" } = useParams();
  const { items, loading } = useStudentEnrollments();
  const enrolled = items.find((item) => item.course.slug === slug);
  const entries = useMemo(
    () =>
      enrolled?.source.modules?.flatMap((module, moduleIndex) =>
        module.lessons.map((lesson) => ({ lesson, module, moduleIndex })),
      ) ?? [],
    [enrolled],
  );
  const [selectedId, setSelectedId] = useState("");
  const [completedIds, setCompletedIds] = useState<Set<string>>(new Set());
  const [completing, setCompleting] = useState(false);
  const [interactionSolved, setInteractionSolved] = useState(false);
  const [interactionAnswer, setInteractionAnswer] = useState<number | number[] | null>(null);
  const firstPendingIndex = entries.findIndex((entry) => !completedIds.has(entry.lesson.id || ""));
  const unlockedThrough = firstPendingIndex === -1 ? entries.length - 1 : firstPendingIndex;
  const selectedIndex = Math.max(
    0,
    entries.findIndex((entry) => entry.lesson.id === selectedId),
  );
  const selectedEntry = entries[selectedIndex];
  const selected = selectedEntry?.lesson;
  const selectedCompleted = selected ? completedIds.has(selected.id || "") : false;
  const progress = enrolled?.courseCompleted
    ? 100
    : entries.length
      ? Math.round((completedIds.size * 90) / entries.length)
      : 90;
  const lessonsComplete = entries.length === completedIds.size;
  const previousCrossesModule =
    selectedIndex > 0 && entries[selectedIndex - 1]?.moduleIndex !== selectedEntry?.moduleIndex;
  const nextCrossesModule =
    selectedIndex < entries.length - 1 &&
    entries[selectedIndex + 1]?.moduleIndex !== selectedEntry?.moduleIndex;

  useEffect(() => {
    if (!enrolled) return;
    const nextCompleted = new Set(enrolled.completedLessonIds);
    setCompletedIds(nextCompleted);
    const firstPending = entries.find((entry) => !nextCompleted.has(entry.lesson.id || ""));
    setSelectedId(firstPending?.lesson.id || entries.at(-1)?.lesson.id || "");
  }, [enrolled, entries]);

  useEffect(() => {
    setInteractionSolved(false);
    setInteractionAnswer(null);
  }, [selectedId]);

  async function completeSelected() {
    if (!enrolled || !selected?.id || selectedCompleted || completing) return;
    if (selected.type === "interactive" && !interactionSolved) {
      toast.error("Resuelve correctamente la actividad antes de continuar.");
      return;
    }
    setCompleting(true);
    try {
      const response = await api<{
        message: string;
        progressPercent: number;
        completedLessonIds: string[];
      }>(`/student/enrollments/${enrolled.id}/lessons/${selected.id}/complete`, {
        method: "POST",
        body: JSON.stringify({ interactionAnswer }),
      });
      setCompletedIds(new Set(response.completedLessonIds));
      toast.success(
        response.progressPercent === 100
          ? "¡Completaste todo el contenido del curso!"
          : "Contenido completado. La siguiente lección está disponible.",
      );
    } catch (reason) {
      toast.error(reason instanceof ApiError ? reason.message : "No pudimos guardar tu avance.");
    } finally {
      setCompleting(false);
    }
  }

  function goTo(index: number) {
    const entry = entries[index];
    if (entry?.lesson.id && index <= unlockedThrough) setSelectedId(entry.lesson.id);
  }

  if (loading)
    return (
      <Shell>
        <div className="surface-card h-72 animate-pulse bg-muted" />
      </Shell>
    );
  if (!enrolled) return <Navigate to="/app/courses" replace />;
  return (
    <Shell>
      <PageHeader
        title={enrolled.course.name}
        description="Aula virtual · acceso exclusivo para estudiantes inscritos."
        actions={
          <div className="flex flex-col items-end gap-2 sm:flex-row sm:items-center">
            <CourseProgressGauge
              value={progress}
              completed={completedIds.size}
              total={entries.length}
            />
            <Button asChild variant="outline">
              <Link to="/app/courses">Salir del aula</Link>
            </Button>
          </div>
        }
      />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="min-w-0">
          {selected ? (
            <>
              <LessonViewer
                lesson={selected}
                onVideoEnded={() => void completeSelected()}
                onInteractionSolved={(answer) => {
                  setInteractionAnswer(answer);
                  setInteractionSolved(true);
                }}
              />
              <div className="mt-6">
                <p className="text-xs font-semibold text-gold">
                  Módulo {(selectedEntry?.moduleIndex ?? 0) + 1} · Lección {selectedIndex + 1} de{" "}
                  {entries.length}
                </p>
                <h2 className="mt-2 font-display text-2xl font-semibold text-navy">
                  {selected.title}
                </h2>
                {selected.content && (
                  <div className="surface-card mt-4 whitespace-pre-wrap p-6 text-sm leading-7 text-muted-foreground">
                    {selected.content}
                  </div>
                )}
                <div className="mt-6 flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:items-center sm:justify-between">
                  <Button
                    variant="outline"
                    disabled={selectedIndex === 0}
                    onClick={() => goTo(selectedIndex - 1)}
                  >
                    <ArrowLeft /> {previousCrossesModule ? "Módulo anterior" : "Anterior lección"}
                  </Button>
                  {!selectedCompleted ? (
                    <Button
                      disabled={
                        completing || (selected.type === "interactive" && !interactionSolved)
                      }
                      onClick={() => void completeSelected()}
                    >
                      {completing ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
                      Marcar como completada
                    </Button>
                  ) : (
                    <span className="flex items-center justify-center gap-2 text-sm font-semibold text-emerald-700">
                      <CheckCircle2 className="h-4 w-4" /> Lección completada
                    </span>
                  )}
                  {selectedIndex === entries.length - 1 && selectedCompleted ? (
                    <Button asChild variant="gold">
                      <Link to={`/app/exam/${slug}`}>
                        Ir al examen final <ClipboardCheck />
                      </Link>
                    </Button>
                  ) : (
                    <Button
                      variant="gold"
                      disabled={
                        selectedIndex >= entries.length - 1 || selectedIndex + 1 > unlockedThrough
                      }
                      onClick={() => goTo(selectedIndex + 1)}
                    >
                      {nextCrossesModule ? "Siguiente módulo" : "Siguiente lección"} <ArrowRight />
                    </Button>
                  )}
                </div>
              </div>
            </>
          ) : (
            <EmptyCourses error="Este curso todavía no tiene lecciones publicadas." />
          )}
        </section>
        <aside className="surface-card h-fit overflow-hidden">
          <div className="border-b border-border p-5">
            <h2 className="font-display font-semibold text-navy">Contenido del curso</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {completedIds.size} de {entries.length} lecciones completadas
            </p>
          </div>
          <div className="max-h-[680px] overflow-y-auto p-3">
            {enrolled.source.modules?.map((module, index) => {
              const moduleFirstIndex = entries.findIndex((entry) => entry.moduleIndex === index);
              const moduleLocked = moduleFirstIndex > unlockedThrough;
              return (
                <div key={module.id || index} className="mb-5">
                  <p
                    className={cn(
                      "flex items-center gap-2 px-2 text-xs font-semibold",
                      moduleLocked ? "text-muted-foreground" : "text-gold",
                    )}
                  >
                    {moduleLocked && <LockKeyhole className="h-3.5 w-3.5" />} Módulo {index + 1}
                  </p>
                  <p
                    className={cn(
                      "px-2 pb-2 pt-1 text-sm font-semibold",
                      moduleLocked ? "text-muted-foreground" : "text-navy",
                    )}
                  >
                    {module.title}
                  </p>
                  {module.description && (
                    <p className="px-2 pb-3 text-xs leading-5 text-muted-foreground">
                      {module.description}
                    </p>
                  )}
                  {module.lessons.map((lesson) => {
                    const lessonGlobalIndex = entries.findIndex(
                      (entry) => entry.lesson.id === lesson.id,
                    );
                    const isLocked = lessonGlobalIndex > unlockedThrough;
                    const isCompleted = completedIds.has(lesson.id || "");
                    const Icon = isCompleted
                      ? CheckCircle2
                      : isLocked
                        ? LockKeyhole
                        : lesson.type === "interactive"
                          ? BrainCircuit
                          : lesson.type === "video"
                            ? PlayCircle
                            : lesson.type === "image"
                              ? ImageIcon
                              : BookOpen;
                    return (
                      <button
                        key={lesson.id}
                        disabled={isLocked}
                        onClick={() => goTo(lessonGlobalIndex)}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
                          selected?.id === lesson.id
                            ? "bg-accent font-medium text-navy"
                            : "text-muted-foreground hover:bg-muted",
                          isLocked && "cursor-not-allowed opacity-55 hover:bg-transparent",
                        )}
                      >
                        <Icon
                          className={cn(
                            "h-4 w-4 shrink-0",
                            isCompleted
                              ? "text-emerald-600"
                              : isLocked
                                ? "text-muted-foreground"
                                : "text-gold",
                          )}
                        />
                        <span>{lesson.title}</span>
                      </button>
                    );
                  })}
                </div>
              );
            })}
            <div className="mt-2 border-t border-border px-2 pt-4">
              {lessonsComplete ? (
                <Button
                  asChild
                  variant={enrolled.courseCompleted ? "outline" : "gold"}
                  className="w-full justify-start"
                >
                  <Link to={`/app/exam/${slug}`}>
                    {enrolled.courseCompleted ? (
                      <Award />
                    ) : enrolled.examStatus === "PENDING_REVIEW" ? (
                      <Clock3 />
                    ) : (
                      <ClipboardCheck />
                    )}
                    {enrolled.courseCompleted
                      ? "Examen aprobado · Curso completado"
                      : enrolled.examStatus === "PENDING_REVIEW"
                        ? "Examen en revisión docente"
                        : "Rendir examen final"}
                  </Link>
                </Button>
              ) : (
                <div className="flex items-center gap-3 rounded-lg bg-muted px-3 py-3 text-sm text-muted-foreground">
                  <LockKeyhole className="h-4 w-4" />
                  <span>Examen final · completa las lecciones para desbloquearlo</span>
                </div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </Shell>
  );
}

const avatarOptions: Array<{ key: NonNullable<AuthUser["avatarKey"]>; label: string }> = [
  { key: "navy", label: "Azul institucional" },
  { key: "gold", label: "Dorado" },
  { key: "emerald", label: "Esmeralda" },
  { key: "plum", label: "Ciruela" },
];

function PasswordInput({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          type={visible ? "text" : "password"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="pr-11"
          required
        />
        <button
          type="button"
          onClick={() => setVisible(!visible)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-navy"
          aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}

export function RealProfilePage() {
  const { user, updateProfile } = useAuth();
  const [profile, setProfile] = useState({
    firstName: user?.firstName ?? "",
    lastName: user?.lastName ?? "",
    phone: user?.phone ?? "",
    avatarKey: user?.avatarKey ?? "navy",
  });
  const [passwords, setPasswords] = useState({ current: "", next: "", confirm: "" });
  const [saving, setSaving] = useState(false);
  const initials = `${profile.firstName[0] ?? ""}${profile.lastName[0] ?? ""}`.toUpperCase();
  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    const invalid = firstError(
      personNameError(profile.firstName, "El nombre"),
      personNameError(profile.lastName, "El apellido"),
      phoneError(profile.phone),
    );
    if (invalid) {
      toast.error(invalid);
      return;
    }
    setSaving(true);
    try {
      await updateProfile(profile);
      toast.success("Perfil actualizado correctamente.");
    } catch (reason) {
      toast.error(reason instanceof ApiError ? reason.message : "No se pudo actualizar el perfil.");
    } finally {
      setSaving(false);
    }
  }
  async function changePassword(event: FormEvent) {
    event.preventDefault();
    if (passwords.next !== passwords.confirm) {
      toast.error("Las contraseñas nuevas no coinciden.");
      return;
    }
    setSaving(true);
    try {
      const response = await api<{ message: string }>("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ currentPassword: passwords.current, newPassword: passwords.next }),
      });
      toast.success(response.message);
      setPasswords({ current: "", next: "", confirm: "" });
    } catch (reason) {
      toast.error(
        reason instanceof ApiError ? reason.message : "No se pudo cambiar la contraseña.",
      );
    } finally {
      setSaving(false);
    }
  }
  return (
    <Shell>
      <PageHeader
        title="Mi perfil"
        description="Información real de tu cuenta y opciones de seguridad."
      />
      <div className="grid gap-6 xl:grid-cols-2">
        <form className="surface-card p-6" onSubmit={saveProfile}>
          <div className="flex items-center gap-4">
            <UserAvatar
              initials={initials}
              tone={profile.avatarKey}
              className="h-16 w-16 text-xl"
            />
            <div>
              <h2 className="font-display text-xl font-semibold text-navy">
                {profile.firstName} {profile.lastName}
              </h2>
              <p className="text-sm text-muted-foreground">Estudiante · {user?.email}</p>
            </div>
          </div>
          <fieldset className="mt-6">
            <legend className="text-sm font-medium text-navy">Elige tu avatar</legend>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {avatarOptions.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => setProfile({ ...profile, avatarKey: option.key })}
                  className={cn(
                    "rounded-xl border p-3 text-center transition",
                    profile.avatarKey === option.key
                      ? "border-gold bg-gold/10 ring-2 ring-gold/20"
                      : "border-border hover:bg-muted",
                  )}
                >
                  <UserAvatar initials={initials} tone={option.key} className="mx-auto h-11 w-11" />
                  <span className="mt-2 block text-[11px] text-muted-foreground">
                    {option.label}
                  </span>
                </button>
              ))}
            </div>
          </fieldset>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="firstName">Nombres</Label>
              <Input
                id="firstName"
                value={profile.firstName}
                onChange={(e) => setProfile({ ...profile, firstName: e.target.value })}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="lastName">Apellidos</Label>
              <Input
                id="lastName"
                value={profile.lastName}
                onChange={(e) => setProfile({ ...profile, lastName: e.target.value })}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Correo</Label>
              <Input value={user?.email ?? ""} disabled />
            </div>
            <div className="space-y-2">
              <Label htmlFor="phone">Teléfono</Label>
              <Input
                id="phone"
                value={profile.phone}
                onChange={(e) => setProfile({ ...profile, phone: e.target.value })}
              />
            </div>
          </div>
          <Button className="mt-6" disabled={saving}>
            <Save />
            Guardar cambios
          </Button>
        </form>
        <form className="surface-card p-6" onSubmit={changePassword}>
          <div className="flex items-center gap-3">
            <ShieldCheck className="text-gold" />
            <div>
              <h2 className="font-display text-xl font-semibold text-navy">Seguridad</h2>
              <p className="text-sm text-muted-foreground">
                Usa al menos 8 caracteres, una letra y un número.
              </p>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            <PasswordInput
              id="currentPassword"
              label="Contraseña actual"
              value={passwords.current}
              onChange={(current) => setPasswords({ ...passwords, current })}
            />
            <PasswordInput
              id="newPassword"
              label="Nueva contraseña"
              value={passwords.next}
              onChange={(next) => setPasswords({ ...passwords, next })}
            />
            <PasswordInput
              id="confirmPassword"
              label="Confirmar contraseña"
              value={passwords.confirm}
              onChange={(confirm) => setPasswords({ ...passwords, confirm })}
            />
          </div>
          <Button variant="outline" className="mt-6" disabled={saving}>
            <LockKeyhole />
            Cambiar contraseña
          </Button>
        </form>
      </div>
    </Shell>
  );
}
