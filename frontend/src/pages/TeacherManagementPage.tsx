import { useEffect, useState, type FormEvent } from "react";
import { Plus, UserCheck } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/layouts/AppShell";
import { adminNav } from "@/components/layouts/nav";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { api, ApiError } from "@/lib/api";
import { cedulaError, emailError, firstError, personNameError, phoneError } from "@/lib/validation";
import type { AuthUser } from "@/contexts/AuthContext";

type TeacherField = "firstName" | "lastName" | "email" | "phone" | "nationalId" | "password";
const emptyTeacher: Record<TeacherField, string> = {
  firstName: "",
  lastName: "",
  email: "",
  phone: "",
  nationalId: "",
  password: "",
};
const teacherFields: Array<{
  label: string;
  key: TeacherField;
  type: string;
  required: boolean;
  maxLength: number;
}> = [
  { label: "Nombres", key: "firstName", type: "text", required: true, maxLength: 100 },
  { label: "Apellidos", key: "lastName", type: "text", required: true, maxLength: 100 },
  { label: "Correo", key: "email", type: "email", required: true, maxLength: 254 },
  { label: "Teléfono", key: "phone", type: "tel", required: false, maxLength: 30 },
  { label: "Cédula (opcional)", key: "nationalId", type: "text", required: false, maxLength: 10 },
  {
    label: "Contraseña temporal",
    key: "password",
    type: "password",
    required: true,
    maxLength: 128,
  },
];

export function TeacherManagementPage() {
  const [teachers, setTeachers] = useState<AuthUser[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<Record<TeacherField, string>>(emptyTeacher);
  const load = () =>
    api<{ users: AuthUser[] }>("/auth/users?role=teacher")
      .then((d) => {
        setTeachers(d.users);
        setListError("");
      })
      .catch((err) =>
        setListError(err instanceof ApiError ? err.message : "No se pudo cargar la lista."),
      )
      .finally(() => setLoading(false));
  useEffect(() => {
    void load();
  }, []);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    const invalid = firstError(
      personNameError(form.firstName, "El nombre"),
      personNameError(form.lastName, "El apellido"),
      emailError(form.email),
      phoneError(form.phone),
      cedulaError(form.nationalId, false),
    );
    if (invalid) {
      toast.error(invalid);
      return;
    }
    setSaving(true);
    try {
      await api("/auth/teachers", { method: "POST", body: JSON.stringify(form) });
      toast.success("Cuenta de profesor creada");
      setOpen(false);
      setForm(emptyTeacher);
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo crear la cuenta.");
    } finally {
      setSaving(false);
    }
  }
  return (
    <AppShell items={adminNav} role="Administrador">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <PageHeader
          title="Profesores"
          description="Crea y administra las cuentas del equipo docente."
        />
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button variant="gold">
              <Plus className="h-4 w-4" /> Nuevo profesor
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Crear cuenta de profesor</DialogTitle>
            </DialogHeader>
            <form onSubmit={submit} className="mt-2 grid gap-4 sm:grid-cols-2">
              {teacherFields.map(({ label, key, type, required, maxLength }) => (
                <div key={key} className={`space-y-2 ${key === "password" ? "sm:col-span-2" : ""}`}>
                  <Label htmlFor={`teacher-${key}`}>{label}</Label>
                  <Input
                    id={`teacher-${key}`}
                    type={type}
                    required={required}
                    minLength={key === "password" ? 8 : 0}
                    maxLength={maxLength}
                    value={form[key]}
                    onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  />
                </div>
              ))}
              <Button className="sm:col-span-2" variant="gold" disabled={saving}>
                {saving ? "Creando cuenta..." : "Crear cuenta"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>
      <div className="mt-6 surface-card overflow-hidden">
        {listError ? (
          <div className="p-6 text-sm text-destructive">
            <p>{listError}</p>
            <Button variant="outline" className="mt-3" onClick={() => void load()}>
              Reintentar
            </Button>
          </div>
        ) : loading ? (
          <p className="p-6 text-sm text-muted-foreground">Cargando profesores...</p>
        ) : teachers.length === 0 ? (
          <div className="grid min-h-64 place-items-center p-8 text-center">
            <div>
              <UserCheck className="mx-auto h-9 w-9 text-gold" />
              <h2 className="mt-4 font-semibold text-navy">Aún no hay profesores</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Crea la primera cuenta para asignarle Programas.
              </p>
            </div>
          </div>
        ) : (
          <div className="divide-y">
            {teachers.map((teacher) => (
              <div key={teacher.id} className="flex items-center gap-4 p-5">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-navy text-sm font-semibold text-white">
                  {teacher.firstName[0]}
                  {teacher.lastName[0]}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-navy">{teacher.name}</p>
                  <p className="truncate text-sm text-muted-foreground">{teacher.email}</p>
                </div>
                <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800">
                  Activo
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
