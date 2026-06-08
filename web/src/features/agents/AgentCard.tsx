import { type FormEvent, useEffect, useState } from "react";
import { FormError } from "../../components/forms";
import { agentsApi, type SettingsPatch } from "../../lib/api/agents";
import { wsUrl } from "../../lib/api/client";
import { groupsApi } from "../../lib/api/groups";
import type { Agent, AgentKey, Group } from "../../lib/api/types";
import { connectToken } from "../../lib/connect";
import { PresenceDot } from "../chat/Sidebar";

const dangerBtn =
  "rounded-md border border-red-700 px-2.5 py-1 text-xs font-medium text-red-300 hover:bg-red-950/40";

/** A high-risk action gated behind three confirmations (warn → reconfirm →
 * type the agent slug), GitHub danger-zone style. */
function DangerAction({
  trigger,
  warning,
  confirmWord,
  onConfirm,
}: {
  trigger: string;
  warning: string;
  confirmWord: string;
  onConfirm: () => void;
}) {
  const [step, setStep] = useState<0 | 1 | 2 | 3>(0);
  const [typed, setTyped] = useState("");
  const reset = () => {
    setStep(0);
    setTyped("");
  };

  if (step === 0) {
    return (
      <button type="button" onClick={() => setStep(1)} className={dangerBtn}>
        {trigger}
      </button>
    );
  }

  const cancel = (
    <button
      type="button"
      onClick={reset}
      className="rounded-md bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
    >
      Cancelar
    </button>
  );

  return (
    <div className="space-y-2 rounded-md border border-red-800 bg-red-950/40 p-2.5 text-xs">
      <p className="text-red-200">{warning}</p>
      {step === 1 && (
        <div className="flex gap-2">
          {cancel}
          <button type="button" onClick={() => setStep(2)} className={dangerBtn}>
            Entendo o risco
          </button>
        </div>
      )}
      {step === 2 && (
        <div className="flex gap-2">
          {cancel}
          <button type="button" onClick={() => setStep(3)} className={dangerBtn}>
            Confirmar de novo
          </button>
        </div>
      )}
      {step === 3 && (
        <div className="space-y-1.5">
          <p className="text-red-200">
            Digite <span className="font-mono font-semibold">{confirmWord}</span> para aplicar:
          </p>
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={confirmWord}
            className="w-full rounded-md border border-red-700 bg-zinc-900 px-2.5 py-1.5 text-sm outline-none focus:border-red-500"
          />
          <div className="flex gap-2">
            {cancel}
            <button
              type="button"
              disabled={typed !== confirmWord}
              onClick={() => {
                onConfirm();
                reset();
              }}
              className={`${dangerBtn} disabled:cursor-not-allowed disabled:opacity-40`}
            >
              Aplicar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function AgentCard({
  agent,
  online,
  groups = [],
  onChanged,
  onGroupsChanged,
}: {
  agent: Agent;
  online?: boolean;
  groups?: Group[];
  onChanged: () => void;
  onGroupsChanged?: () => void;
}) {
  const [keys, setKeys] = useState<AgentKey[]>([]);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [trustInput, setTrustInput] = useState("");

  useEffect(() => {
    agentsApi
      .listKeys(agent.slug)
      .then(setKeys)
      .catch(() => {});
  }, [agent.slug]);

  async function handleSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const allowRaw = String(data.get("allowed_senders") ?? "").trim();
    const allowList = allowRaw
      ? allowRaw
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      : [];
    const deniedRaw = String(data.get("denied_paths") ?? "").trim();
    const deniedList = deniedRaw
      ? deniedRaw
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
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
        // sensitive-paths block and trusted senders live in the danger zone below
        allow_write: data.get("allow_write") === "on",
        block_hidden_files: data.get("block_hidden_files") === "on",
        confine_to_dir: data.get("confine_to_dir") === "on",
        denied_paths: deniedList,
      });
      setSaved(true);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar.");
    }
  }

  // Danger-zone fields are patched directly (outside the main form), each one
  // behind a triple confirmation in the UI below.
  async function patchDanger(patch: SettingsPatch) {
    setError(null);
    try {
      await agentsApi.updateSettings(agent.slug, patch);
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

  async function toggleGroup(group: Group, isMember: boolean) {
    setError(null);
    try {
      if (isMember) await groupsApi.removeMember(group.slug, agent.slug);
      else await groupsApi.addMember(group.slug, agent.slug);
      onGroupsChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar grupos.");
    }
  }

  const connectSnippet = `# ~/.amp/config.json
{
  "hub_url": "${wsUrl()}",
  "agent_id": "${agent.slug}",
  "agent_key": "amp_COLE_SUA_CHAVE_AQUI"
}

pnpm daemon   # deixe rodando`;

  const inputClass =
    "w-full rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-sm outline-none focus:border-emerald-500";

  return (
    <section className="rounded-lg border border-zinc-800 p-4">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="font-mono text-sm font-semibold text-emerald-300">{agent.slug}</h3>
          <p className="text-xs text-zinc-500">{agent.display_name}</p>
        </div>
        <div className="flex items-center gap-2.5">
          <span className="flex items-center gap-1.5 text-xs text-zinc-400" title="presença">
            <PresenceDot online={!!online} />
            {online ? "online" : "offline"}
          </span>
          <span
            className={`rounded px-2 py-0.5 text-xs font-medium ${
              agent.mode === "auto" ? "bg-amber-900/50 text-amber-300" : "bg-zinc-800 text-zinc-400"
            }`}
          >
            {agent.mode === "auto" ? "auto-respond" : "inbox"}
          </span>
        </div>
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
        <fieldset className="space-y-2 rounded-md border border-zinc-800 p-2.5">
          <legend className="px-1 text-xs text-zinc-500">
            Restrições de arquivo (auto-respond)
          </legend>
          <label className="flex items-center gap-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              name="block_hidden_files"
              defaultChecked={agent.block_hidden_files}
              className="accent-emerald-500"
            />
            Bloquear arquivos ocultos (.env, .gitignore, dotfiles)
          </label>
          <label className="flex items-center gap-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              name="confine_to_dir"
              defaultChecked={agent.confine_to_dir}
              className="accent-emerald-500"
            />
            Confinar ao diretório do projeto (bloqueia /etc, /var, /tmp…)
          </label>
          <label className="flex items-center gap-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              name="allow_write"
              defaultChecked={agent.allow_write}
              className="accent-emerald-500"
            />
            Permitir escrita (Edit/Write) — o padrão é só leitura
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-zinc-400">
              Caminhos negados (separados por vírgula)
            </span>
            <input
              name="denied_paths"
              defaultValue={agent.denied_paths.join(", ")}
              placeholder="secrets.txt, *.pem, config/prod.json"
              className={inputClass}
            />
          </label>
        </fieldset>
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
            type="button"
            onClick={handleCreateKey}
            className="rounded-md bg-zinc-800 px-2.5 py-1 text-xs font-medium text-zinc-200 hover:bg-zinc-700"
          >
            Gerar chave
          </button>
        </div>
        {newKey && (
          <div className="mb-2 space-y-2 rounded-md bg-amber-950/40 px-3 py-2">
            <div>
              <p className="text-xs text-amber-300">
                Copie agora — esta chave não será exibida novamente:
              </p>
              <p className="break-all font-mono text-xs text-amber-200">{newKey}</p>
            </div>
            <div>
              <p className="text-xs text-amber-300">
                Ou conecte em um comando (escreve config, registra o MCP e instala os hooks):
              </p>
              {(() => {
                const cmd = `amp connect ${connectToken(wsUrl(), agent.slug, newKey)}`;
                return (
                  <div className="mt-1 flex items-center gap-2">
                    <code className="min-w-0 flex-1 break-all rounded bg-zinc-900 px-2 py-1 font-mono text-[11px] text-emerald-300">
                      {cmd}
                    </code>
                    <button
                      type="button"
                      onClick={() => navigator.clipboard?.writeText(cmd)}
                      className="shrink-0 rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-700"
                    >
                      copiar
                    </button>
                  </div>
                );
              })()}
              <p className="mt-1 text-[10px] text-zinc-500">
                <span className="font-mono">amp</span> ={" "}
                <span className="font-mono">pnpm --dir /caminho/para/amp/bridge connect</span>
              </p>
            </div>
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
                {key.revoked_at && <span className="ml-1.5 text-red-400">revogada</span>}
              </span>
              {!key.revoked_at && (
                <button
                  type="button"
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

      <div className="mt-4 border-t border-zinc-800 pt-3">
        <h4 className="mb-2 text-sm font-medium text-zinc-300">Grupos</h4>
        {groups.length === 0 ? (
          <p className="text-xs text-zinc-500">
            Nenhum grupo na equipe ainda — crie um em “Grupos”.
          </p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {groups.map((group) => {
              const isMember = group.members.includes(agent.slug);
              return (
                <button
                  key={group.slug}
                  type="button"
                  onClick={() => toggleGroup(group, isMember)}
                  title={isMember ? "sair do grupo" : "entrar no grupo"}
                  className={`rounded-full border px-2.5 py-1 font-mono text-xs transition-colors ${
                    isMember
                      ? "border-emerald-600 bg-emerald-900/40 text-emerald-300 hover:bg-emerald-900/20"
                      : "border-zinc-700 text-zinc-400 hover:border-emerald-500 hover:text-emerald-300"
                  }`}
                >
                  {isMember ? "✓ " : "+ "}@{group.slug}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="mt-4 rounded-md border border-red-800/70 bg-red-950/20 p-3">
        <h4 className="mb-2 text-sm font-semibold text-red-300">⚠ Zona de perigo</h4>

        <div className="mb-3">
          <p className="text-xs text-zinc-400">
            Bloqueio de segredos do SO (<span className="font-mono">~/.ssh, ~/.aws, /etc…</span>):{" "}
            {agent.block_sensitive_paths ? (
              <span className="text-emerald-400">ativo</span>
            ) : (
              <span className="font-semibold text-red-400">DESATIVADO</span>
            )}
          </p>
          {agent.block_sensitive_paths ? (
            <div className="mt-1.5">
              <DangerAction
                trigger="Desativar bloqueio de segredos"
                warning="Sem isto, uma mensagem de terceiro pode fazer o auto-respond ler ~/.ssh, ~/.aws e .env e devolver o conteúdo na resposta. Só desative se confia em TODOS que podem enviar a este agente."
                confirmWord={agent.slug}
                onConfirm={() => patchDanger({ block_sensitive_paths: false })}
              />
            </div>
          ) : (
            <button
              type="button"
              onClick={() => patchDanger({ block_sensitive_paths: true })}
              className="mt-1.5 rounded-md bg-emerald-800/60 px-2.5 py-1 text-xs font-medium text-emerald-200 hover:bg-emerald-800"
            >
              Reativar bloqueio
            </button>
          )}
        </div>

        <div>
          <p className="text-xs text-zinc-400">
            Agentes confiáveis (acesso TOTAL, sem restrições de arquivo):
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {agent.trusted_senders.length === 0 && (
              <span className="text-xs text-zinc-500">nenhum</span>
            )}
            {agent.trusted_senders.map((s) => (
              <span
                key={s}
                className="flex items-center gap-1 rounded-full border border-red-700 bg-red-950/40 px-2 py-0.5 font-mono text-xs text-red-300"
              >
                {s}
                <button
                  type="button"
                  title="remover"
                  onClick={() =>
                    patchDanger({
                      trusted_senders: agent.trusted_senders.filter((t) => t !== s),
                    })
                  }
                  className="text-red-400 hover:text-red-200"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
          <input
            value={trustInput}
            onChange={(e) => setTrustInput(e.target.value)}
            placeholder="slug-do-agente-confiável"
            className={`${inputClass} mt-2`}
          />
          {trustInput.trim() && (
            <div className="mt-1.5">
              <DangerAction
                trigger={`Tornar "${trustInput.trim()}" confiável`}
                warning={`"${trustInput.trim()}" passará a rodar o auto-respond SEM nenhuma restrição de arquivo (acesso total). Se a sessão dele for comprometida, vaza tudo. Confirme só se confia plenamente.`}
                confirmWord={agent.slug}
                onConfirm={() => {
                  patchDanger({
                    trusted_senders: [...agent.trusted_senders, trustInput.trim()],
                  });
                  setTrustInput("");
                }}
              />
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 border-t border-zinc-800 pt-3">
        <h4 className="mb-2 text-sm font-medium text-zinc-300">Como conectar este agente</h4>
        <pre className="overflow-x-auto whitespace-pre rounded-md bg-zinc-900 px-3 py-2 font-mono text-[11px] leading-relaxed text-zinc-400">
          {connectSnippet}
        </pre>
      </div>
    </section>
  );
}
