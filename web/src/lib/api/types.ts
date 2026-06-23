/** Types for the hub's REST contracts (hub/app/schemas/*). */

export interface User {
  id: number;
  email: string;
  name: string;
  role: "admin" | "member";
  created_at: string;
}

export interface TokenResponse {
  token: string;
  user: User;
}

export interface AgentSettings {
  mode: "inbox" | "auto";
  allowed_senders: string[] | null;
  max_auto_per_hour: number;
  auto_timeout_secs: number;
  instructions: string;
  // Auto-respond filesystem guardrails
  allow_write: boolean;
  block_hidden_files: boolean;
  block_sensitive_paths: boolean;
  confine_to_dir: boolean;
  denied_paths: string[];
  trusted_senders: string[];
  // Fast brake: pause auto-respond without changing `mode` (Epic 03 · 3.2).
  auto_paused: boolean;
  // Daily auto-respond budget (Epic 03 · 3.4). null = unlimited.
  max_auto_tokens_per_day: number | null;
  max_auto_cost_usd_per_day: number | null;
  // Human-in-the-loop approval (Epic 03 · 3.3): draft, don't send, until approved.
  require_approval: boolean;
  // Availability window / DND (Epic 04 · 4.2): null = always-on.
  auto_schedule: AutoSchedule | null;
}

/** Recurring availability window. days are ISO weekdays (1=Mon..7=Sun);
 * start/end are HH:MM in the schedule's timezone. */
export interface ScheduleWindow {
  days: number[];
  start: string;
  end: string;
}

export interface AutoSchedule {
  tz: string;
  windows: ScheduleWindow[];
}

/** Guardrail/auto subset carried by a preset (Epic 04 · 4.1). */
export interface PresetSettings {
  mode: "inbox" | "auto";
  max_auto_per_hour: number;
  auto_timeout_secs: number;
  allow_write: boolean;
  block_hidden_files: boolean;
  block_sensitive_paths: boolean;
  confine_to_dir: boolean;
  denied_paths: string[];
  trusted_senders: string[];
  require_approval: boolean;
  auto_paused: boolean;
  max_auto_tokens_per_day: number | null;
  max_auto_cost_usd_per_day: number | null;
}

export interface Preset {
  id: number;
  owner_id: number | null; // null = built-in
  name: string;
  settings: PresetSettings;
  created_at: string;
}

/** A scheduled agent task (Epic 08): the agent wakes on a schedule and runs a
 * trusted, owner-authored prompt. `tools` = "write" is the danger-zone case. */
export type ScheduleKind = "cron" | "interval" | "once";

