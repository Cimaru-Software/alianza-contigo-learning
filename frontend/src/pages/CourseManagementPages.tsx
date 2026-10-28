import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  BookOpen,
  BrainCircuit,
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  FileText,
  Image,
  Plus,
  Save,
  Trash2,
  Video,
} from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/layouts/AppShell";
import { adminNav, teacherNav } from "@/components/layouts/nav";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { api, ApiError, upload } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type {
  ExamQuestionDraft,
  FinalExamDraft,
  LessonDraft,
  LessonType,
  LmsCourse,
  ModuleDraft,
  TrainingArea,
} from "@/types/lms";

interface CourseForm {
  name: string;
  trainingAreaId: string;
  shortDescription: string;
  fullDescription: string;
  coverUrl: string;
  modality: string;
  duration: string;
  certification: string;
  endorsement: string;
  price: string | number;
  discountPercent: string | number;
  status: string;
}
const emptyCourse: CourseForm = {
  name: "",
  trainingAreaId: "",
  shortDescription: "",
  fullDescription: "",
  coverUrl: "",
  modality: "Virtual",
  duration: "A tu ritmo",
  certification: "Certificado de aprobación",
  endorsement: "",
  price: "",
  discountPercent: "",
  status: "CERRADO",
};
const emptyExam: FinalExamDraft = {
  title: "Evaluación final",
  instructions: "Responde todas las preguntas.",
  timeLimitMinutes: 45,
  attemptsAllowed: 1,
  passingScore: 70,
  questions: [],
};
const money = new Intl.NumberFormat("es-EC", { style: "currency", currency: "USD" });

