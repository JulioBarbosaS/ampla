import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FormError } from "../../components/forms";
import { notificationsApi } from "../../lib/api/notifications";
import type { AppNotification, NotificationStatus } from "../../lib/api/types";
import { useInboxStore } from "../../stores/inbox";

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

const VIEWS: { key: NotificationStatus; label: string }[] = [
  { key: "inbox", label: "Inbox" },
  { key: "saved", label: "Salvos" },
  { key: "done", label: "Concluídos" },
];

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
}: {
  n: AppNotification;
  onOpen: (n: AppNotification) => void;
  onTriage: (n: AppNotification, patch: { unread?: boolean; status?: NotificationStatus }) => void;
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
      </div>
    </li>
  );
}

export function InboxPage() {
  const navigate = useNavigate();
  const { items, setItems, setUnreadCount } = useInboxStore();
  const [view, setView] = useState<NotificationStatus>("inbox");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(
    (status: NotificationStatus) => {
      setLoading(true);
      Promise.all([notificationsApi.list(status), notificationsApi.unreadCount()])
        .then(([list, count]) => {
          setItems(list);
          setUnreadCount(count.unread_count);
        })
        .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar."))
        .finally(() => setLoading(false));
    },
    [setItems, setUnreadCount],
  );

  useEffect(() => reload(view), [view, reload]);

  async function triage(
    n: AppNotification,
    patch: { unread?: boolean; status?: NotificationStatus },
  ) {
    setError(null);
    try {
      await notificationsApi.triage(n.id, patch);
      reload(view); // re-sync list (item may leave the current view) + badge
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar.");
    }
  }

  function open(n: AppNotification) {
    if (n.unread) void notificationsApi.triage(n.id, { unread: false }).catch(() => {});
    navigate(n.link || "/");
  }

  async function readAll() {
    setError(null);
    try {
      await notificationsApi.readAll();
      reload(view);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao marcar como lidas.");
    }
  }

  return (
    <div className="mx-auto h-full max-w-3xl space-y-4 overflow-y-auto px-4 py-6">
      <h1 className="text-lg font-semibold text-zinc-100">Inbox</h1>
      <FormError message={error} />
      <div className="flex items-center gap-1">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            type="button"
            onClick={() => setView(v.key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              view === v.key ? "bg-zinc-800 text-zinc-50" : "text-zinc-400 hover:text-zinc-50"
            }`}
          >
            {v.label}
          </button>
        ))}
        <button
          type="button"
          onClick={readAll}
          className="ml-auto rounded-md px-2.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-50"
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
            <NotificationRow key={n.id} n={n} onOpen={open} onTriage={triage} />
          ))}
        </ul>
      )}
    </div>
  );
}
