import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AuthCard, Field, FormError, PrimaryButton } from "../../components/forms";
import { authApi } from "../../lib/api/auth";
import { authErrorMessage } from "../../lib/api/errors";
import { useAuthStore } from "../../stores/auth";

export function RegisterPage() {
  const setAuth = useAuthStore((s) => s.setAuth);
  const [params] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const result = await authApi.register({
        invite_code: String(data.get("invite_code")).trim().toUpperCase(),
        email: String(data.get("email")),
        name: String(data.get("name")),
        password: String(data.get("password")),
      });
      setAuth(result.token, result.user);
    } catch (err) {
      setError(authErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Criar conta com convite">
      <form onSubmit={handleSubmit} className="space-y-3">
        <Field
          label="Código de convite"
          name="invite_code"
          required
          defaultValue={params.get("code") ?? ""}
          placeholder="AMP-XXXX-XXXX-XXXX-XXXX"
        />
        <Field label="Nome" name="name" required maxLength={120} />
        <Field label="Email" name="email" type="email" required />
        <Field
          label="Senha (mínimo 10 caracteres)"
          name="password"
          type="password"
          required
          minLength={10}
        />
        <FormError message={error} />
        <PrimaryButton disabled={busy}>Criar conta</PrimaryButton>
      </form>
      <p className="text-center text-sm text-zinc-500">
        Já tem conta?{" "}
        <Link to="/" className="text-emerald-400 hover:underline">
          Entrar
        </Link>
      </p>
    </AuthCard>
  );
}
