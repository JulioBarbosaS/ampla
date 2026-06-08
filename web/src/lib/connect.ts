/**
 * Token de conexão lido pelo `amp connect <token>` do bridge: base64url de
 * {hub_url, agent_id, key}. Empacotamento no cliente — o hub não muda.
 * Formato espelhado em bridge/src/cli/connect.ts (connectTokenSchema).
 */
export function connectToken(hubUrl: string, agentId: string, key: string): string {
  const json = JSON.stringify({ hub_url: hubUrl, agent_id: agentId, key });
  // base64url: btoa dá base64 padrão; troca +/ por -_ e tira o padding.
  return btoa(unescape(encodeURIComponent(json)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}
