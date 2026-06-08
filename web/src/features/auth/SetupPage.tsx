import { type FormEvent, useState } from "react";
import { AuthCard, Field, FormError, PrimaryButton } from "../../components/forms";
import { authApi } from "../../lib/api/auth";
import { useAuthStore } from "../../stores/auth";

export function SetupPage({ onDone }: { onDone: () => void }) {
  const setUser = useAuthStore((s) => s.setUser);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const result = await authApi.setup({
        email: String(data.get("email")),
        name: String(data.get("name")),
        password: String(data.get("password")),
      });
      setUser(result.user); // session set via HttpOnly cookie by the hub
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha no setup.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Criar conta de administrador">
      <p className="text-center text-sm text-zinc-500">
        Primeiro acesso ao hub — esta conta gerencia a equipe.
      </p>
      <form onSubmit={handleSubmit} className="space-y-3">
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
        <PrimaryButton disabled={busy}>Criar conta admin</PrimaryButton>
      </form>
    </AuthCard>
  );
}
