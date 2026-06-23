import { useState } from "react";
import { DangerAction } from "../../components/DangerAction";
import { agentsApi } from "../../lib/api/agents";
import { presetsApi } from "../../lib/api/presets";
import type { Agent, Preset, PresetSettings } from "../../lib/api/types";

/** A preset relaxes a dangerous knob → applying it goes behind the danger zone. */
function isPermissive(s: PresetSettings): boolean {
  return (
    s.allow_write || !s.block_sensitive_paths || !s.confine_to_dir || s.trusted_senders.length > 0
  );
}

function snapshot(agent: Agent): PresetSettings {
  return {
    mode: agent.mode,
    max_auto_per_hour: agent.max_auto_per_hour,
    auto_timeout_secs: agent.auto_timeout_secs,
    allow_write: agent.allow_write,
    block_hidden_files: agent.block_hidden_files,
    block_sensitive_paths: agent.block_sensitive_paths,
    confine_to_dir: agent.confine_to_dir,
    denied_paths: agent.denied_paths,
    trusted_senders: agent.trusted_senders,
    require_approval: agent.require_approval,
    auto_paused: agent.auto_paused,
    max_auto_tokens_per_day: agent.max_auto_tokens_per_day,
    max_auto_cost_usd_per_day: agent.max_auto_cost_usd_per_day,
  };
}

/** Apply a reusable guardrail preset to this agent, or save its current config
 * as a new one (Epic 04 · 4.1). Permissive presets apply behind the danger zone. */
export function AgentPresets({ agent, onChanged }: { agent: Agent; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [presets, setPresets] = useState<Preset[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [draftName, setDraftName] = useState("");

  function load() {
    setError(null);
    setLoading(true);
    presetsApi
      .list()
      .then(setPresets)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar."))
      .finally(() => setLoading(false));
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && presets === null && !loading) load();
  }

  async function apply(preset: Preset) {
    setError(null);
    try {
      await agentsApi.applyPreset(agent.slug, preset.id);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao aplicar preset.");
    }
  }

  async function saveCurrent() {
    if (!name.trim()) return setError("Dê um nome ao preset.");
    setError(null);
    try {
      await presetsApi.create(name.trim(), snapshot(agent));
      setName("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar preset.");
    }
  }

  async function remove(preset: Preset) {
    setError(null);
    try {
      await presetsApi.remove(preset.id);
      setPresets((prev) => (prev ? prev.filter((p) => p.id !== preset.id) : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao excluir preset.");
    }
  }

  async function commitRename(preset: Preset) {
    const next = draftName.trim();
    setRenamingId(null);
    if (!next || next === preset.name) return;
    setError(null);
    try {
      const updated = await presetsApi.update(preset.id, { name: next });
      setPresets((prev) => (prev ? prev.map((p) => (p.id === preset.id ? updated : p)) : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao renomear preset.");
    }
  }

  /** Overwrite the preset's settings with this agent's current config. */
  async function updateSettings(preset: Preset) {
    setError(null);
    try {
      const updated = await presetsApi.update(preset.id, { settings: snapshot(agent) });
      setPresets((prev) => (prev ? prev.map((p) => (p.id === preset.id ? updated : p)) : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar preset.");
    }
  }

  return (
    <div className="mt-4 border-t border-zinc-800 pt-3">
      <button
        type="button"
        onClick={toggle}
        className="flex items-center gap-1.5 text-sm font-medium text-zinc-300 hover:text-zinc-100"
        aria-expanded={open}
      >
        <span className="text-zinc-500">{open ? "▾" : "▸"}</span> Presets de guardrails
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {error && (
            <p role="alert" className="text-xs text-red-400">
              {error}
            </p>
          )}
          {loading && presets === null && <p className="text-xs text-zinc-500">carregando…</p>}
          {presets && (
            <ul className="space-y-1">
              {presets.map((p) => (
                <li
                  key={p.id}
                  className="flex flex-wrap items-center gap-2 rounded-md bg-zinc-900 px-2.5 py-1.5 text-xs"
                >
                  {renamingId === p.id ? (
                    <input
                      aria-label={`Novo nome do preset ${p.name}`}
                      value={draftName}
                      // biome-ignore lint/a11y/noAutofocus: focus the field the user just opened
                      autoFocus
                      onChange={(e) => setDraftName(e.target.value)}
                      onBlur={() => commitRename(p)}
                      onKeyDown={(e) => e.key === "Enter" && commitRename(p)}
                      className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-950 px-1.5 py-0.5 text-zinc-100"
                    />
                  ) : (
                    <span className="text-zinc-200">{p.name}</span>
                  )}
                  {p.owner_id === null && (
                    <span className="rounded bg-zinc-800 px-1 text-[10px] text-zinc-500">
                      padrão
                    </span>
                  )}
                  <span className="ml-auto flex items-center gap-1.5">
                    {isPermissive(p.settings) ? (
                      <DangerAction
                        trigger="Aplicar"
                        warning={`"${p.name}" relaxa proteções (escrita / segredos / acesso amplo). Aplicar a ${agent.slug}?`}
                        confirmWord="aplicar"
                        onConfirm={() => apply(p)}
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => apply(p)}
                        className="rounded bg-zinc-800 px-2 py-0.5 text-zinc-300 hover:bg-zinc-700"
                      >
                        Aplicar
                      </button>
                    )}
                    {/* Editing a preset is owner-only (default presets are read-only). */}
                    {p.owner_id !== null && renamingId !== p.id && (
                      <>
                        <button
                          type="button"
                          aria-label={`Renomear preset ${p.name}`}
                          onClick={() => {
                            setRenamingId(p.id);
                            setDraftName(p.name);
                          }}
                          className="rounded px-2 py-0.5 text-zinc-500 hover:text-zinc-200"
                        >
                          Renomear
                        </button>
                        <button
                          type="button"
                          aria-label={`Atualizar preset ${p.name} com a config atual`}
                          title="Salvar a configuração atual deste agente neste preset"
                          onClick={() => updateSettings(p)}
                          className="rounded px-2 py-0.5 text-zinc-500 hover:text-zinc-200"
                        >
                          Atualizar
                        </button>
                        <button
                          type="button"
                          onClick={() => remove(p)}
                          className="rounded px-2 py-0.5 text-zinc-500 hover:text-zinc-200"
                        >
                          Excluir
                        </button>
                      </>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="flex items-center gap-2">
            <input
              aria-label="Nome do preset"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Salvar config atual como…"
              className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100"
            />
            <button
              type="button"
              onClick={saveCurrent}
              className="rounded-md bg-zinc-800 px-2.5 py-1 text-xs text-zinc-200 hover:bg-zinc-700"
            >
              Salvar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