export interface ScheduledTask {
  id: number;
  owner_id: number;
  agent_slug: string;
  name: string;
  kind: ScheduleKind;
  spec: string;
  prompt: string;
  tools: "read" | "write";
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  last_status: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export type DelegationStatus = "open" | "completed" | "declined";

/** An agent-to-agent task hand-off (Epic 04 · 4.4). */
export interface Delegation {
  id: number;
  from_agent: string;
  to_agent: string;
  task: string;
  root_message_id: number | null;
  result_message_id: number | null;
  status: DelegationStatus;
  created_at: string;
  updated_at: string;
}

export type ApprovalStatus = "pending" | "approved" | "rejected" | "edited";

export interface Approval {
  id: number;
  agent_slug: string;
  trigger_message_id: number | null;
  to_agent: string;
  draft_body: string;
  status: ApprovalStatus;
  decided_by: number | null;
  decided_at: string | null;
  created_at: string;
}

/** Auto-respond outcomes that can be routed to the owner's Inbox (Epic 04 · 4.3).
 * Mirrors the hub's ESCALATE_OUTCOMES. The `__ESCALATE__` sentinel always
 * escalates and is not user-configurable, so it is not listed here. */
export type EscalateOutcome =
  | "failed"
  | "blocked"
  | "rate_limited"
  | "budget_exceeded"
  | "outside_hours";

export interface Agent extends AgentSettings {
  slug: string;
  user_id: number;
  display_name: string;
  created_at: string;
  // Escalation routing (Epic 04 · 4.3): hub-side policy (not in the WS settings),
  // so it lives on the agent record, not in AgentSettings.
  escalate_on: EscalateOutcome[];
}

export interface DirectoryEntry {
  slug: string;
  display_name: string;
  online: boolean;
}

export interface KillSwitchState {
  auto_responder_enabled: boolean;
}

export type NotificationStatus = "inbox" | "saved" | "done";

/** Coarse delivery gate (the GitHub repo-watch analog). */
export type NotifyLevel = "all" | "mentions_and_direct" | "mute";

export interface NotificationPrefs {
  notify_level: NotifyLevel;
}

/** Fine per-thread override on top of the coarse level. */
export type SubscriptionState = "subscribed" | "ignored";

export interface NotificationSubscription {
  subject_key: string;
  state: SubscriptionState;
}

export interface AppNotification {
  id: number;
  subject_type: string;
  subject_key: string;
  agent_slug: string | null;
  reason: string;
  title: string;
  link: string;
  actor: string;
  unread: boolean;
  status: NotificationStatus;
  created_at: string;
  updated_at: string;
  last_read_at: string | null;
}

export interface AutorespondRun {
  id: number;
  agent_slug: string;
  trigger_message_id: number | null;
  from_sender: string;
  result: "replied" | "blocked" | "failed" | "skipped";
  reason: string | null;
  reply_preview: string;
  tools_allowed: string;
  tools_disallowed: string;
  guardrails: Record<string, unknown>;
  duration_ms: number;
  timed_out: boolean;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  created_at: string;
}

export interface AgentKey {
  id: number;
  label: string;
  created_at: string;
  revoked_at: string | null;
}

export interface AgentKeyCreated {
  id: number;
  label: string;
  key: string;
}

export interface Group {
  slug: string;
  display_name: string;
  created_by: number;
  created_at: string;
  members: string[];
}

export interface Invite {
  id: number;
  code: string;
  created_at: string;
  expires_at: string;
  used_by: number | null;
  used_at: string | null;
}

export type MessageType =
  | "request"
  | "response"
  | "notification"
  | "task"
  | "alert"
  | "status"
  | "ack";

export type Priority = "urgent" | "high" | "normal" | "low";

export interface Message {
  id: number;
  from: string;
  to: string;
  body: string;
  type: MessageType;
  priority: Priority;
  group: string | null;
  thread_id: number | null;
  in_reply_to: number | null;
  created_at: string;
  delivered_at: string | null;
  expires_at: string | null;
}

export interface ConversationPartner {
  agent: string;
  last_message: Message;
}

// ---- Kanban (Epic 06) ----

export interface KanbanBoard {
  id: number;
  owner_id: number;
  name: string;
  visibility: "team" | "private";
  default_agent_role: "none" | "viewer" | "contributor" | "editor";
  auto_card_on_delegation: boolean;
  auto_card_on_escalation: boolean;
  created_at: string;
}

export interface KanbanColumn {
  id: number;
  board_id: number;
  name: string;
  rank: string;
  wip_limit: number | null;
  is_landing: boolean;
  is_done: boolean;
}

export interface KanbanCard {
  id: number;
  board_id: number;
  column_id: number;
  rank: string;
  title: string;
  body: string;
  created_by: string;
  assignee: string | null;
  priority: Priority;
  origin: Record<string, unknown> | null;
  version: number;
  depends_on: number[];
  created_at: string;
  updated_at: string;
}

export interface KanbanComment {
  id: number;
  card_id: number;
  author: string;
  body: string;
  created_at: string;
}

export interface KanbanBoardFull {
  board: KanbanBoard;
  columns: KanbanColumn[];
  cards: KanbanCard[];
}

export interface KanbanGrant {
  board_id: number;
  agent_slug: string;
  role: "viewer" | "contributor" | "editor";
}

/** A card's `origin` resolved to a panel deep-link (Epic 07). */
export interface KanbanCardOrigin {
  kind: string | null;
  label: string;
  deep_link: string | null;
  available: boolean;
}

/** hub→panel live board delta (mirrors KanbanDeltaFrame). */
export interface KanbanDelta {
  board_id: number;
  op: "card_created" | "card_moved" | "card_updated" | "card_deleted" | "comment_added";
  card: KanbanCard | null;
  comment: KanbanComment | null;
}
