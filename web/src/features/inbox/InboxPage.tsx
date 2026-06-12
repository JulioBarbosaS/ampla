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
  selected,
  onSelect,
  onOpen,
  onTriage,
  onIgnore,
}: {
  n: AppNotification;
  selected: boolean;
  onSelect: (n: AppNotification, checked: boolean) => void;
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
      <input
        type="checkbox"
        aria-label={`Selecionar: ${n.title}`}
        checked={selected}
        onChange={(e) => onSelect(n, e.target.checked)}
        className="mt-1.5 shrink-0"
      />
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
  const [selected, setSelected] = useState<Set<number>>(new Set());
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

  function toggleSelect(n: AppNotification, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(n.id);
      else next.delete(n.id);
      return next;
    });
  }

  const bulkTriage = useCallback(
    async (patch: { unread?: boolean; status?: NotificationStatus }) => {
      if (selected.size === 0) return;
      setError(null);
      try {
        await Promise.all([...selected].map((id) => notificationsApi.triage(id, patch)));
        setSelected(new Set());
        reload(buildFilter(viewKey, appliedQ));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Falha ao atualizar.");
      }
    },
    [selected, viewKey, appliedQ, reload],
  );

  const bulkIgnore = useCallback(async () => {
    if (selected.size === 0) return;
    setError(null);
    const targets = items.filter((n) => selected.has(n.id));
    try {
      await Promise.all(
        targets.map(async (n) => {
          await notificationsApi.subscribe(n.subject_key, "ignored");
          await notificationsApi.triage(n.id, { status: "done" });
        }),
      );
      setSelected(new Set());
      reload(buildFilter(viewKey, appliedQ));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao ignorar.");
    }
  }, [selected, items, viewKey, appliedQ, reload]);

  // Keyboard triage on the current selection (E=concluir, ⇧I=lida, ⇧U=não
  // lida, ⇧M=ignorar). Ignored while typing in a text field/search.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (selected.size === 0) return;
      const el = document.activeElement as HTMLElement | null;
      const tag = el?.tagName.toLowerCase();
      const type = (el as HTMLInputElement | null)?.type;
      const typing =
        tag === "textarea" ||
        (tag === "input" && !["checkbox", "radio", "button", "submit"].includes(type ?? ""));
      if (typing) return;
      const k = e.key.toLowerCase();
      if (k === "e" && !e.shiftKey) {
        e.preventDefault();
        void bulkTriage({ status: "done" });
      } else if (e.shiftKey && k === "i") {
        e.preventDefault();
        void bulkTriage({ unread: false });
      } else if (e.shiftKey && k === "u") {
        e.preventDefault();
        void bulkTriage({ unread: true });
      } else if (e.shiftKey && k === "m") {
        e.preventDefault();
        void bulkIgnore();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selected, bulkTriage, bulkIgnore]);

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
          setSelected(new Set());
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
              setSelected(new Set());
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
            onClick={() => {
              setViewKey(v.key);
              setSelected(new Set());
            }}
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
      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-zinc-700 bg-zinc-900/60 px-3 py-2 text-sm">
          <span className="text-zinc-300">{selected.size} selecionada(s)</span>
          <button
            type="button"
            onClick={() => bulkTriage({ unread: false })}
            className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300 hover:bg-zinc-700"
          >
            Marcar lidas
          </button>
          <button
            type="button"
            onClick={() => bulkTriage({ status: "done" })}
            className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-emerald-300 hover:bg-zinc-700"
          >
            Concluir selecionadas
          </button>
          <button
            type="button"
            onClick={() => bulkIgnore()}
            className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-700"
          >
            Ignorar selecionadas
          </button>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            className="rounded px-2 py-0.5 text-xs text-zinc-500 hover:text-zinc-200"
          >
            Limpar seleção
          </button>
          <span className="ml-auto hidden text-xs text-zinc-600 sm:inline">
            E concluir · ⇧I lida · ⇧U não lida · ⇧M ignorar
          </span>
        </div>
      )}
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
              selected={selected.has(n.id)}
              onSelect={toggleSelect}
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
