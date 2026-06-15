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

export interface Agent extends AgentSettings {
  slug: string;
  user_id: number;
  display_name: string;
  created_at: string;
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
