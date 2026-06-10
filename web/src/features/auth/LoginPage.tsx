import { type FormEvent, useState } from "react";
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

      {/* Password recovery is a placeholder for now — the reset flow isn't wired yet. */}
      <div className="mt-3 text-right">
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
