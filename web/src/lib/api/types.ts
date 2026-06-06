/** Tipos dos contratos REST do hub (hub/app/schemas/*). */

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
