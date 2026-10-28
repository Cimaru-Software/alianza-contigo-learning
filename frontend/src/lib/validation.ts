/**
 * Client-side mirror of backend/app/presentation/validation.py, for immediate feedback.
 * The API remains the authority: it repeats every check and also verifies the email domain's MX records.
 */

const CEDULA_COEFFICIENTS = [2, 1, 2, 1, 2, 1, 2, 1, 2];
const RESERVED_TLDS = new Set(["arpa", "invalid", "local", "localhost", "onion", "test"]);
const DISPOSABLE_DOMAINS = new Set([
  "10minutemail.com",
  "20minutemail.com",
  "discard.email",
  "dispostable.com",
  "emailondeck.com",
  "fakeinbox.com",
  "getnada.com",
  "guerrillamail.com",
  "guerrillamail.net",
  "maildrop.cc",
  "mailinator.com",
  "mailnesia.com",
  "mintemail.com",
  "mohmal.com",
  "sharklasers.com",
  "spamgourmet.com",
  "temp-mail.org",
  "tempail.com",
  "tempmail.com",
  "tempr.email",
  "throwawaymail.com",
  "trashmail.com",
  "yopmail.com",
  "yopmail.net",
]);
const EMAIL_PATTERN =
  /^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$/;
const PHONE_PATTERN = /^\+?[0-9(][0-9 ()-]*[0-9]$/;
const NAME_PATTERN = /^[\p{L}][\p{L} '’.-]*$/u;

/** Registro Civil modulo-10 check digit for a natural person's cédula (provinces 01–24 and 30). */
export function isValidCedula(value: string): boolean {
  if (!/^\d{10}$/.test(value)) return false;
  const digits = [...value].map(Number);
  const province = Number(value.slice(0, 2));
  if (!((province >= 1 && province <= 24) || province === 30) || (digits[2] ?? 9) >= 6)
    return false;
  const total = CEDULA_COEFFICIENTS.reduce((sum, coefficient, index) => {
    const product = (digits[index] ?? 0) * coefficient;
    return sum + (product > 9 ? product - 9 : product);
  }, 0);
  return (10 - (total % 10)) % 10 === digits[9];
}

/** Returns an error message, or null when the address looks real. */
export function emailError(value: string): string | null {
  const email = value.trim();
  if (email.length > 254 || !EMAIL_PATTERN.test(email))
    return "Ingresa un correo electrónico válido.";
  const domain = email.split("@")[1]?.toLowerCase() ?? "";
  if (RESERVED_TLDS.has(domain.split(".").pop() ?? ""))
    return "Ingresa un correo electrónico válido.";
  if (DISPOSABLE_DOMAINS.has(domain)) return "No se permiten correos temporales o desechables.";
  return null;
}

export function personNameError(value: string, label: string): string | null {
  const name = value.trim();
  if (!name) return `${label} es obligatorio.`;
  if (name.length > 100) return `${label} supera los 100 caracteres permitidos.`;
  if (!NAME_PATTERN.test(name))
    return `${label} solo puede contener letras, espacios, apóstrofos y guiones.`;
  return null;
}

export function phoneError(value: string, required = false): string | null {
  const phone = value.trim();
  if (!phone) return required ? "El teléfono es obligatorio." : null;
  const digits = phone.replace(/\D/g, "").length;
  if (!PHONE_PATTERN.test(phone) || digits < 7 || digits > 15)
    return "Ingresa un teléfono válido (7 a 15 dígitos).";
  return null;
}

export function cedulaError(value: string, required = true): string | null {
  const cedula = value.trim();
  if (!cedula) return required ? "La cédula es obligatoria." : null;
  return isValidCedula(cedula) ? null : "La cédula no es válida. Verifica los 10 dígitos.";
}

/** First error among the given checks, or null. */
export function firstError(...errors: Array<string | null>): string | null {
  return errors.find((error) => error !== null) ?? null;
}
