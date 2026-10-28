import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  ShieldCheck,
  BookOpenCheck,
  ClipboardCheck,
  UsersRound,
  KeyRound,
  ServerCog,
} from "lucide-react";
import { toast } from "sonner";
import { Logo } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { api, ApiError } from "@/lib/api";
import { cedulaError, emailError, firstError, personNameError, phoneError } from "@/lib/validation";
import { useAuth, type Role } from "@/contexts/AuthContext";
import hero from "@/assets/hero.jpg";

const destinations: Record<Role, string> = {
  admin: "/admin",
  teacher: "/profesor",
  student: "/app",
};

function AuthFrame({
  children,
  title,
  subtitle,
  portal = "Academia",
}: {
  children: ReactNode;
  title: string;
  subtitle: string;
  portal?: string;
}) {
  return (
    <main className="min-h-screen bg-white lg:grid lg:grid-cols-[minmax(360px,0.85fr)_1.15fr]">
      <section className="navy-gradient relative hidden overflow-hidden p-12 text-white lg:flex lg:flex-col">
        <img src={hero} alt="" className="absolute inset-0 h-full w-full object-cover opacity-20" />
        <div className="absolute inset-0 bg-navy/65" />
        <Logo variant="light" className="relative" />
        <div className="relative mt-auto max-w-lg">
          <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-gold text-navy">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <p className="font-display text-4xl font-semibold">Aprende. Crece. Trasciende.</p>
          <p className="mt-4 max-w-md text-white/75">
            Formación profesional con acompañamiento y certificaciones con aval institucional.
          </p>
          <p className="mt-8 text-xs font-medium text-white/55">Acceso seguro · {portal}</p>
        </div>
      </section>
      <section className="flex items-center justify-center px-5 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-10 lg:hidden">
            <Logo />
          </div>
          <h1 className="font-display text-3xl font-semibold text-navy">{title}</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{subtitle}</p>
          {children}
        </div>
      </section>
    </main>
  );
}

