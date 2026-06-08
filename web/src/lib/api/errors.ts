import { ApiError } from "./client";

/**
 * Maps an API call error to a friendly pt-BR message.
 * `unauthorized` covers the 401 with a screen-specific meaning (on login,
 * "invalid credentials"); elsewhere the 401 falls back to the hub message.
 */
export function authErrorMessage(err: unknown, opts: { unauthorized?: string } = {}): string {
  if (err instanceof ApiError) {
    if (err.status === 401 && opts.unauthorized) return opts.unauthorized;
    if (err.status === 429) return "Muitas tentativas. Aguarde alguns minutos.";
    if (err.status === 403) return "Você não tem permissão para isso.";
  }
  return err instanceof Error ? err.message : "Algo deu errado. Tente de novo.";
}
