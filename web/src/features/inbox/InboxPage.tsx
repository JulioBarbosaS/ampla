import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FormError } from "../../components/forms";
import { type NotificationFilter, notificationsApi } from "../../lib/api/notifications";
import type { AppNotification, NotificationStatus, NotifyLevel } from "../../lib/api/types";
import { useInboxStore } from "../../stores/inbox";

/** Delivery gate options (pt-BR for the operator). */
const NOTIFY_LEVELS: { value: NotifyLevel; label: string }[] = [
  { value: "all", label: "Tudo" },
  { value: "mentions_and_direct", label: "Menções e diretos" },
  { value: "mute", label: "Silenciar" },
];

/** Reason → chip. Plain, glanceable; an audit/triage surface. */
const REASON_CHIP: Record<string, { label: string; cls: string }> = {
  mention: { label: "menção", cls: "bg-amber-900/50 text-amber-300" },
  direct_message: { label: "mensagem", cls: "bg-zinc-800 text-zinc-300" },
  task_assigned: { label: "tarefa", cls: "bg-emerald-900/50 text-emerald-300" },
  broadcast: { label: "broadcast", cls: "bg-sky-900/50 text-sky-300" },
  approval_requested: { label: "aprovação", cls: "bg-red-900/50 text-red-300" },
  autorespond_completed: { label: "auto-resposta", cls: "bg-zinc-800 text-zinc-300" },
  autorespond_blocked: { label: "auto bloqueada", cls: "bg-red-900/50 text-red-300" },
};

/** Built-in views: triage states + canned reason filters (the server already
 * accepts `?status=`/`?reason=`). */
type InboxView = {
  key: string;
  label: string;
  filter: { status?: NotificationStatus; reason?: string };
};

const VIEWS: InboxView[] = [
  { key: "inbox", label: "Inbox", filter: { status: "inbox" } },
  { key: "saved", label: "Salvos", filter: { status: "saved" } },
  { key: "done", label: "Concluídos", filter: { status: "done" } },
  { key: "mentions", label: "Menções", filter: { reason: "mention" } },
  { key: "approvals", label: "Aprovações", filter: { reason: "approval_requested" } },
  { key: "tasks", label: "Tarefas", filter: { reason: "task_assigned" } },
];

const filterOf = (key: string): InboxView["filter"] =>
  (VIEWS.find((v) => v.key === key) ?? VIEWS[0]).filter;

