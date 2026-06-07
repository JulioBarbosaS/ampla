import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { AuthCard, Field, FormError, PrimaryButton } from "../../components/forms";
import { authApi } from "../../lib/api/auth";
import { authErrorMessage } from "../../lib/api/errors";
import { useAuthStore } from "../../stores/auth";

export function LoginPage() {
  const setAuth = useAuthStore((s) => s.setAuth);
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
      setAuth(result.token, result.user);
    } catch (err) {
      setError(authErrorMessage(err, { unauthorized: "E-mail ou senha incorretos." }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Entrar">
      <form onSubmit={handleSubmit} className="space-y-3">
        <Field label="Email" name="email" type="email" required />
        <Field label="Senha" name="password" type="password" required />
        <FormError message={error} />
        <PrimaryButton disabled={busy}>Entrar</PrimaryButton>
      </form>
      <p className="text-center text-sm text-zinc-500">
        Recebeu um convite?{" "}
        <Link to="/register" className="text-emerald-400 hover:underline">
          Criar conta
        </Link>
      </p>
    </AuthCard>
  );
}
