import { useCallback, useEffect, useState } from "react";
import { DangerAction } from "../../components/DangerAction";
import { agentsApi } from "../../lib/api/agents";
import { kanbanApi } from "../../lib/api/kanban";
import type { DirectoryEntry, KanbanBoard, KanbanGrant } from "../../lib/api/types";

const ROLES = ["viewer", "contributor", "editor"] as const;
type Role = (typeof ROLES)[number];

// contributor/editor let an AI WRITE to the board → behind the danger-zone,
// like trusted_senders (Epic 06 · 6.3).
const WRITE_ROLES = new Set<Role>(["contributor", "editor"]);

const roleLabel: Record<Role, string> = {
  viewer: "Leitor",
  contributor: "Colaborador",
  editor: "Editor",
};

/**
 * Per-agent grants panel (Epic 06 · 6.3/6.6). Owner/admin only — the hub 403s
 * otherwise. Granting an agent WRITE (contributor/editor) is gated behind the
 * danger-zone confirm: relaxing a guardrail by letting an AI mutate the board.
 */
const AGENT_ROLE_LABEL: Record<string, string> = {
  none: "Sem acesso (só devs)",
  viewer: "Leitor",
  contributor: "Colaborador",
  editor: "Editor",
};

export function BoardSettings({
  board,
  onBoardChange,
  onBoardDeleted,
}: {
  board: KanbanBoard;
  onBoardChange: (b: KanbanBoard) => void;
  onBoardDeleted: () => void;
}) {
  const boardId = board.id;
  const [name, setName] = useState(board.name);
  const [grants, setGrants] = useState<KanbanGrant[]>([]);
  const [directory, setDirectory] = useState<DirectoryEntry[]>([]);
  const [agent, setAgent] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    kanbanApi
      .listGrants(boardId)
      .then(setGrants)
      .catch((e) => setError(e instanceof Error ? e.message : "Falha ao carregar permissões."));
  }, [boardId]);

  useEffect(() => {
    reload();
    agentsApi
      .directory()
      .then(setDirectory)
      .catch(() => {});
  }, [reload]);

  async function grant(slug: string, r: Role) {
    setError(null);
    try {
      await kanbanApi.setGrant(boardId, slug, r);
      setAgent("");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao conceder permissão.");
    }
  }

  async function revoke(slug: string) {
    try {
      await kanbanApi.removeGrant(boardId, slug);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao remover permissão.");
    }
  }

  async function patchBoard(data: Parameters<typeof kanbanApi.updateBoard>[1]) {
    try {
      onBoardChange(await kanbanApi.updateBoard(boardId, data));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao salvar a configuração.");
    }
  }

  async function toggleEventCard(
    flag: "auto_card_on_delegation" | "auto_card_on_escalation",
    value: boolean,
  ) {
    await patchBoard({ [flag]: value });
  }

  async function deleteBoard() {
    try {
      await kanbanApi.deleteBoard(boardId);
      onBoardDeleted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao excluir o quadro.");
    }
  }

  const granted = new Set(grants.map((g) => g.agent_slug));
  const candidates = directory.filter((d) => !granted.has(d.slug));

  return (
    <section
      aria-label="Permissões de agentes"
      className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3"
    >
      <h2 className="text-sm font-semibold text-zinc-200">Configurações do quadro</h2>
      <div className="flex flex-wrap items-center gap-2">
        <input
          aria-label="Nome do quadro"
          className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() =>
            name.trim() && name.trim() !== board.name && patchBoard({ name: name.trim() })
          }
        />
        <select
          aria-label="Visibilidade"
          className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-200"
          value={board.visibility}
          onChange={(e) => patchBoard({ visibility: e.target.value })}
        >
          <option value="team">Time (todos editam)</option>
          <option value="private">Privado (dono + concedidos)</option>
        </select>
        <select
          aria-label="Papel padrão dos agentes"
          className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-200"
          value={board.default_agent_role}
          onChange={(e) => patchBoard({ default_agent_role: e.target.value })}
        >
          {Object.entries(AGENT_ROLE_LABEL).map(([v, label]) => (
            <option key={v} value={v}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <h2 className="border-t border-zinc-800 pt-3 text-sm font-semibold text-zinc-200">
        Permissões de agentes
      </h2>
      <p className="text-xs text-zinc-500">
        Por padrão o quadro é só para devs. Conceda a um agente o direito de ler, criar/mover seus
        próprios cards (colaborador) ou editar qualquer card (editor).
      </p>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <ul className="space-y-1">
        {grants.length === 0 && (
          <li className="text-xs text-zinc-500">Nenhum agente com acesso (só devs).</li>
        )}
        {grants.map((g) => (
          <li
            key={g.agent_slug}
            className="flex items-center justify-between rounded bg-zinc-800 px-2 py-1 text-sm"
          >
            <span className="text-zinc-200">
              {g.agent_slug}
              <span className="ml-2 rounded bg-zinc-700 px-1.5 py-0.5 text-xs text-zinc-300">
                {roleLabel[g.role as Role] ?? g.role}
              </span>
            </span>
            <button
              type="button"
              aria-label={`Remover acesso de ${g.agent_slug}`}
              className="text-xs text-zinc-400 hover:text-red-300"
              onClick={() => revoke(g.agent_slug)}
            >
              remover
            </button>
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-3">
        <select
          aria-label="Agente"
          className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-200"
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
        >
          <option value="">Escolha um agente…</option>
          {candidates.map((d) => (
            <option key={d.slug} value={d.slug}>
              {d.slug}
            </option>
          ))}
        </select>
        <select
          aria-label="Papel"
          className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-200"
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {roleLabel[r]}
            </option>
          ))}
        </select>

        {agent && !WRITE_ROLES.has(role) && (
          <button
            type="button"
            className="rounded bg-indigo-600 px-3 py-1 text-sm text-white"
            onClick={() => grant(agent, role)}
          >
            Conceder
          </button>
        )}
        {agent && WRITE_ROLES.has(role) && (
          <DangerAction
            trigger={`Conceder ${roleLabel[role]} a ${agent}`}
            warning={`Você vai permitir que a IA “${agent}” escreva neste quadro (criar/mover/editar cards). Trate como relaxar uma proteção.`}
            confirmWord={agent}
            onConfirm={() => grant(agent, role)}
          />
        )}
      </div>

      <div className="space-y-2 border-t border-zinc-800 pt-3">
        <h3 className="text-sm font-medium text-zinc-300">Cards automáticos</h3>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={board.auto_card_on_delegation}
            onChange={(e) => toggleEventCard("auto_card_on_delegation", e.target.checked)}
          />
          Criar card quando uma tarefa for delegada a um agente meu
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={board.auto_card_on_escalation}
            onChange={(e) => toggleEventCard("auto_card_on_escalation", e.target.checked)}
          />
          Criar card quando um agente meu escalar para mim
        </label>
      </div>

      <div className="space-y-2 border-t border-red-900/60 pt-3">
        <h3 className="text-sm font-medium text-red-300">Zona de perigo</h3>
        <DangerAction
          trigger="Excluir este quadro"
          warning={`Excluir o quadro “${board.name}” apaga todas as colunas, cards e comentários. Não dá para desfazer.`}
          confirmWord={board.name}
          onConfirm={deleteBoard}
        />
      </div>
    </section>
  );
}
