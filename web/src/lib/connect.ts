/**
 * Connection token read by the bridge's `amp connect <token>`: base64url of
 * {hub_url, agent_id, key}. Packed client-side — the hub does not change.
 * Format mirrored in bridge/src/cli/connect.ts (connectTokenSchema).
 */
export function connectToken(hubUrl: string, agentId: string, key: string): string {
  const json = JSON.stringify({ hub_url: hubUrl, agent_id: agentId, key });
  // base64url: btoa yields standard base64; swap +/ for -_ and strip padding.
  return btoa(unescape(encodeURIComponent(json)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}