function Shell({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  return (
    <AppShell
      items={user?.role === "teacher" ? teacherNav : adminNav}
      role={user?.role === "teacher" ? "Profesor" : "Administrador"}
    >
      {children}
    </AppShell>
  );
}
const Field = ({
  label,
  children,
  wide = false,
}: {
  label: string;
  children: React.ReactNode;
  wide?: boolean;
}) => (
  <div className={`space-y-2 ${wide ? "md:col-span-2" : ""}`}>
    <Label>{label}</Label>
    {children}
  </div>
);

export function CourseAdminList({ teacher = false }: { teacher?: boolean }) {
  const [courses, setCourses] = useState<LmsCourse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = () =>
    api<LmsCourse[]>("/courses/manage")
      .then(setCourses)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  useEffect(() => {
    void load();
  }, []);
  async function remove(slug: string) {
    try {
      await api(`/courses/${slug}`, { method: "DELETE" });
      setCourses(courses.filter((c) => c.slug !== slug));
      toast.success("Curso eliminado");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo eliminar");
    }
  }
  async function updateStatus(course: LmsCourse, status: "ACTIVO" | "CERRADO") {
    if (course.status === status) return;
    try {
      const updated = await api<LmsCourse>(`/courses/${course.slug}`, {
        method: "PUT",
        body: JSON.stringify({ status }),
      });
      setCourses(courses.map((item) => (item.id === course.id ? updated : item)));
      toast.success(status === "ACTIVO" ? "Curso activado" : "Curso cerrado");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "No se pudo cambiar el estado");
    }
  }
  return (
    <Shell>
      <PageHeader
        title={teacher ? "Mis Programas asignados" : "Gestión de Programas"}
        description={
          teacher
            ? "Consulta estudiantes, progreso y evaluaciones por curso."
            : "Administra precios, módulos, lecciones y evaluación final."
        }
        actions={
          !teacher ? (
            <Button asChild variant="gold">
              <Link to="/admin/courses/new">
                <Plus /> Crear curso
              </Link>
            </Button>
          ) : undefined
        }
      />
      <div className="surface-card overflow-x-auto">
        {loading ? (
          <p className="p-6 text-sm text-muted-foreground">Cargando Programas...</p>
        ) : error ? (
          <p className="p-6 text-sm text-destructive">{error}</p>
        ) : courses.length === 0 ? (
          <div className="grid min-h-72 place-items-center p-8 text-center">
            <div>
              <BookOpen className="mx-auto h-9 w-9 text-gold" />
              <h2 className="mt-4 font-semibold text-navy">
                {teacher ? "No tienes Programas asignados" : "Crea tu primer curso"}
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Luego agrega sus módulos y examen final.
              </p>
            </div>
          </div>
        ) : (
          <table className="w-full min-w-[850px] text-sm">
            <thead className="bg-muted/70 text-left text-xs text-muted-foreground">
              <tr>
                <th className="p-4">Curso</th>
                <th className="p-4">Precio</th>
                <th className="p-4">Contenido</th>
                <th className="p-4">Estado</th>
                <th className="p-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {courses.map((c) => (
                <tr key={c.id}>
                  <td className="p-4">
                    <p className="font-medium text-navy">{c.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {c.modality} · {c.duration}
                    </p>
                    <p className="mt-1 text-xs font-medium text-gold-dark">
                      Área de formación · {c.trainingArea.name}
                    </p>
                  </td>
                  <td className="p-4">
                    <p>{money.format(c.finalPrice)}</p>
                    {c.discountPercent > 0 && (
                      <p className="text-xs text-emerald-700">
                        -{c.discountPercent}% · antes {money.format(c.price)}
                      </p>
                    )}
                  </td>
                  <td className="p-4">
                    <p>
                      {c.modulesCount} módulos · {c.lessonsCount} lecciones
                    </p>
                    <p
                      className={`text-xs ${c.hasFinalExam ? "text-emerald-700" : "text-amber-700"}`}
                    >
                      {c.hasFinalExam ? "Examen configurado" : "Examen pendiente"}
                    </p>
                  </td>
                  <td className="p-4">
                    {teacher ? (
                      <Badge
                        className={
                          c.status === "ACTIVO"
                            ? "bg-emerald-50 text-emerald-800"
                            : "bg-slate-100 text-slate-700"
                        }
                      >
                        {c.status}
                      </Badge>
                    ) : (
                      <Select
                        value={c.status}
                        onValueChange={(status: "ACTIVO" | "CERRADO") =>
                          void updateStatus(c, status)
                        }
                      >
                        <SelectTrigger className="w-36 bg-white">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="ACTIVO">Activo</SelectItem>
                          <SelectItem value="CERRADO">Cerrado</SelectItem>
                        </SelectContent>
                      </Select>
                    )}
                  </td>
                  <td className="p-4">
                    <div className="flex justify-end gap-2">
                      {teacher ? (
                        <Button asChild size="sm">
                          <Link to={`/profesor/Programas/${c.slug}`}>Ver estudiantes y avance</Link>
                        </Button>
                      ) : (
                        <>
                          <Button asChild size="sm" variant="outline">
                            <Link to={`/admin/courses/${c.slug}/edit`}>Datos</Link>
                          </Button>
                          <Button asChild size="sm">
                            <Link to={`/admin/courses/${c.slug}/content`}>Constructor</Link>
                          </Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button size="icon" variant="ghost">
                                <Trash2 className="h-4 w-4 text-destructive" />
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>¿Eliminar “{c.name}”?</AlertDialogTitle>
                                <AlertDialogDescription>
                                  Se eliminarán todos sus módulos, lecciones y evaluación.
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>Cancelar</AlertDialogCancel>
                                <AlertDialogAction onClick={() => void remove(c.slug)}>
                                  Eliminar
                                </AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Shell>
  );
}

export function CourseDataForm() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState<CourseForm>(emptyCourse);
  const [loading, setLoading] = useState(Boolean(slug));
  const [saving, setSaving] = useState(false);
  const [uploadingCover, setUploadingCover] = useState(false);
  const [trainingAreas, setTrainingAreas] = useState<TrainingArea[]>([]);
  useEffect(() => {
    api<TrainingArea[]>("/training-areas")
      .then(setTrainingAreas)
      .catch(() => toast.error("No se pudieron cargar las áreas de formación"));
  }, []);
  useEffect(() => {
    if (slug)
      api<LmsCourse>(`/courses/${slug}/author`)
        .then((c) =>
          setForm({
            name: c.name,
            trainingAreaId: c.trainingArea.id,
            shortDescription: c.shortDescription,
            fullDescription: c.fullDescription,
            coverUrl: c.coverUrl || "",
            modality: c.modality,
            duration: c.duration,
            certification: c.certification,
            endorsement: c.endorsement,
            price: c.price,
            discountPercent: c.discountPercent,
            status: c.status,
          }),
        )
        .catch(() => toast.error("No se pudo cargar el curso"))
        .finally(() => setLoading(false));
  }, [slug]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const saved = await api<LmsCourse>(slug ? `/courses/${slug}` : "/courses", {
        method: slug ? "PUT" : "POST",
        body: JSON.stringify(slug ? form : { ...form, status: "CERRADO" }),
      });
      toast.success(slug ? "Curso actualizado" : "Curso creado");
      navigate(`/admin/courses/${saved.slug}/content`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo guardar");
    } finally {
      setSaving(false);
    }
  }
  if (loading)
    return (
      <Shell>
        <p>Cargando...</p>
      </Shell>
    );
  return (
    <Shell>
      <PageHeader
        title={slug ? "Editar información del curso" : "Crear un nuevo curso"}
        description="Define su presentación, precio y disponibilidad."
      />
      <form onSubmit={submit} className="surface-card grid gap-5 p-6 md:grid-cols-2">
        <Field label="Nombre del curso" wide>
          <Input
            required
            value={String(form.name)}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </Field>
        <Field label="Área de formación">
          <Select
            required
            value={String(form.trainingAreaId)}
            onValueChange={(trainingAreaId) => setForm({ ...form, trainingAreaId })}
          >
            <SelectTrigger>
              <SelectValue placeholder="Selecciona un área" />
            </SelectTrigger>
            <SelectContent>
              {trainingAreas.map((area) => (
                <SelectItem key={area.id} value={area.id}>
                  {area.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {trainingAreas.length === 0 && (
            <p className="text-xs text-muted-foreground">
              Crea primero un área desde Áreas de formación.
            </p>
          )}
        </Field>
        <Field label="Descripción corta" wide>
          <Input
            required
            maxLength={240}
            value={String(form.shortDescription)}
            onChange={(e) => setForm({ ...form, shortDescription: e.target.value })}
          />
        </Field>
        <Field label="Descripción completa" wide>
          <Textarea
            rows={6}
            value={String(form.fullDescription)}
            onChange={(e) => setForm({ ...form, fullDescription: e.target.value })}
          />
        </Field>
        <Field label="Portada del curso">
          <Input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            disabled={uploadingCover}
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setUploadingCover(true);
              try {
                const coverUrl = await upload(file);
                setForm({ ...form, coverUrl });
                toast.success("Portada cargada");
              } catch (error) {
                toast.error(error instanceof ApiError ? error.message : "No se pudo cargar");
              } finally {
                setUploadingCover(false);
              }
            }}
          />
          {form.coverUrl && (
            <img
              src={String(form.coverUrl)}
              alt="Vista previa de portada"
              className="mt-3 aspect-[16/7] w-full rounded-xl object-cover"
            />
          )}
          <p className="text-xs text-muted-foreground">
            JPG, PNG o WebP · recomendado 1600 × 900 px.
          </p>
        </Field>
        <Field label="Modalidad">
          <Input
            value={String(form.modality)}
            onChange={(e) => setForm({ ...form, modality: e.target.value })}
          />
        </Field>
        <Field label="Duración">
          <Input
            value={String(form.duration)}
            onChange={(e) => setForm({ ...form, duration: e.target.value })}
          />
        </Field>
        <Field label="Precio USD">
          <Input
            type="number"
            min="0"
            step="0.01"
            value={form.price}
            placeholder="Ej. 120.00"
            onChange={(e) => setForm({ ...form, price: e.target.value })}
          />
        </Field>
        <Field label="Descuento (%)">
          <Input
            type="number"
            min="0"
            max="100"
            value={form.discountPercent}
            placeholder="Sin descuento"
            onChange={(e) => setForm({ ...form, discountPercent: e.target.value })}
          />
        </Field>
        <Field label="Certificación">
          <Input
            value={String(form.certification)}
            onChange={(e) => setForm({ ...form, certification: e.target.value })}
          />
        </Field>
        <Field label="Institución que avala">
          <Input
            value={String(form.endorsement)}
            onChange={(e) => setForm({ ...form, endorsement: e.target.value })}
          />
        </Field>
        <Field label="Estado">
          <Select
            value={String(form.status)}
            onValueChange={(status) => setForm({ ...form, status })}
            disabled={!slug}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ACTIVO">Activo · disponible</SelectItem>
              <SelectItem value="CERRADO">Cerrado · no disponible</SelectItem>
            </SelectContent>
          </Select>
          {!slug && (
            <p className="text-xs text-muted-foreground">
              Se crea cerrado. Podrás activarlo después de agregar un módulo y el examen final.
            </p>
          )}
        </Field>
        <div className="flex items-end">
          <Button type="submit" variant="gold" disabled={saving || !form.trainingAreaId}>
            <Save /> {saving ? "Guardando..." : "Guardar y editar contenido"}
          </Button>
        </div>
      </form>
    </Shell>
  );
}

const newLesson = (type: LessonType): LessonDraft => ({
  title: type === "interactive" ? "Repaso interactivo" : "Nueva lección",
  type,
  content: "",
  mediaUrl: "",
  durationMinutes: 0,
  isPreview: false,
  ...(type === "interactive"
    ? {
        interaction: {
          type: "multiple_choice",
          prompt: "",
          options: ["", ""],
          correctAnswers: [0],
          pairs: [
            { left: "", right: "" },
            { left: "", right: "" },
          ],
          explanation: "",
        },
      }
    : {}),
});
export function CourseContentBuilder() {
  const { slug = "" } = useParams();
  const { user } = useAuth();
  const [course, setCourse] = useState<LmsCourse | null>(null);
  const [modules, setModules] = useState<ModuleDraft[]>([]);
  const [exam, setExam] = useState<FinalExamDraft>(emptyExam);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    api<LmsCourse>(`/courses/${slug}/author`)
      .then((c) => {
        setCourse(c);
        setModules(c.modules || []);
        setExam(c.finalExam || emptyExam);
      })
      .catch(() => toast.error("No se pudo cargar el curso"));
  }, [slug]);
  if (!course)
    return (
      <Shell>
        <p>Cargando constructor...</p>
      </Shell>
    );
  function move(index: number, direction: number) {
    const target = index + direction;
    if (target < 0 || target >= modules.length) return;
    const next = [...modules];
    [next[index], next[target]] = [next[target]!, next[index]!];
    setModules(next);
  }
  async function saveContent() {
    setSaving(true);
    try {
      const saved = await api<LmsCourse>(`/courses/${slug}/content`, {
        method: "PUT",
        body: JSON.stringify({ modules }),
      });
      // Keep the ids the server assigned: the next save updates these rows instead of duplicating them.
      setModules(saved.modules ?? []);
      toast.success("Contenido guardado");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo guardar");
    } finally {
      setSaving(false);
    }
  }
  return (
    <Shell>
      <PageHeader
        title={`Constructor · ${course.name}`}
        description="Organiza módulos y combina contenidos con repasos y actividades didácticas."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link to="/admin/courses">
                <ArrowLeft /> Volver a Programas
              </Link>
            </Button>
            <Button variant="gold" onClick={() => void saveContent()} disabled={saving}>
              <Save /> {saving ? "Guardando..." : "Guardar contenido"}
            </Button>
          </div>
        }
      />
      <Tabs defaultValue="content">
        <TabsList className="mb-5">
          <TabsTrigger value="content">Módulos y lecciones</TabsTrigger>
          <TabsTrigger value="exam">Examen final {exam.questions.length ? "✓" : ""}</TabsTrigger>
          <TabsTrigger value="preview">Vista previa</TabsTrigger>
        </TabsList>
        <TabsContent value="content">
          <div className="space-y-4">
            {modules.map((module, mi) => (
              <section key={mi} className="surface-card p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    className="min-w-64 flex-1 font-medium"
                    value={module.title}
                    onChange={(e) =>
                      setModules(
                        modules.map((m, i) => (i === mi ? { ...m, title: e.target.value } : m)),
                      )
                    }
                  />
                  <Button size="icon" variant="ghost" onClick={() => move(mi, -1)}>
                    <ChevronUp />
                  </Button>
                  <Button size="icon" variant="ghost" onClick={() => move(mi, 1)}>
                    <ChevronDown />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => setModules(modules.filter((_, i) => i !== mi))}
                  >
                    <Trash2 className="text-destructive" />
                  </Button>
                </div>
                <Textarea
                  className="mt-3"
                  placeholder="Descripción del módulo"
                  value={module.description}
                  onChange={(e) =>
                    setModules(
                      modules.map((m, i) => (i === mi ? { ...m, description: e.target.value } : m)),
                    )
                  }
                />
                <div className="mt-4 space-y-3">
                  {module.lessons.map((lesson, li) => (
                    <LessonEditor
                      key={li}
                      lesson={lesson}
                      onChange={(lesson) =>
                        setModules(
                          modules.map((m, i) =>
                            i === mi
                              ? { ...m, lessons: m.lessons.map((l, j) => (j === li ? lesson : l)) }
                              : m,
                          ),
                        )
                      }
                      onDelete={() =>
                        setModules(
                          modules.map((m, i) =>
                            i === mi ? { ...m, lessons: m.lessons.filter((_, j) => j !== li) } : m,
                          ),
                        )
                      }
                    />
                  ))}
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {(["video", "text", "image", "pdf", "interactive"] as LessonType[]).map(
                    (type) => (
                      <Button
                        key={type}
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          setModules(
                            modules.map((m, i) =>
                              i === mi ? { ...m, lessons: [...m.lessons, newLesson(type)] } : m,
                            ),
                          )
                        }
                      >
                        <Plus className="h-4 w-4" />{" "}
                        {type === "video"
                          ? "Video"
                          : type === "text"
                            ? "Texto"
                            : type === "image"
                              ? "Imagen"
                              : type === "pdf"
                                ? "PDF"
                                : "Actividad interactiva"}
                      </Button>
                    ),
                  )}
                </div>
              </section>
            ))}
            <Button
              variant="outline"
              onClick={() =>
                setModules([
                  ...modules,
                  { title: `Módulo ${modules.length + 1}`, description: "", lessons: [] },
                ])
              }
            >
              <Plus /> Agregar módulo
            </Button>
          </div>
        </TabsContent>
        <TabsContent value="exam">
          <ExamEditor exam={exam} setExam={setExam} slug={slug} />
        </TabsContent>
        <TabsContent value="preview">
          <CoursePreview course={course} modules={modules} />
        </TabsContent>
      </Tabs>
    </Shell>
  );
}

function LessonEditor({
  lesson,
  onChange,
  onDelete,
}: {
  lesson: LessonDraft;
  onChange: (value: LessonDraft) => void;
  onDelete: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const Icon =
    lesson.type === "interactive"
      ? BrainCircuit
      : lesson.type === "video"
        ? Video
        : lesson.type === "image"
          ? Image
          : FileText;
  async function file(selected?: File) {
    if (!selected) return;
    setUploading(true);
    try {
      onChange({ ...lesson, mediaUrl: await upload(selected) });
      toast.success("Archivo cargado");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Error al cargar");
    } finally {
      setUploading(false);
    }
  }
  return (
    <div className="rounded-xl bg-muted/60 p-4">
      <div className="flex items-center gap-3">
        <Icon className="h-5 w-5 text-gold" />
        <Input
          className="flex-1 bg-white"
          value={lesson.title}
          onChange={(e) => onChange({ ...lesson, title: e.target.value })}
        />
        <Badge variant="outline">{lesson.type}</Badge>
        <Button size="icon" variant="ghost" onClick={onDelete}>
          <Trash2 className="h-4 w-4 text-destructive" />
        </Button>
      </div>
      {lesson.type === "interactive" ? (
        <InteractionEditor lesson={lesson} onChange={onChange} />
      ) : (
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <Field label="Contenido / descripción">
            <Textarea
              rows={3}
              value={lesson.content}
              onChange={(e) => onChange({ ...lesson, content: e.target.value })}
            />
          </Field>
          {lesson.type !== "text" && (
            <Field label="Archivo o URL">
              <Input
                value={lesson.mediaUrl}
                onChange={(e) => onChange({ ...lesson, mediaUrl: e.target.value })}
                placeholder="https://..."
              />
              <Input
                className="mt-2"
                type="file"
                accept={
                  lesson.type === "video"
                    ? "video/mp4,video/webm"
                    : lesson.type === "image"
                      ? "image/*"
                      : "application/pdf"
                }
                disabled={uploading}
                onChange={(e) => void file(e.target.files?.[0])}
              />
            </Field>
          )}
          {lesson.type === "video" && (
            <Field label="Duración del video (minutos)">
              <Input
                type="number"
                min="0"
                value={lesson.durationMinutes || ""}
                placeholder="Ej. 12"
                onChange={(e) =>
                  onChange({ ...lesson, durationMinutes: Number(e.target.value) || 0 })
                }
              />
            </Field>
          )}
        </div>
      )}
    </div>
  );
}

function InteractionEditor({
  lesson,
  onChange,
}: {
  lesson: LessonDraft;
  onChange: (value: LessonDraft) => void;
}) {
  const interaction = lesson.interaction!;
  const update = (changes: Partial<typeof interaction>) =>
    onChange({ ...lesson, interaction: { ...interaction, ...changes } });
  const labels = {
    multiple_choice: "Opción múltiple",
    true_false: "Verdadero o falso",
    ordering: "Ordenar los pasos",
    matching: "Relacionar parejas",
  } as const;
  const setType = (type: typeof interaction.type) => {
    const options = type === "true_false" ? ["Verdadero", "Falso"] : interaction.options;
    update({ type, options, correctAnswers: [0] });
  };
  return (
    <div className="mt-4 space-y-4 rounded-xl border border-gold/30 bg-white p-4">
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Tipo de actividad">
          <Select
            value={interaction.type}
            onValueChange={(value) => setType(value as typeof interaction.type)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(labels).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Consigna o pregunta">
          <Input
            value={interaction.prompt}
            onChange={(e) => update({ prompt: e.target.value })}
            placeholder="¿Qué aprendimos en este módulo?"
          />
        </Field>
      </div>
      {interaction.type === "matching" ? (
        <div className="space-y-2">
          <Label>Parejas correctas</Label>
          {interaction.pairs.map((pair, index) => (
            <div key={index} className="grid grid-cols-[1fr_auto_1fr_auto] items-center gap-2">
              <Input
                value={pair.left}
                placeholder="Concepto"
                onChange={(e) =>
                  update({
                    pairs: interaction.pairs.map((p, i) =>
                      i === index ? { ...p, left: e.target.value } : p,
                    ),
                  })
                }
              />
              <span className="text-gold">↔</span>
              <Input
                value={pair.right}
                placeholder="Definición"
                onChange={(e) =>
                  update({
                    pairs: interaction.pairs.map((p, i) =>
                      i === index ? { ...p, right: e.target.value } : p,
                    ),
                  })
                }
              />
              <Button
                size="icon"
                variant="ghost"
                onClick={() => update({ pairs: interaction.pairs.filter((_, i) => i !== index) })}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button
            size="sm"
            variant="outline"
            onClick={() => update({ pairs: [...interaction.pairs, { left: "", right: "" }] })}
          >
            <Plus /> Añadir pareja
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          <Label>
            {interaction.type === "ordering"
              ? "Pasos en el orden correcto"
              : "Opciones (marca la correcta)"}
          </Label>
          {interaction.options.map((option, index) => (
            <div key={index} className="flex items-center gap-2">
              {interaction.type !== "ordering" && (
                <input
                  type="radio"
                  name={`correct-${lesson.title}`}
                  checked={interaction.correctAnswers[0] === index}
                  onChange={() => update({ correctAnswers: [index] })}
                />
              )}
              <Badge variant="outline">{index + 1}</Badge>
              <Input
                disabled={interaction.type === "true_false"}
                value={option}
                onChange={(e) =>
                  update({
                    options: interaction.options.map((item, i) =>
                      i === index ? e.target.value : item,
                    ),
                  })
                }
              />
              {interaction.type !== "true_false" && (
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() =>
                    update({ options: interaction.options.filter((_, i) => i !== index) })
                  }
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </div>
          ))}
          {interaction.type !== "true_false" && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => update({ options: [...interaction.options, ""] })}
            >
              <Plus /> Añadir {interaction.type === "ordering" ? "paso" : "opción"}
            </Button>
          )}
        </div>
      )}
      <Field label="Explicación al responder correctamente">
        <Textarea
          rows={2}
          value={interaction.explanation}
          onChange={(e) => update({ explanation: e.target.value })}
          placeholder="Refuerza aquí la idea principal..."
        />
      </Field>
    </div>
  );
}

function ExamEditor({
  exam,
  setExam,
  slug,
}: {
  exam: FinalExamDraft;
  setExam: (value: FinalExamDraft) => void;
  slug: string;
}) {
  const [saving, setSaving] = useState(false);
  const question = (): ExamQuestionDraft => ({
    prompt: "",
    type: "single_choice",
    options: ["", ""],
    correctAnswers: [0],
    points: 1,
  });
  async function save() {
    setSaving(true);
    try {
      await api(`/courses/${slug}/exam`, { method: "PUT", body: JSON.stringify(exam) });
      toast.success("Examen final guardado");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo guardar");
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="space-y-5">
      <div className="surface-card grid gap-4 p-5 md:grid-cols-2">
        <Field label="Título">
          <Input value={exam.title} onChange={(e) => setExam({ ...exam, title: e.target.value })} />
        </Field>
        <Field label="Puntaje mínimo (%)">
          <Input
            type="number"
            min="1"
            max="100"
            value={exam.passingScore}
            onChange={(e) => setExam({ ...exam, passingScore: Number(e.target.value) })}
          />
        </Field>
        <Field label="Tiempo límite">
          <Input
            type="number"
            min="1"
            value={exam.timeLimitMinutes}
            onChange={(e) => setExam({ ...exam, timeLimitMinutes: Number(e.target.value) })}
          />
        </Field>
        <Field label="Intentos">
          <Input
            type="number"
            min="1"
            value={exam.attemptsAllowed}
            onChange={(e) => setExam({ ...exam, attemptsAllowed: Number(e.target.value) })}
          />
        </Field>
        <Field label="Instrucciones" wide>
          <Textarea
            value={exam.instructions}
            onChange={(e) => setExam({ ...exam, instructions: e.target.value })}
          />
        </Field>
      </div>
      {exam.questions.map((q, qi) => (
        <section key={qi} className="surface-card p-5">
          <div className="flex gap-3">
            <span className="font-semibold text-gold">{qi + 1}</span>
            <Input
              className="flex-1"
              placeholder="Escribe la pregunta"
              value={q.prompt}
              onChange={(e) =>
                setExam({
                  ...exam,
                  questions: exam.questions.map((x, i) =>
                    i === qi ? { ...x, prompt: e.target.value } : x,
                  ),
                })
              }
            />
            <Button
              size="icon"
              variant="ghost"
              onClick={() =>
                setExam({ ...exam, questions: exam.questions.filter((_, i) => i !== qi) })
              }
            >
              <Trash2 className="text-destructive" />
            </Button>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {q.options.map((option, oi) => (
              <label key={oi} className="flex items-center gap-2">
                <input
                  type="radio"
                  name={`correct-${qi}`}
                  checked={q.correctAnswers[0] === oi}
                  onChange={() =>
                    setExam({
                      ...exam,
                      questions: exam.questions.map((x, i) =>
                        i === qi ? { ...x, correctAnswers: [oi] } : x,
                      ),
                    })
                  }
                />
                <Input
                  placeholder={`Opción ${oi + 1}`}
                  value={option}
                  onChange={(e) =>
                    setExam({
                      ...exam,
                      questions: exam.questions.map((x, i) =>
                        i === qi
                          ? {
                              ...x,
                              options: x.options.map((o, j) => (j === oi ? e.target.value : o)),
                            }
                          : x,
                      ),
                    })
                  }
                />
              </label>
            ))}
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="mt-2"
            onClick={() =>
              setExam({
                ...exam,
                questions: exam.questions.map((x, i) =>
                  i === qi ? { ...x, options: [...x.options, ""] } : x,
                ),
              })
            }
          >
            <Plus /> Agregar opción
          </Button>
        </section>
      ))}
      <div className="flex gap-3">
        <Button
          variant="outline"
          onClick={() => setExam({ ...exam, questions: [...exam.questions, question()] })}
        >
          <Plus /> Agregar pregunta
        </Button>
        <Button variant="gold" onClick={() => void save()} disabled={saving}>
          <Save /> {saving ? "Guardando..." : "Guardar examen final"}
        </Button>
      </div>
    </div>
  );
}

function CoursePreview({ course, modules }: { course: LmsCourse; modules: ModuleDraft[] }) {
  const activityIcon = (type: LessonType) => {
    if (type === "interactive") return BrainCircuit;
    if (type === "video") return Video;
    if (type === "image") return Image;
    return FileText;
  };

  const activityLabel = (type: LessonType) => {
    if (type === "interactive") return "Actividad interactiva";
    if (type === "video") return "Video";
    if (type === "image") return "Imagen";
    if (type === "pdf") return "Documento PDF";
    if (type === "file") return "Recurso";
    return "Lectura";
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <section className="surface-card overflow-hidden">
        {course.coverUrl && (
          <img src={course.coverUrl} alt="" className="aspect-[16/7] w-full object-cover" />
        )}
        <div className="p-6">
          <h2 className="text-2xl font-semibold text-navy">{course.name}</h2>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            {course.fullDescription || course.shortDescription}
          </p>
        </div>
      </section>
      <aside className="surface-card h-fit p-5">
        <h3 className="font-semibold text-navy">Contenido del curso</h3>
        <div className="mt-4 space-y-4">
          {modules.map((m, i) => (
            <div key={i} className="rounded-xl border border-border p-3">
              <div className="flex items-center gap-2">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-navy text-xs font-semibold text-white">
                  {i + 1}
                </span>
                <p className="text-sm font-semibold text-navy">{m.title}</p>
              </div>
              {m.lessons.length ? (
                <div className="mt-3 space-y-3 border-l border-border pl-3">
                  {m.lessons.map((lesson, lessonIndex) => {
                    const ActivityIcon = activityIcon(lesson.type);
                    return (
                      <div key={lesson.id || lessonIndex}>
                        <div className="flex items-start gap-2">
                          <BookOpen className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-navy">
                              Lección {lessonIndex + 1}: {lesson.title}
                            </p>
                            <p className="text-xs text-muted-foreground">1 actividad</p>
                          </div>
                        </div>
                        <div className="ml-6 mt-2 flex items-center gap-2 rounded-lg bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
                          <ActivityIcon className="h-3.5 w-3.5 shrink-0 text-gold" />
                          <span>{activityLabel(lesson.type)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="mt-3 text-xs text-muted-foreground">Sin lecciones todavía</p>
              )}
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}
