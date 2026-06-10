import { useEffect, useState } from "react";
import { Dropdown } from "../../components/Dropdown";
import { stripMarkdown } from "../../components/Markdown";
import { agentsApi } from "../../lib/api/agents";
import { groupsApi } from "../../lib/api/groups";
import { messagesApi } from "../../lib/api/messages";
import type { Agent } from "../../lib/api/types";
import { useChatStore } from "../../stores/chat";

const AUTO_PREFIX = "[auto] ";

function previewOf(body: string, max = 38): string {
  const stripped = body.startsWith(AUTO_PREFIX) ? body.slice(AUTO_PREFIX.length) : body;
  const flat = stripMarkdown(stripped);
  return flat.length > max ? `${flat.slice(0, max)}…` : flat;
}

export function PresenceDot({ online }: { online: boolean }) {
  return (
    <span
      role="img"
      aria-label={online ? "online" : "offline"}
      className={`inline-block h-2.5 w-2.5 rounded-full ${
        online ? "bg-emerald-500" : "bg-zinc-600"
      }`}
    />
  );
}

export function Sidebar() {
  const { perspective, partner, directory, groups, online, activity } = useChatStore();
  const setPerspective = useChatStore((s) => s.setPerspective);
  const setPartner = useChatStore((s) => s.setPartner);
  const setGroups = useChatStore((s) => s.setGroups);
  const [mine, setMine] = useState<Agent[]>([]);
  const [previews, setPreviews] = useState<Record<string, string>>({});

  useEffect(() => {
    agentsApi
      .mine()
      .then(setMine)
      .catch(() => {});
    groupsApi
      .list()
      .then(setGroups)
      .catch(() => {});
  }, [setGroups]);

  // Preview of each partner's last message (under the current perspective).
  useEffect(() => {
    if (!perspective) {
      setPreviews({});
      return;
    }
    messagesApi
      .partners(perspective)
      .then((partners) =>
        setPreviews(
          Object.fromEntries(partners.map((p) => [p.agent, previewOf(p.last_message.body)])),
        ),
      )
      .catch(() => {});
  }, [perspective]);

  const others = directory.filter((entry) => entry.slug !== perspective);
  const current = mine.find((agent) => agent.slug === perspective) ?? null;

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-zinc-800">
      <div className="border-b border-zinc-800 p-3">
        <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">Conversando como</p>
        <Dropdown
          ariaLabel="Conversando como"
          value={perspective ?? ""}
          onChange={(v) => setPerspective(v || null)}
          placeholder="— selecione um agente —"
          className="w-full"
          options={mine.map((agent) => ({
            value: agent.slug,
            label:
              agent.display_name === agent.slug
                ? agent.slug
                : `${agent.display_name} (${agent.slug})`,
          }))}
        />
        {current && (
          <div className="mt-2 flex items-start justify-between gap-2 rounded-md bg-zinc-900 px-2.5 py-2">
            <div className="min-w-0">
              <div className="truncate text-sm text-zinc-200">{current.display_name}</div>
              <div className="truncate font-mono text-[11px] text-zinc-500">@{current.slug}</div>
            </div>
            <div className="shrink-0 text-right">
              <div className="text-xs text-zinc-400">
                {current.mode === "auto" ? "auto" : "inbox"}
              </div>
              <div className="text-xs text-zinc-500">
                {online[current.slug] ? "online" : "offline"}
              </div>
            </div>
          </div>
        )}
        {mine.length === 0 && (
          <p className="mt-2 text-xs text-zinc-500">
            Você ainda não tem agentes. Crie um em “Meus agentes”.
          </p>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <p className="px-3 pb-1 pt-3 text-xs uppercase tracking-wide text-zinc-500">Equipe</p>
        <ul>
          {others.map((entry) => (
            <li key={entry.slug}>
              <button
                type="button"
                onClick={() => setPartner(entry.slug)}
                className={`flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-zinc-900 ${
                  partner === entry.slug ? "bg-zinc-900" : ""
                }`}
              >
                <PresenceDot online={online[entry.slug] ?? false} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-zinc-200">{entry.slug}</span>
                  {activity[entry.slug] ? (
                    <span className="block truncate text-xs text-amber-400">respondendo…</span>
                  ) : (
                    <span className="block truncate text-xs text-zinc-500">
                      {previews[entry.slug] ?? entry.display_name}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
          {others.length === 0 && (
            <li className="px-3 py-2 text-sm text-zinc-500">Nenhum outro agente na equipe.</li>
          )}
        </ul>

        <p className="px-3 pb-1 pt-4 text-xs uppercase tracking-wide text-zinc-500">Grupos</p>
        <ul>
          <li>
            <GroupItem
              target="@all"
              label="@all"
              sub={`todos os agentes (${directory.length})`}
              active={partner === "@all"}
              onClick={() => setPartner("@all")}
            />
          </li>
          {groups.map((group) => (
            <li key={group.slug}>
              <GroupItem
                target={`@${group.slug}`}
                label={`@${group.slug}`}
                sub={`${group.display_name} · ${group.members.length} membro(s)`}
                active={partner === `@${group.slug}`}
                onClick={() => setPartner(`@${group.slug}`)}
              />
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

function GroupItem({
  label,
  sub,
  active,
  onClick,
}: {
  target: string;
  label: string;
  sub: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-zinc-900 ${
        active ? "bg-zinc-900" : ""
      }`}
    >
      <span className="text-zinc-500">#</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-mono text-sm text-zinc-200">{label}</span>
        <span className="block truncate text-xs text-zinc-500">{sub}</span>
      </span>
    </button>
  );
}