function RoleLoginFrame({
  children,
  role,
  title,
  subtitle,
}: {
  children: ReactNode;
  role: Role;
  title: string;
  subtitle: string;
}) {
  if (role === "admin") {
    return (
      <main className="min-h-screen bg-navy px-5 py-6 text-white sm:px-8 lg:grid lg:grid-cols-[minmax(320px,0.72fr)_1.28fr] lg:items-stretch lg:p-8">
        <section className="hidden flex-col justify-between border-r border-white/10 px-8 py-5 lg:flex xl:px-14">
          <Logo variant="light" />
          <div className="max-w-md">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gold text-navy">
              <ServerCog className="h-6 w-6" />
            </div>
            <p className="mt-7 font-display text-4xl font-semibold leading-tight">
              Centro de control institucional
            </p>
            <p className="mt-4 max-w-sm text-sm leading-6 text-white/65">
              Gestión protegida de usuarios, contenidos, matrículas y operación académica.
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs text-white/45">
            <ShieldCheck className="h-4 w-4 text-gold" /> Sesión cifrada y acceso restringido
          </div>
        </section>
        <section className="flex min-h-[calc(100vh-3rem)] items-center justify-center lg:min-h-0">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 text-foreground shadow-[0_8px_24px_oklch(0.08_0.04_260/0.35)] sm:p-10">
            <div className="mb-9 flex items-center justify-between lg:hidden">
              <Logo />
              <span className="rounded-full bg-navy px-3 py-1 text-xs font-medium text-white">
                Admin
              </span>
            </div>
            <div className="mb-6 flex items-center gap-2 text-xs font-medium text-navy">
              <KeyRound className="h-4 w-4 text-gold" /> Acceso privilegiado
            </div>
            <h1 className="font-display text-3xl font-semibold text-navy">{title}</h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{subtitle}</p>
            {children}
          </div>
        </section>
      </main>
    );
  }

  if (role === "teacher") {
    return (
      <main className="min-h-screen bg-slate-100 lg:grid lg:grid-cols-[1.08fr_0.92fr]">
        <section className="flex items-center justify-center px-5 py-10 sm:px-10">
          <div className="w-full max-w-md">
            <Logo />
            <div className="mt-14 inline-flex items-center gap-2 rounded-full bg-navy px-3 py-1.5 text-xs font-medium text-white">
              <BookOpenCheck className="h-4 w-4 text-gold" /> Portal docente
            </div>
            <h1 className="mt-6 font-display text-4xl font-semibold text-navy">{title}</h1>
            <p className="mt-3 max-w-sm text-sm leading-6 text-muted-foreground">{subtitle}</p>
            {children}
          </div>
        </section>
        <section className="navy-gradient relative hidden overflow-hidden p-12 text-white lg:flex lg:flex-col">
          <div className="absolute right-0 top-0 h-56 w-56 rounded-bl-full bg-gold/10" />
          <div className="relative mt-auto mb-auto max-w-md">
            <p className="text-sm font-medium text-gold">Tu espacio académico</p>
            <h2 className="mt-3 font-display text-3xl font-semibold">
              Enseña, acompaña y evalúa desde un solo lugar.
            </h2>
            <div className="mt-10 space-y-4">
              {(
                [
                  [ClipboardCheck, "Revisa evaluaciones y entrega retroalimentación"],
                  [UsersRound, "Consulta el avance de tus grupos"],
                  [BookOpenCheck, "Personaliza el contenido de tus Programas"],
                ] as const
              ).map(([Icon, text]) => (
                <div
                  key={String(text)}
                  className="flex items-center gap-4 border-b border-white/10 pb-4"
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10">
                    <Icon className="h-4 w-4 text-gold" />
                  </span>
                  <p className="text-sm text-white/80">{String(text)}</p>
                </div>
              ))}
            </div>
          </div>
          <p className="relative text-xs text-white/45">Acceso exclusivo para personal docente</p>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-white lg:grid lg:grid-cols-[0.9fr_1.1fr]">
      <section className="relative hidden overflow-hidden lg:block">
        <img
          src={hero}
          alt="Estudiante aprendiendo en línea"
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-navy via-navy/55 to-navy/10" />
        <div className="relative flex h-full flex-col justify-between p-12 text-white">
          <Logo variant="light" />
          <div className="max-w-lg">
            <p className="font-display text-5xl font-semibold leading-[1.08]">
              Tu próxima meta comienza aquí.
            </p>
            <p className="mt-5 max-w-md text-base leading-7 text-white/78">
              Retoma tus clases, revisa tu progreso y avanza hacia una certificación que impulse tu
              perfil.
            </p>
          </div>
        </div>
      </section>
      <section className="flex items-center justify-center px-5 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-12 lg:hidden">
            <Logo />
          </div>
          <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-accent text-gold">
            <BookOpenCheck className="h-5 w-5" />
          </div>
          <h1 className="font-display text-3xl font-semibold text-navy">{title}</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{subtitle}</p>
          {children}
        </div>
      </section>
    </main>
  );
}

function PasswordInput({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <LockKeyhole className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        id={id}
        type={show ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required
        minLength={8}
        className="h-11 px-10"
      />
      <button
        type="button"
        onClick={() => setShow(!show)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground"
        aria-label={show ? "Ocultar contraseña" : "Mostrar contraseña"}
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

export function LoginPage({ role = "student" }: { role?: Role }) {
  const navigate = useNavigate();
  const { user, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  if (user) return <Navigate to={destinations[user.role]} replace />;
  const copy: readonly [string, string, string] =
    role === "admin"
      ? [
          "Acceso administrativo",
          "Gestiona usuarios, programas y operación de la academia.",
          "Administración",
        ]
      : role === "teacher"
        ? ["Portal de profesores", "Ingresa con la cuenta asignada por administración.", "Docentes"]
        : ["Bienvenido de nuevo", "Ingresa tus datos para continuar aprendiendo.", "Academia"];
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const logged = await login(email, password, role);
      navigate(destinations[logged.role], { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No pudimos iniciar sesión.");
    } finally {
      setLoading(false);
    }
  }
  return (
    <RoleLoginFrame role={role} title={copy[0]} subtitle={copy[1]}>
      <form onSubmit={submit} className="mt-8 space-y-5">
        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <div className="space-y-2">
          <Label htmlFor={`${role}-email`}>Correo electrónico</Label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id={`${role}-email`}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="nombre@correo.com"
              className="h-11 pl-10"
            />
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor={`${role}-password`}>Contraseña</Label>
          <PasswordInput id={`${role}-password`} value={password} onChange={setPassword} />
        </div>
        <div className="flex items-center justify-between text-sm">
          <label className="flex items-center gap-2">
            <Checkbox /> Recordarme
          </label>
          <Link to="/olvide-mi-contrasena" className="font-medium text-navy hover:text-gold">
            ¿Olvidaste tu contraseña?
          </Link>
        </div>
        <Button
          type="submit"
          variant={role === "teacher" ? "navy" : "gold"}
          size="lg"
          className="w-full"
          disabled={loading}
        >
          {loading ? "Verificando..." : "Iniciar sesión"}
        </Button>
        {role === "student" ? (
          <p className="text-center text-sm text-muted-foreground">
            ¿Aún no tienes cuenta?{" "}
            <Link to="/register" className="font-semibold text-navy">
              Crear cuenta
            </Link>
          </p>
        ) : (
          <p className="text-center text-xs leading-5 text-muted-foreground">
            Las cuentas de{" "}
            {role === "teacher"
              ? "profesores son creadas por administración"
              : "administración son de acceso restringido"}
            .
          </p>
        )}
        <Link
          to="/"
          className="mx-auto flex w-fit items-center gap-2 text-sm text-muted-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Volver al sitio
        </Link>
      </form>
    </RoleLoginFrame>
  );
}

type RegisterField = "firstName" | "lastName" | "nationalId" | "phone" | "email";
const registerFields: Array<{
  label: string;
  key: RegisterField;
  type: string;
  maxLength: number;
  inputMode?: "text" | "numeric" | "tel" | "email";
  autoComplete: string;
}> = [
  { label: "Nombres", key: "firstName", type: "text", maxLength: 100, autoComplete: "given-name" },
  {
    label: "Apellidos",
    key: "lastName",
    type: "text",
    maxLength: 100,
    autoComplete: "family-name",
  },
  {
    label: "Cédula",
    key: "nationalId",
    type: "text",
    maxLength: 10,
    inputMode: "numeric",
    autoComplete: "off",
  },
  {
    label: "Teléfono",
    key: "phone",
    type: "tel",
    maxLength: 30,
    inputMode: "tel",
    autoComplete: "tel",
  },
  {
    label: "Correo electrónico",
    key: "email",
    type: "email",
    maxLength: 254,
    inputMode: "email",
    autoComplete: "email",
  },
];

export function RegisterPage() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    firstName: "",
    lastName: "",
    nationalId: "",
    phone: "",
    email: "",
    password: "",
    confirmation: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [touched, setTouched] = useState<Partial<Record<RegisterField, boolean>>>({});
  if (user) return <Navigate to={destinations[user.role]} replace />;
  const fieldErrors: Record<RegisterField, string | null> = {
    firstName: personNameError(form.firstName, "El nombre"),
    lastName: personNameError(form.lastName, "El apellido"),
    nationalId: cedulaError(form.nationalId),
    phone: phoneError(form.phone, true),
    email: emailError(form.email),
  };
  async function submit(e: FormEvent) {
    e.preventDefault();
    const invalid = firstError(...registerFields.map((field) => fieldErrors[field.key]));
    if (invalid) {
      setTouched(Object.fromEntries(registerFields.map((field) => [field.key, true])));
      return setError(invalid);
    }
    if (form.password !== form.confirmation) return setError("Las contraseñas no coinciden.");
    setError("");
    setLoading(true);
    try {
      await register(form);
      navigate("/app", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No pudimos crear tu cuenta.");
    } finally {
      setLoading(false);
    }
  }
  return (
    <AuthFrame
      title="Crea tu cuenta"
      subtitle="Regístrate para acceder a tus programas y certificados."
    >
      <form onSubmit={submit} className="mt-8 grid gap-4 sm:grid-cols-2">
        {error && (
          <Alert variant="destructive" className="sm:col-span-2">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {registerFields.map(({ label, key, type, maxLength, inputMode, autoComplete }) => {
          const fieldError = touched[key] ? fieldErrors[key] : null;
          return (
            <div key={key} className={`space-y-2 ${key === "email" ? "sm:col-span-2" : ""}`}>
              <Label htmlFor={key}>{label}</Label>
              <Input
                id={key}
                type={type}
                inputMode={inputMode}
                autoComplete={autoComplete}
                maxLength={maxLength}
                value={form[key]}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                onBlur={() => setTouched((current) => ({ ...current, [key]: true }))}
                aria-invalid={Boolean(fieldError)}
                aria-describedby={fieldError ? `${key}-error` : undefined}
                required
                className="h-11"
              />
              {fieldError && (
                <p id={`${key}-error`} className="text-xs text-destructive">
                  {fieldError}
                </p>
              )}
            </div>
          );
        })}
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="register-password">Contraseña</Label>
          <PasswordInput
            id="register-password"
            value={form.password}
            onChange={(password) => setForm({ ...form, password })}
          />
          <p className="text-xs text-muted-foreground">
            Mínimo 8 caracteres, una letra y un número.
          </p>
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="confirmation">Confirmar contraseña</Label>
          <PasswordInput
            id="confirmation"
            value={form.confirmation}
            onChange={(confirmation) => setForm({ ...form, confirmation })}
          />
        </div>
        <label className="flex items-start gap-2 text-sm text-muted-foreground sm:col-span-2">
          <Checkbox required className="mt-0.5" /> Acepto los términos y condiciones y la política
          de privacidad.
        </label>
        <Button type="submit" variant="gold" size="lg" className="sm:col-span-2" disabled={loading}>
          {loading ? "Creando cuenta..." : "Crear mi cuenta"}
        </Button>
        <p className="text-center text-sm text-muted-foreground sm:col-span-2">
          ¿Ya tienes cuenta?{" "}
          <Link to="/login" className="font-semibold text-navy">
            Iniciar sesión
          </Link>
        </p>
      </form>
    </AuthFrame>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await api("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
      setSent(true);
    } catch {
      toast.error("No se pudo procesar la solicitud.");
    } finally {
      setLoading(false);
    }
  }
  return (
    <AuthFrame
      title="Recupera tu acceso"
      subtitle="Te enviaremos un enlace seguro para crear una nueva contraseña."
    >
      {sent ? (
        <div className="mt-8 rounded-xl bg-emerald-50 p-5 text-emerald-900">
          <CheckCircle2 className="h-6 w-6" />
          <h2 className="mt-3 font-semibold">Revisa tu correo</h2>
          <p className="mt-1 text-sm leading-6">
            Si existe una cuenta asociada, recibirás el enlace en unos minutos.
          </p>
        </div>
      ) : (
        <form onSubmit={submit} className="mt-8 space-y-5">
          <div className="space-y-2">
            <Label htmlFor="reset-email">Correo electrónico</Label>
            <Input
              id="reset-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="h-11"
            />
          </div>
          <Button type="submit" variant="gold" size="lg" className="w-full" disabled={loading}>
            {loading ? "Enviando..." : "Enviar enlace"}
          </Button>
        </form>
      )}
      <Link to="/login" className="mt-6 flex items-center gap-2 text-sm font-medium text-navy">
        <ArrowLeft className="h-4 w-4" /> Volver al inicio de sesión
      </Link>
    </AuthFrame>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (password !== confirmation) return setError("Las contraseñas no coinciden.");
    setLoading(true);
    try {
      await api("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token: params.get("token"), password }),
      });
      toast.success("Contraseña actualizada.");
      navigate("/login");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No pudimos actualizarla.");
    } finally {
      setLoading(false);
    }
  }
  return (
    <AuthFrame title="Nueva contraseña" subtitle="Elige una contraseña segura.">
      <form onSubmit={submit} className="mt-8 space-y-5">
        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <div className="space-y-2">
          <Label>Nueva contraseña</Label>
          <PasswordInput id="new-password" value={password} onChange={setPassword} />
        </div>
        <div className="space-y-2">
          <Label>Confirmar contraseña</Label>
          <PasswordInput id="reset-confirmation" value={confirmation} onChange={setConfirmation} />
        </div>
        <Button type="submit" variant="gold" size="lg" className="w-full" disabled={loading}>
          {loading ? "Actualizando..." : "Guardar contraseña"}
        </Button>
      </form>
    </AuthFrame>
  );
}
