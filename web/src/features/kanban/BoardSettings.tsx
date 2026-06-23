import { useCallback, useEffect, useState } from "react";
import { DangerAction } from "../../components/DangerAction";
import { agentsApi } from "../../lib/api/agents";
import { kanbanApi } from "../../lib/api/kanban";
import type {
  DirectoryEntry,
  KanbanBoard,
  KanbanGrant,
  KanbanMember,
  User,
} from "../../lib/api/types";
import { usersApi } from "../../lib/api/users";

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

const AGENT_ROLE_LABEL: Record<string, string> = {
  none: "Sem acesso (só devs)",
  viewer: "Leitor",
  contributor: "Colaborador",
  editor: "Editor",
};

/**
 * Board configuration (Epic 06 · 6.3/6.6 + Epic 10).
 *
 * Owner/admin (`canManage`) get the full panel: visibility, default agent role,
 * **board members** (share a private board with specific people), every agent
 * grant, event cards, and the danger-zone.
 *
 * A non-owner who can see the board gets a limited panel: they may grant/revoke
 * only **their own** agents (Epic 10). Granting an agent WRITE
 * (contributor/editor) is gated behind the danger-zone confirm either way.
 */
export function BoardSettings({
  board,
  onBoardChange,
  onBoardDeleted,
  canManage,
}: {
  board: KanbanBoard;
  onBoardChange: (b: KanbanBoard) => void;
  onBoardDeleted: () => void;
  canManage: boolean;
}) {
  const boardId = board.id;
  const [name, setName] = useState(board.name);
  const [grants, setGrants] = useState<KanbanGrant[]>([]);
  const [directory, setDirectory] = useState<DirectoryEntry[]>([]);
  const [myAgents, setMyAgents] = useState<string[]>([]);
  const [members, setMembers] = useState<KanbanMember[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [agent, setAgent] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [newMemberId, setNewMemberId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    kanbanApi
      .listGrants(boardId)
      .then(setGrants)
      .catch((e) => setError(e instanceof Error ? e.message : "Falha ao carregar permissões."));
  }, [boardId]);

  const reloadMembers = useCallback(() => {
    kanbanApi
      .listMembers(boardId)
      .then(setMembers)
      .catch((e) => setError(e instanceof Error ? e.message : "Falha ao carregar membros."));
  }, [boardId]);

  useEffect(() => {
    reload();
    // Own agents drive the member-limited grant picker + revoke gating (Epic 10).
    agentsApi
      .mine()
      .then((a) => setMyAgents(a.map((x) => x.slug)))
      .catch(() => {});
    if (canManage) {
      agentsApi
        .directory()
        .then(setDirectory)
        .catch(() => {});
      reloadMembers();
      usersApi
        .list()
        .then(setUsers)
        .catch(() => {});
    }
  }, [reload, reloadMembers, canManage]);

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

  async function addMember() {
    const id = Number(newMemberId);
    if (!id) return;
    setError(null);
    try {
      await kanbanApi.addMember(boardId, id);
      setNewMemberId("");
      reloadMembers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao adicionar membro.");
    }
  }

  async function removeMember(userId: number) {
    try {
      await kanbanApi.removeMember(boardId, userId);
      reloadMembers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao remover membro.");
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
  // Owner/admin can grant any agent; a member only their own (Epic 10).
  const grantable = canManage ? directory.map((d) => d.slug) : myAgents;
  const candidates = grantable.filter((slug) => !granted.has(slug));
  const canRevoke = (slug: string) => canManage || myAgents.includes(slug);

  const memberIds = new Set(members.map((m) => m.user_id));
  const addableUsers = users.filter((u) => u.id !== board.owner_id && !memberIds.has(u.id));

  return (
    <section
      aria-label="Configurações do quadro"
      className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3"
    >
      <h2 className="text-sm font-semibold text-zinc-200">Configurações do quadro</h2>

      {canManage && (
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
            <option value="private">Privado (dono + convidados)</option>
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
      )}

      {/* Members — owner/admin only; the way to share a private board (Epic 10). */}
      {canManage && (
        <div className="space-y-2 border-t border-zinc-800 pt-3">
          <h2 className="text-sm font-semibold text-zinc-200">Membros do quadro</h2>
          <p className="text-xs text-zinc-500">
            Compartilhe este quadro com pessoas específicas. Útil para um quadro{" "}
            <strong>privado</strong>: cada membro passa a ver e editar o quadro e pode conceder
            acesso aos próprios agentes.
          </p>
          <ul className="space-y-1">
            {members.length === 0 && (
              <li className="text-xs text-zinc-500">
                Nenhum membro convidado (apenas o dono e admins têm acesso).
              </li>
            )}
            {members.map((m) => (
              <li
                key={m.user_id}
                className="flex items-center justify-between rounded bg-zinc-800 px-2 py-1 text-sm"
              >
                <span className="text-zinc-200">
                  {m.name}
                  <span className="ml-2 text-xs text-zinc-500">{m.email}</span>
                </span>
                <button
                  type="button"
                  aria-label={`Remover ${m.name} do quadro`}
                  className="text-xs text-zinc-400 hover:text-red-300"
                  onClick={() => removeMember(m.user_id)}
                >
                  remover
                </button>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label="Pessoa"
              className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-200"
              value={newMemberId}
              onChange={(e) => setNewMemberId(e.target.value)}
            >
              <option value="">Escolha uma pessoa…</option>
              {addableUsers.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name} ({u.email})
                </option>
              ))}
            </select>
            {newMemberId && (
              <button
                type="button"
                className="rounded bg-indigo-600 px-3 py-1 text-sm text-white"
                onClick={addMember}
              >
                Adicionar
              </button>
            )}
          </div>
        </div>
      )}

      <h2 className="border-t border-zinc-800 pt-3 text-sm font-semibold text-zinc-200">
        Permissões de agentes
      </h2>
      <p className="text-xs text-zinc-500">
        {canManage
          ? "Por padrão o quadro é só para devs. Conceda a um agente o direito de ler, criar/mover seus próprios cards (colaborador) ou editar qualquer card (editor)."
          : "Conceda aos seus próprios agentes o direito de ler, criar/mover seus próprios cards (colaborador) ou editar qualquer card (editor) neste quadro."}
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
            {canRevoke(g.agent_slug) && (
              <button
                type="button"
                aria-label={`Remover acesso de ${g.agent_slug}`}
                className="text-xs text-zinc-400 hover:text-red-300"
                onClick={() => revoke(g.agent_slug)}
              >
                remover
              </button>
            )}
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
          <option value="">
            {candidates.length === 0 && !canManage ? "Você não tem agentes" : "Escolha um agente…"}
          </option>
          {candidates.map((slug) => (
            <option key={slug} value={slug}>
              {slug}
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

      {canManage && (
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
      )}

      {canManage && (
        <div className="space-y-2 border-t border-red-900/60 pt-3">
          <h3 className="text-sm font-medium text-red-300">Zona de perigo</h3>
          <DangerAction
            trigger="Excluir este quadro"
            warning={`Excluir o quadro “${board.name}” apaga todas as colunas, cards e comentários. Não dá para desfazer.`}
            confirmWord={board.name}
            onConfirm={deleteBoard}
          />
        </div>
      )}
    </section>
  );
}