/** The active query = the view's base filter + free search qualifiers (q). */
function buildFilter(viewKey: string, q: string): NotificationFilter {
  const base = filterOf(viewKey);
  const trimmed = q.trim();
  return trimmed ? { ...base, q: trimmed } : base;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.round(diff / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `há ${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `há ${h} h`;
  return new Date(iso).toLocaleDateString("pt-BR");
}

export function NotificationRow({
  n,
  onOpen,
  onTriage,
  onIgnore,
}: {
  n: AppNotification;
  onOpen: (n: AppNotification) => void;
  onTriage: (n: AppNotification, patch: { unread?: boolean; status?: NotificationStatus }) => void;
  onIgnore: (n: AppNotification) => void;
}) {
  const chip = REASON_CHIP[n.reason] ?? { label: n.reason, cls: "bg-zinc-800 text-zinc-300" };
  return (
    <li
      className={`flex items-start gap-3 rounded-md border px-3 py-2 ${
        n.unread ? "border-zinc-700 bg-zinc-900/60" : "border-zinc-800/60 bg-transparent"
      }`}
    >
      {n.unread && (
        <span
          aria-hidden="true"
          title="não lida"
          className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-emerald-400"
        />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={`rounded px-1.5 py-0.5 font-medium ${chip.cls}`}>{chip.label}</span>
          {n.agent_slug && <span className="font-mono text-zinc-500">{n.agent_slug}</span>}
          <span className="text-zinc-600">· {relativeTime(n.updated_at)}</span>
        </div>
        <button
          type="button"
          onClick={() => onOpen(n)}
          className={`mt-1 block w-full truncate text-left text-sm hover:underline ${
            n.unread ? "font-medium text-zinc-100" : "text-zinc-400"
          }`}
        >
          {n.title}
        </button>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          onClick={() => onTriage(n, { unread: !n.unread })}
          className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300 hover:bg-zinc-700"
        >
          {n.unread ? "Lida" : "Não lida"}
        </button>
        {n.status !== "saved" && (
          <button
            type="button"
            onClick={() => onTriage(n, { status: "saved" })}
            className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300 hover:bg-zinc-700"
          >
            Salvar
          </button>
        )}
        {n.status !== "done" && (
          <button
            type="button"
            onClick={() => onTriage(n, { status: "done" })}
            className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-emerald-300 hover:bg-zinc-700"
          >
            Concluir
          </button>
        )}
        <button
          type="button"
          onClick={() => onIgnore(n)}
          title="Silenciar esta conversa e concluir"
          className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-700"
        >
          Ignorar
        </button>
      </div>
    </li>
  );
}

export function InboxPage() {
  const navigate = useNavigate();
  const { items, setItems, setUnreadCount } = useInboxStore();
  const [viewKey, setViewKey] = useState<string>("inbox");
  const [searchInput, setSearchInput] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const [notifyLevel, setNotifyLevel] = useState<NotifyLevel>("mentions_and_direct");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(
    (filter: NotificationFilter) => {
      setLoading(true);
      Promise.all([notificationsApi.list(filter), notificationsApi.unreadCount()])
        .then(([list, count]) => {
          setItems(list);
          setUnreadCount(count.unread_count);
        })
        .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar."))
        .finally(() => setLoading(false));
    },
    [setItems, setUnreadCount],
  );

  useEffect(() => reload(buildFilter(viewKey, appliedQ)), [viewKey, appliedQ, reload]);

  useEffect(() => {
    notificationsApi
      .getPrefs()
      .then((p) => setNotifyLevel(p.notify_level))
      .catch(() => {});
  }, []);

  async function changeLevel(level: NotifyLevel) {
    setNotifyLevel(level); // optimistic
    setError(null);
    try {
      await notificationsApi.setPrefs(level);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar preferência.");
    }
  }

  async function triage(
    n: AppNotification,
    patch: { unread?: boolean; status?: NotificationStatus },
  ) {
    setError(null);
    try {
      await notificationsApi.triage(n.id, patch);
      reload(buildFilter(viewKey, appliedQ)); // re-sync (item may leave the view) + badge
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar.");
    }
  }

  function open(n: AppNotification) {
    if (n.unread) void notificationsApi.triage(n.id, { unread: false }).catch(() => {});
    navigate(n.link || "/");
  }

  async function ignoreThread(n: AppNotification) {
    setError(null);
    try {
      // Mute the thread (future low-signal activity won't resurface it) and
      // archive the current row in one gesture.
      await notificationsApi.subscribe(n.subject_key, "ignored");
      await notificationsApi.triage(n.id, { status: "done" });
      reload(buildFilter(viewKey, appliedQ));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao ignorar conversa.");
    }
  }

  async function readAll() {
    setError(null);
    try {
      await notificationsApi.readAll();
      reload(buildFilter(viewKey, appliedQ));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao marcar como lidas.");
    }
  }

  return (
    <div className="mx-auto h-full max-w-3xl space-y-4 overflow-y-auto px-4 py-6">
      <h1 className="text-lg font-semibold text-zinc-100">Inbox</h1>
      <FormError message={error} />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setAppliedQ(searchInput);
        }}
        className="flex gap-2"
      >
        <input
          type="search"
          aria-label="Buscar no inbox"
          placeholder="Buscar: is:unread reason:mention from:slug agent:slug…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-600"
        />
        <button
          type="submit"
          className="rounded-md bg-zinc-800 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-700"
        >
          Buscar
        </button>
        {appliedQ && (
          <button
            type="button"
            onClick={() => {
              setSearchInput("");
              setAppliedQ("");
            }}
            className="rounded-md px-2.5 py-1.5 text-sm text-zinc-400 hover:text-zinc-50"
          >
            Limpar
          </button>
        )}
      </form>
      <div className="flex flex-wrap items-center gap-1 gap-y-2">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            type="button"
            onClick={() => setViewKey(v.key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              viewKey === v.key ? "bg-zinc-800 text-zinc-50" : "text-zinc-400 hover:text-zinc-50"
            }`}
          >
            {v.label}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-1.5 text-xs text-zinc-500">
          Notificar:
          <select
            aria-label="Nível de notificação"
            value={notifyLevel}
            onChange={(e) => changeLevel(e.target.value as NotifyLevel)}
            className="rounded-md border border-zinc-700 bg-zinc-900 px-1.5 py-1 text-xs text-zinc-200"
          >
            {NOTIFY_LEVELS.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={readAll}
          className="rounded-md px-2.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-50"
        >
          Marcar todas como lidas
        </button>
      </div>
      {loading && items.length === 0 ? (
        <p className="text-sm text-zinc-500">carregando…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-zinc-500">Nada por aqui — inbox-zero. ✨</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((n) => (
            <NotificationRow
              key={n.id}
              n={n}
              onOpen={open}
              onTriage={triage}
              onIgnore={ignoreThread}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
