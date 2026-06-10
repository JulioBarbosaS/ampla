import { type ChangeEvent, type FormEvent, useRef, useState } from "react";
import { Avatar } from "../../components/Avatar";
import { AvatarCropper } from "../../components/AvatarCropper";
import { authApi } from "../../lib/api/auth";
import { authErrorMessage } from "../../lib/api/errors";
import { readFileAsDataUrl, validateImageFile } from "../../lib/crop";
import { useAuthStore } from "../../stores/auth";
import { useAvatarStore } from "../../stores/avatar";

const fieldClass =
  "w-full rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-sm text-zinc-300 disabled:cursor-not-allowed";
const inputClass =
  "w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 outline-none transition-colors focus:border-amber-500";

/** Profile page (reached from the account drawer → "Perfil"). Name and photo are
 * editable; email/role stay read-only. */
export function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const present = useAvatarStore((s) => (user ? (s.present[user.id] ?? false) : false));
  const bump = useAvatarStore((s) => s.bump);
  const inputRef = useRef<HTMLInputElement>(null);
  const [cropping, setCropping] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState(user?.name ?? "");
  const [savingName, setSavingName] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [nameSaved, setNameSaved] = useState(false);
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwSaved, setPwSaved] = useState(false);

  const trimmedName = name.trim();
  const nameDirty = trimmedName !== (user?.name ?? "") && trimmedName.length > 0;

  async function handleSaveName(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!nameDirty) return;
    setSavingName(true);
    setNameError(null);
    setNameSaved(false);
    try {
      const updated = await authApi.updateProfile({ name: trimmedName });
      setUser(updated);
      setNameSaved(true);
    } catch (err) {
      setNameError(authErrorMessage(err));
    } finally {
      setSavingName(false);
    }
  }

  async function handleChangePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPwError(null);
    setPwSaved(false);
    if (newPw.length < 10) {
      setPwError("A nova senha precisa de pelo menos 10 caracteres.");
      return;
    }
    if (newPw !== confirmPw) {
      setPwError("A confirmação não confere com a nova senha.");
      return;
    }
    setPwBusy(true);
    try {
      await authApi.changePassword({ current_password: currentPw, new_password: newPw });
      setPwSaved(true);
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
    } catch (err) {
      setPwError(authErrorMessage(err));
    } finally {
      setPwBusy(false);
    }
  }

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow re-picking the same file
    if (!file) return;
    const invalid = validateImageFile(file);
    if (invalid) {
      setError(invalid);
      return;
    }
    setError(null);
    try {
      setCropping(await readFileAsDataUrl(file));
    } catch {
      setError("Falha ao ler o arquivo.");
    }
  }

  return (
    <div className="mx-auto max-w-lg p-6">
      <h1 className="mb-4 text-lg font-semibold text-zinc-100">Perfil</h1>

      <section className="rounded-lg border border-zinc-800 p-4">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">Foto</h2>
        <div className="flex items-center gap-4">
          <Avatar user={user} sizeClass="h-20 w-20" textClass="text-2xl" alt="Foto de perfil" />
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-200 transition-colors hover:bg-zinc-800"
            >
              {present ? "Trocar foto" : "Adicionar foto"}
            </button>
            {present && user && (
              <button
                type="button"
                onClick={async () => {
                  setError(null);
                  try {
                    await authApi.removeAvatar();
                    bump(user.id);
                  } catch (err) {
                    setError(authErrorMessage(err));
                  }
                }}
                className="rounded-md px-3 py-1.5 text-sm text-red-400 transition-colors hover:bg-red-950/40"
              >
                Remover foto
              </button>
            )}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            onChange={handleFile}
            className="hidden"
            aria-label="Selecionar foto"
          />
        </div>
        {error && (
          <p role="alert" className="mt-2 text-xs text-red-400">
            {error}
          </p>
        )}
      </section>

      <form onSubmit={handleSaveName} className="mt-4 rounded-lg border border-zinc-800 p-4">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">Dados</h2>
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs text-zinc-500">Nome</span>
            <input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setNameSaved(false);
              }}
              maxLength={120}
              aria-label="Nome"
              className={inputClass}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-zinc-500">Email</span>
            <input value={user?.email ?? ""} disabled className={fieldClass} />
          </label>
          <div>
            <span className="mb-1 block text-xs text-zinc-500">Papel</span>
            <span className="inline-block rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300">
              {user?.role}
            </span>
          </div>
        </div>
        {nameError && (
          <p role="alert" className="mt-2 text-xs text-red-400">
            {nameError}
          </p>
        )}
        <div className="mt-3 flex items-center gap-3">
          <button
            type="submit"
            disabled={!nameDirty || savingName}
            className="rounded-md bg-amber-500 px-3 py-1.5 text-sm font-semibold text-black transition-colors hover:bg-amber-400 disabled:opacity-50"
          >
            Salvar
          </button>
          {nameSaved && <span className="text-xs text-emerald-400">Salvo.</span>}
        </div>
        <p className="mt-2 text-xs text-zinc-600">A edição de email chega em breve.</p>
      </form>

      <form onSubmit={handleChangePassword} className="mt-4 rounded-lg border border-zinc-800 p-4">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">Senha</h2>
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs text-zinc-500">Senha atual</span>
            <input
              type="password"
              autoComplete="current-password"
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              aria-label="Senha atual"
              className={inputClass}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-zinc-500">Nova senha (mínimo 10)</span>
            <input
              type="password"
              autoComplete="new-password"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              aria-label="Nova senha"
              className={inputClass}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-zinc-500">Confirmar nova senha</span>
            <input
              type="password"
              autoComplete="new-password"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              aria-label="Confirmar nova senha"
              className={inputClass}
            />
          </label>
        </div>
        {pwError && (
          <p role="alert" className="mt-2 text-xs text-red-400">
            {pwError}
          </p>
        )}
        <div className="mt-3 flex items-center gap-3">
          <button
            type="submit"
            disabled={pwBusy || !currentPw || !newPw || !confirmPw}
            className="rounded-md bg-amber-500 px-3 py-1.5 text-sm font-semibold text-black transition-colors hover:bg-amber-400 disabled:opacity-50"
          >
            Alterar senha
          </button>
          {pwSaved && <span className="text-xs text-emerald-400">Senha alterada.</span>}
        </div>
      </form>

      {cropping && user && (
        <AvatarCropper
          image={cropping}
          onCancel={() => setCropping(null)}
          onSave={async (dataUrl) => {
            setError(null);
            try {
              await authApi.setAvatar(dataUrl);
              bump(user.id);
            } catch (err) {
              setError(authErrorMessage(err));
            } finally {
              setCropping(null);
            }
          }}
        />
      )}
    </div>
  );
}
