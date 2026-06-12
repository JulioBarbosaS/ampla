import { api } from "./client";
import type {
  Agent,
  AgentKey,
  AgentKeyCreated,
  Approval,
  ApprovalStatus,
  AutorespondRun,
  DirectoryEntry,
} from "./types";

export interface SettingsPatch {
  mode?: "inbox" | "auto";
  allowed_senders?: string[];
  clear_allowed_senders?: boolean;
  max_auto_per_hour?: number;
  auto_timeout_secs?: number;
  instructions?: string;
  allow_write?: boolean;
  block_hidden_files?: boolean;
  block_sensitive_paths?: boolean;
  confine_to_dir?: boolean;
  denied_paths?: string[];
  trusted_senders?: string[];
  auto_paused?: boolean;
  // 0 clears the cap (unlimited); a positive value sets the daily ceiling.
  max_auto_tokens_per_day?: number;
  max_auto_cost_usd_per_day?: number;
  require_approval?: boolean;
}

export const agentsApi = {
  mine: () => api.get<Agent[]>("/api/agents"),
  directory: () => api.get<DirectoryEntry[]>("/api/agents/directory"),
  create: (data: { slug: string; display_name: string }) => api.post<Agent>("/api/agents", data),
  updateSettings: (slug: string, patch: SettingsPatch) =>
    api.patch<Agent>(`/api/agents/${slug}/settings`, patch),
  createKey: (slug: string, label = "") =>
    api.post<AgentKeyCreated>(`/api/agents/${slug}/keys`, { label }),
  listKeys: (slug: string) => api.get<AgentKey[]>(`/api/agents/${slug}/keys`),
  revokeKey: (slug: string, keyId: number) =>
    api.delete<AgentKey>(`/api/agents/${slug}/keys/${keyId}`),
  autorespondRuns: (slug: string, limit = 50) =>
    api.get<AutorespondRun[]>(`/api/agents/${slug}/autorespond-runs?limit=${limit}`),
  approvals: (slug: string, status: ApprovalStatus = "pending") =>
    api.get<Approval[]>(`/api/agents/${slug}/approvals?status=${status}`),
  decideApproval: (id: number, decision: "approve" | "reject", body?: string) =>
    api.post<Approval>(`/api/approvals/${id}/decision`, body ? { decision, body } : { decision }),
};
