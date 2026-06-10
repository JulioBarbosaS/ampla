import { type ChangeEvent, useRef, useState } from "react";
import { Avatar } from "../../components/Avatar";
import { AvatarCropper } from "../../components/AvatarCropper";
import { readFileAsDataUrl, validateImageFile } from "../../lib/crop";
import { useAuthStore } from "../../stores/auth";
import { useAvatarStore } from "../../stores/avatar";

const fieldClass =
  "w-full rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-sm text-zinc-300 disabled:cursor-not-allowed";

/** Profile page (reached from the account drawer → "Perfil"). The photo is
 * editable now (cropped, kept client-side); name/email/role stay read-only
 * until the profile-update endpoints land. */
export function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const photo = useAvatarStore((s) => (user ? (s.photos[user.id] ?? null) : null));
  const setPhoto = useAvatarStore((s) => s.setPhoto);
  const removePhoto = useAvatarStore((s) => s.removePhoto);
  const inputRef = useRef<HTMLInputElement>(null);
  const [cropping, setCropping] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
              {photo ? "Trocar foto" : "Adicionar foto"}
            </button>
            {photo && user && (
              <button
                type="button"
                onClick={() => removePhoto(user.id)}
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

      <section className="mt-4 rounded-lg border border-zinc-800 p-4">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">Dados</h2>
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs text-zinc-500">Nome</span>
            <input value={user?.name ?? ""} disabled className={fieldClass} />
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
        <p className="mt-3 text-xs text-zinc-600">A edição de nome e email chega em breve.</p>
      </section>

      {cropping && user && (
        <AvatarCropper
          image={cropping}
          onCancel={() => setCropping(null)}
          onSave={(dataUrl) => {
            setPhoto(user.id, dataUrl);
            setCropping(null);
          }}
        />
      )}
    </div>
  );
}
