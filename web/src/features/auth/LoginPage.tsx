import { type FormEvent, type ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import { AuthCard, Field, FormError, PrimaryButton } from "../../components/forms";
import { authApi } from "../../lib/api/auth";
import { authErrorMessage } from "../../lib/api/errors";
import { useAuthStore } from "../../stores/auth";

export function LoginPage() {
  const setUser = useAuthStore((s) => s.setUser);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const result = await authApi.login({
        email: String(data.get("email")),
        password: String(data.get("password")),
      });
      setUser(result.user); // session set via HttpOnly cookie by the hub
    } catch (err) {
      setError(authErrorMessage(err, { unauthorized: "E-mail ou senha incorretos." }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Bem-vindo de volta">
      <form onSubmit={handleSubmit} className="space-y-3">
        <Field label="Email" name="email" type="email" required placeholder="voce@exemplo.com" />
        <Field label="Senha" name="password" type="password" required placeholder="Sua senha" />
        <FormError message={error} />
        <PrimaryButton disabled={busy}>Entrar</PrimaryButton>
      </form>

      {/* Social sign-in and password recovery are placeholders for now — the
       * OAuth providers and the reset flow aren't wired yet. */}
      <div className="mt-4 flex items-center justify-between">
        <div className="flex gap-2">
          <SocialButton label="Continuar com Google (em breve)">
            <GoogleIcon />
          </SocialButton>
          <SocialButton label="Continuar com GitHub (em breve)">
            <GitHubIcon />
          </SocialButton>
        </div>
        <button
          type="button"
          disabled
          title="Recuperação de senha em breve"
          className="text-xs text-zinc-500 underline-offset-2 hover:underline disabled:cursor-not-allowed disabled:no-underline"
        >
          Esqueci minha senha
        </button>
      </div>

      <p className="mt-5 text-center text-xs text-zinc-500">
        Recebeu um convite?{" "}
        <Link to="/register" className="text-amber-400 hover:underline">
          Criar conta
        </Link>
      </p>
    </AuthCard>
  );
}

function SocialButton({ label, children }: { label: string; children: ReactNode }) {
  return (
    <button
      type="button"
      disabled
      aria-label={label}
      title={label}
      className="flex h-9 w-9 items-center justify-center rounded-full border border-zinc-700 text-zinc-400 transition-colors disabled:cursor-not-allowed disabled:opacity-60"
    >
      {children}
    </button>
  );
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z"
      />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
      <path d="M12 .5C5.37.5 0 5.87 0 12.5c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58v-2.03c-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.09-.75.08-.73.08-.73 1.21.09 1.84 1.24 1.84 1.24 1.07 1.84 2.81 1.31 3.5 1 .11-.78.42-1.31.76-1.61-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 6 0c2.29-1.55 3.3-1.23 3.3-1.23.66 1.66.24 2.88.12 3.18.77.84 1.24 1.91 1.24 3.22 0 4.61-2.8 5.62-5.48 5.92.43.37.81 1.1.81 2.22v3.29c0 .32.22.7.83.58A12 12 0 0 0 24 12.5C24 5.87 18.63.5 12 .5z" />
    </svg>
  );
}
