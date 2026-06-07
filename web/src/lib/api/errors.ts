import { ApiError } from "./client";

/**
 * Traduz um erro de chamada à API numa mensagem amigável em pt-BR.
 * `unauthorized` cobre o 401 com sentido específico da tela (no login,
 * "credenciais inválidas"); nas demais o 401 cai na mensagem do hub.
 */
export function authErrorMessage(err: unknown, opts: { unauthorized?: string } = {}): string {
  if (err instanceof ApiError) {
    if (err.status === 401 && opts.unauthorized) return opts.unauthorized;
    if (err.status === 429) return "Muitas tentativas. Aguarde alguns minutos.";
    if (err.status === 403) return "Você não tem permissão para isso.";
  }
  return err instanceof Error ? err.message : "Algo deu errado. Tente de novo.";
}
