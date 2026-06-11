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
