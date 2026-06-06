import { type FormEvent, useEffect, useState } from "react";
import { FormError } from "../../components/forms";
import { agentsApi } from "../../lib/api/agents";
import type { Agent, AgentKey } from "../../lib/api/types";

export function AgentCard({ agent, onChanged }: { agent: Agent; onChanged: () => void }) {
  const [keys, setKeys] = useState<AgentKey[]>([]);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    agentsApi.listKeys(agent.slug).then(setKeys).catch(() => {});
  }, [agent.slug]);

  async function handleSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const allowRaw = String(data.get("allowed_senders") ?? "").trim();
    const allowList = allowRaw
      ? allowRaw.split(",").map((s) => s.trim()).filter(Boolean)
      : [];
    setError(null);
    setSaved(false);
    try {
      await agentsApi.updateSettings(agent.slug, {
        mode: data.get("mode") === "auto" ? "auto" : "inbox",
        ...(allowList.length > 0
          ? { allowed_senders: allowList }
          : { clear_allowed_senders: true }),
        max_auto_per_hour: Number(data.get("max_auto_per_hour")),
        auto_timeout_secs: Number(data.get("auto_timeout_secs")),
        instructions: String(data.get("instructions") ?? ""),
      });
      setSaved(true);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar.");
    }
  }

  async function handleCreateKey() {
    setError(null);
    try {
      const created = await agentsApi.createKey(agent.slug);
      setNewKey(created.key);
      setKeys(await agentsApi.listKeys(agent.slug));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao gerar chave.");
    }
  }

  async function handleRevoke(keyId: number) {
    setError(null);
    try {
      await agentsApi.revokeKey(agent.slug, keyId);
      setKeys(await agentsApi.listKeys(agent.slug));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao revogar.");
    }
  }

  const inputClass =
    "w-full rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-sm outline-none focus:border-emerald-500";

  return (
    <section className="rounded-lg border border-zinc-800 p-4">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="font-mono text-sm font-semibold text-emerald-300">{agent.slug}</h3>
          <p className="text-xs text-zinc-500">{agent.display_name}</p>
        </div>
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            agent.mode === "auto"
              ? "bg-amber-900/50 text-amber-300"
              : "bg-zinc-800 text-zinc-400"
          }`}
        >
          {agent.mode === "auto" ? "auto-respond" : "inbox"}
        </span>
      </header>

      <form onSubmit={handleSettings} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">
            <span className="mb-1 block text-zinc-400">Modo de resposta</span>
            <select name="mode" defaultValue={agent.mode} className={inputClass}>
              <option value="inbox">inbox — só enfileira para mim</option>
              <option value="auto">auto — Claude responde sozinho</option>
            </select>
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-zinc-400">Quem pode enviar (vazio = todos)</span>
            <input
              name="allowed_senders"
              defaultValue={agent.allowed_senders?.join(", ") ?? ""}
              placeholder="mobile-eduardo, frontend-joao"
              className={inputClass}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-zinc-400">Máx. respostas auto/hora</span>
            <input
              name="max_auto_per_hour"
              type="number"
              min={1}
              max={120}
              defaultValue={agent.max_auto_per_hour}
              className={inputClass}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-zinc-400">Timeout da resposta (s)</span>
            <input
              name="auto_timeout_secs"
              type="number"
              min={10}
              max={600}
              defaultValue={agent.auto_timeout_secs}
              className={inputClass}
            />
          </label>
        </div>
        <label className="block text-sm">
          <span className="mb-1 block text-zinc-400">Instruções do agente (auto-respond)</span>
          <textarea
            name="instructions"
            defaultValue={agent.instructions}
            rows={2}
            maxLength={4000}
            placeholder="ex: responda apenas sobre o repositório backend; nunca discuta infraestrutura"
            className={inputClass}
          />
        </label>
        <div className="flex items-center gap-3">
          <button
            type="submit"
            className="rounded-md bg-zinc-800 px-3 py-1.5 text-sm font-medium text-zinc-200 hover:bg-zinc-700"
          >
            Salvar regras
          </button>
          {saved && <span className="text-xs text-emerald-400">salvo ✓</span>}
        </div>
        <FormError message={error} />
      </form>

      <div className="mt-4 border-t border-zinc-800 pt-3">
        <div className="mb-2 flex items-center justify-between">
          <h4 className="text-sm font-medium text-zinc-300">Chaves do daemon</h4>
          <button
            onClick={handleCreateKey}
            className="rounded-md bg-zinc-800 px-2.5 py-1 text-xs font-medium text-zinc-200 hover:bg-zinc-700"
          >
            Gerar chave
          </button>
        </div>
        {newKey && (
          <div className="mb-2 rounded-md bg-amber-950/40 px-3 py-2">
            <p className="text-xs text-amber-300">
              Copie agora — esta chave não será exibida novamente:
            </p>
            <p className="break-all font-mono text-xs text-amber-200">{newKey}</p>
          </div>
        )}
        <ul className="space-y-1">
          {keys.map((key) => (
            <li
              key={key.id}
              className="flex items-center justify-between rounded-md bg-zinc-900 px-3 py-1.5 text-xs"
            >
              <span className="text-zinc-400">
                #{key.id} {key.label && `· ${key.label} `}· criada em{" "}
                {new Date(key.created_at).toLocaleDateString("pt-BR")}
                {key.revoked_at && (
                  <span className="ml-1.5 text-red-400">revogada</span>
                )}
              </span>
              {!key.revoked_at && (
                <button
                  onClick={() => handleRevoke(key.id)}
                  className="text-red-400 hover:text-red-300"
                >
                  Revogar
                </button>
              )}
            </li>
          ))}
          {keys.length === 0 && (
            <li className="text-xs text-zinc-500">
              Nenhuma chave — gere uma para conectar o daemon desta máquina.
            </li>
          )}
        </ul>
      </div>
    </section>
  );
}
