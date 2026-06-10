import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AuthCard, Field, FormError, PrimaryButton } from "../../components/forms";
import { authApi } from "../../lib/api/auth";
import { authErrorMessage } from "../../lib/api/errors";

/** Public page reached from an admin-issued reset link (`/reset?token=…`).
 * No email is sent — the admin hands the link over out-of-band. */
export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const password = String(data.get("password"));
    const confirm = String(data.get("confirm"));
    if (password.length < 10) {
      setError("A senha precisa de pelo menos 10 caracteres.");
      return;
    }
    if (password !== confirm) {
      setError("A confirmação não confere com a nova senha.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await authApi.resetPassword({ token, new_password: password });
      setDone(true);
    } catch (err) {
      setError(authErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <AuthCard title="Senha redefinida">
        <p className="text-center text-sm text-zinc-400">
          Sua senha foi redefinida.{" "}
          <Link to="/" className="text-amber-400 hover:underline">
            Entrar
          </Link>
        </p>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Redefinir senha">
      {token ? (
        <form onSubmit={handleSubmit} className="space-y-3">
          <Field
            label="Nova senha (mínimo 10)"
            name="password"
            type="password"
            required
            minLength={10}
          />
          <Field label="Confirmar nova senha" name="confirm" type="password" required />
          <FormError message={error} />
          <PrimaryButton disabled={busy}>Redefinir senha</PrimaryButton>
        </form>
      ) : (
        <p className="text-center text-sm text-zinc-400">
          Link inválido. Peça um novo link de redefinição ao administrador.
        </p>
      )}
      <p className="mt-4 text-center text-xs text-zinc-500">
        <Link to="/" className="text-amber-400 hover:underline">
          Voltar ao login
        </Link>
      </p>
    </AuthCard>
  );
}
