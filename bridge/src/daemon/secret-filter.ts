/**
 * Filtro de saída do auto-respond (docs/ARCHITECTURE.md · Ameaça 1):
 * a resposta do Claude headless passa por aqui ANTES de ir ao hub.
 * Match ⇒ resposta bloqueada (nunca "limpada" — bloqueio total é mais seguro).
 */

interface SecretPattern {
  name: string;
  regex: RegExp;
}

const PATTERNS: SecretPattern[] = [
  { name: "private key (PEM)", regex: /-----BEGIN [A-Z ]*PRIVATE KEY-----/ },
  // sem \b final: pega a chave mesmo concatenada a outros chars (AKIA…X)
  { name: "AWS access key", regex: /\bAKIA[0-9A-Z]{16}/ },
  { name: "chave de agente AMP", regex: /\bamp_[0-9a-f]{64}\b/ },
  // gh{p,o,u,s,r}_ (clássico) e github_pat_ (fine-grained)
  { name: "GitHub token", regex: /\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})\b/ },
  { name: "Anthropic API key", regex: /\bsk-ant-[A-Za-z0-9-_]{20,}\b/ },
  { name: "OpenAI API key", regex: /\bsk-[A-Za-z0-9]{40,}\b/ },
  { name: "Slack token", regex: /\bxox[abposr]-[A-Za-z0-9-]{10,}\b/ },
  { name: "JWT", regex: /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/ },
  {
    // usuário opcional ([^\s:]* aceita "redis://:senha@…")
    name: "connection string com senha",
    regex: /\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp):\/\/[^\s:]*:[^\s@]+@/i,
  },
  {
    // case-insensitive: pega DATABASE_PASSWORD= e também database_password=
    name: "atribuição de segredo (.env)",
    regex:
      /^\s*(?:export\s+)?[A-Za-z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY|CREDENTIALS)[A-Za-z0-9_]*\s*=\s*\S/im,
  },
];

export interface SecretScanResult {
  clean: boolean;
  matches: string[];
}

export function scanForSecrets(text: string): SecretScanResult {
  const matches = PATTERNS.filter((p) => p.regex.test(text)).map((p) => p.name);
  return { clean: matches.length === 0, matches };
}
