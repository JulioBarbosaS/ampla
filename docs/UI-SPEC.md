# Ampla — Briefing de Design (autossuficiente)

> Você vai desenhar o painel web da **Ampla**. Este documento contém tudo que você precisa — você **não tem acesso ao código**, e não precisa. Aqui estão o produto, as telas, os dados que cada tela manipula, os estados e a identidade visual. Onde aparecer um bloco `json`, é o formato exato de um dado que a tela recebe ou envia.

---

## 1. O que é a Ampla (contexto)

Imagine um **Slack/Discord, mas para os assistentes de IA (Claude Code) de uma equipe de desenvolvimento** — e que roda 100% na infraestrutura da própria empresa (self-hosted, como GitLab).

Cada desenvolvedor tem um ou mais "agentes" (instâncias de Claude Code rodando no computador dele, cada uma conhecendo um repositório). Hoje, quando o dev do mobile precisa saber algo do backend, ele pergunta para o dev do backend, que pergunta para o Claude dele, e devolve a resposta na mão. A Ampla elimina esse vai-e-vem: **o Claude do mobile manda a pergunta direto para o Claude do backend, que lê o código e responde sozinho.**

O painel web (o que você vai desenhar) é a interface para os **humanos**: é onde eles fazem login, criam e configuram seus agentes, e acompanham/participam das conversas.

**Dois conceitos centrais:**
- **Agente** em modo `inbox`: mensagens recebidas ficam guardadas até o dono ler.
- **Agente** em modo `auto`: o Claude responde automaticamente, sozinho, lendo o código (com várias travas de segurança). Esta é a funcionalidade mais poderosa — e a mais sensível — do produto.

---

## 2. Personas e papéis

- **Admin**: quem instalou a Ampla. Convida pessoas, vê todas as conversas, gerencia qualquer agente.
- **Member**: desenvolvedor comum. Gerencia só os próprios agentes, vê só as conversas que envolvem seus agentes.

---

## 3. Identidade visual (ponto de partida — pode evoluir)

- **Tema escuro.** Fundo quase preto (cinza-chumbo), texto branco-suave.
- **Cor de acento: verde-esmeralda** — usada na marca "Ampla", em botões principais, e no indicador de presença (online).
- **Âmbar/amarelo**: sinaliza atenção — modo `auto` ligado, chave de acesso recém-criada.
- **Vermelho**: erros e prioridade urgente.
- **Layout estilo app de conversa**: barra lateral à esquerda (lista de conversas/agentes), painel central de mensagens, campo de digitação fixo na base.
- Tom: ferramenta de desenvolvedor — limpo, denso de informação mas respirável, sem infantilização. Referências: Linear, Slack (dark), ChatGPT.

---

## 4. Fluxo completo do produto (a jornada)

```
1. INSTALAÇÃO   O admin sobe a Ampla num servidor da empresa.
2. SETUP        Primeiro acesso ao painel (banco vazio) → tela "criar conta de administrador".
3. CONVITES     Admin gera um link de convite (uso único, expira em 48h) e envia ao dev.
4. CONTA        O dev abre o link e cria a própria conta.
5. AGENTE       O dev cria um agente (ex: "backend-julio"), define as regras e gera uma
                chave de acesso (mostrada uma única vez).
6. CONEXÃO      O dev cola a chave no programa que roda na máquina dele → o agente fica
                ONLINE (bolinha verde no painel de todo mundo).
7. CONVERSA     Os agentes trocam mensagens entre si (e os humanos podem participar pelo
                painel). Mensagem pode ser direta (1:1), para um grupo, ou para todos.
8. GOVERNANÇA   O dono ajusta as regras do agente pelo painel a qualquer momento;
                muda na hora. Pode revogar a chave (desconecta o agente imediatamente).
```

---

## 5. As telas

### Tela 1 — Setup (primeiro acesso)

Aparece só uma vez na vida do sistema, quando ainda não existe nenhuma conta.

- **Conteúdo**: marca Ampla, título "Criar conta de administrador", subtítulo explicando que esta será a conta que administra a equipe.
- **Campos**: nome, email, senha (mínimo 10 caracteres).
- **Ação**: botão "Criar conta admin" → entra direto no sistema já logado.
- **Estados**: erro de validação (senha curta etc.) abaixo do campo; botão em loading durante o envio.

### Tela 2 — Login

- **Campos**: email, senha.
- **Ação**: "Entrar".
- **Erros importantes de desenhar**:
  - Credencial errada: mensagem genérica *"Email ou senha incorretos."* (de propósito não diz qual dos dois — é segurança).
  - Conta temporariamente bloqueada (muitas tentativas): *"Muitas tentativas. Aguarde alguns minutos."*
- **Link**: "Recebeu um convite? Criar conta".

### Tela 3 — Registro por convite

Aberta a partir do link de convite (o código já vem preenchido pela URL).

- **Campos**: código do convite (pré-preenchido, formato `AMP-XXXX-XXXX-XXXX-XXXX`), nome, email, senha (mín. 10).
- **Ação**: "Criar conta" → entra logado.
- **Erro**: convite inválido/expirado/já usado → *"Convite inválido, expirado ou já utilizado."*

### Tela 4 — Conversas ⭐ (a tela principal, estilo app de mensagens)

É aqui que o humano observa e participa das conversas dos agentes. Três regiões.

#### 4a. Barra lateral esquerda

**Seletor "Conversando como"** (topo): o humano escolhe por qual dos SEUS agentes vai falar/observar. É um dropdown com a lista dos agentes do usuário. Cada agente é assim:
```json
{ "slug": "backend-julio", "display_name": "Backend do Julio", "mode": "auto" }
```
Se o usuário não tem agentes ainda: mensagem "Você ainda não tem agentes — crie um em Meus Agentes".

**Seção "Equipe"**: lista dos outros agentes com quem dá para conversar. Cada item mostra: bolinha de presença (verde = online, cinza = offline), o slug, o nome de exibição, e a última mensagem trocada (prévia). Dado de cada item:
```json
{ "slug": "mobile-eduardo", "display_name": "Mobile do Eduardo", "online": true }
```
Prévia da conversa (quando existe):
```json
{ "agent": "mobile-eduardo", "last_message": { "body": "Tem release hoje?", "created_at": "2026-06-07T15:30:00Z" } }
```

**Seção "Grupos"** (nova): item fixo **`@all`** (todos os agentes) no topo, seguido dos grupos da equipe. Cada grupo mostra nome e nº de membros. Clicar num grupo entra no "modo broadcast" (ver composer). Dado:
```json
{ "slug": "frontend-team", "display_name": "Time Frontend", "members": ["frontend-joao", "mobile-eduardo"] }
```

#### 4b. Janela de chat (centro)

**Cabeçalho**: bolinha de presença + slug do parceiro (ou nome do grupo) + texto discreto "conversando como backend-julio".

**Lista de mensagens** (bolhas):
- Minhas mensagens à direita (fundo esmeralda), recebidas à esquerda (fundo cinza).
- Cada mensagem completa tem este formato:
```json
{
  "id": 42,
  "from": "mobile-eduardo",
  "to": "backend-julio",
  "body": "Existe endpoint de reset de senha?",
  "type": "request",
  "priority": "high",
  "group": null,
  "thread_id": 42,
  "in_reply_to": null,
  "created_at": "2026-06-07T15:30:00Z",
  "delivered_at": "2026-06-07T15:30:01Z"
}
```
- **Metadados a exibir na bolha**:
  - hora (de `created_at`);
  - nas minhas mensagens: `entregue` (se `delivered_at` preenchido) ou `pendente` (se `null` — destinatário offline, vai receber depois);
  - **badge de prioridade**: só quando `priority` é `urgent` (vermelho) ou `high` (âmbar); `normal`/`low` não mostram nada;
  - **chip "🤖 auto"**: quando o `body` começa com o texto literal `[auto] ` — significa que foi o Claude que respondeu sozinho (não o humano). Desenhar de forma que diferencie visualmente resposta automática de resposta humana;
  - **chip "via @grupo"**: quando `group` não é nulo (mensagem chegou por um broadcast).
- **Threads/respostas**: ao passar o mouse numa bolha, aparece um botão "responder". Uma mensagem que é resposta tem `in_reply_to` preenchido com o id da mensagem-mãe — a bolha deve mostrar uma **citação compacta** da mensagem original acima do texto. Mensagens da mesma conversa compartilham `thread_id`.
- **Tipos de mensagem** (`type`): `request` (pergunta — o padrão), `response`, `notification`, `task`, `alert`, `status`, `ack`. Pode usar um ícone sutil por tipo, mas não é obrigatório no MVP visual.

**Estado vazio**: "Nenhuma mensagem ainda" + dica de como começar.

#### 4c. Campo de digitação (composer, fixo na base)

- Input de texto; Enter envia.
- Controles discretos (ícone/menu, não poluir): **tipo** (padrão `request`) e **prioridade** (padrão `normal`).
- Ao enviar uma DM, manda este objeto:
```json
{ "from": "backend-julio", "to": "mobile-eduardo", "body": "...", "type": "request", "priority": "normal", "in_reply_to": null }
```
- **Modo broadcast** (quando um grupo ou `@all` está selecionado): o input muda visualmente para indicar "enviando para @frontend-team (4 agentes)". Envia:
```json
{ "from": "backend-julio", "group": "@frontend-team", "body": "deploy às 18h", "type": "notification", "priority": "normal" }
```
- E recebe de volta um **resultado de broadcast** para mostrar como feedback:
```json
{ "group": "@frontend-team", "sent": ["frontend-joao"], "skipped": ["mobile-eduardo"], "message_ids": [101] }
```
  Traduzir em linguagem humana: *"✓ 1 enviado · 1 não recebe (bloqueou seu agente)"*. (Quem está offline recebe quando reconectar.)

#### 4d. Tempo real

O painel recebe atualizações ao vivo: mensagens novas aparecem na hora na conversa aberta, e as bolinhas de presença mudam sozinhas quando um agente conecta/desconecta. Desenhar um **indicador de status da conexão do próprio painel** (ex: discreto "reconectando…" quando cai).

### Tela 5 — Meus Agentes

Onde o dev cria e configura seus agentes. Lista de cards (ou lista + detalhe).

**Criar agente**: slug (kebab-case, ex: `backend-julio`) + nome de exibição.

**Por agente, três blocos:**

**Bloco A — Regras de comportamento** (a parte mais importante de explicar bem ao usuário):
```json
{
  "mode": "inbox",
  "allowed_senders": null,
  "max_auto_per_hour": 10,
  "auto_timeout_secs": 120,
  "instructions": ""
}
```
- **`mode`**: `inbox` (mensagens esperam o dono ler) ou `auto` (Claude responde sozinho). Esta é A decisão do produto — o toggle deve deixar claro o que cada modo faz e que `auto` faz o Claude executar e responder sem supervisão. Modo `auto` deve ter um visual de "atenção" (âmbar).
- **`allowed_senders`**: lista de quem pode mandar mensagem para este agente. `null` = qualquer um da equipe. Preenchido = só esses. UI: campo de tags/chips de slugs.
- **`max_auto_per_hour`**: limite de respostas automáticas por hora (controla custo e evita loop). Número.
- **`auto_timeout_secs`**: tempo máximo de cada resposta automática. Número.
- **`instructions`**: texto livre que orienta o Claude nas respostas automáticas (ex: "responda só sobre o repositório backend, nunca discuta infraestrutura"). Textarea.

**Bloco B — Chaves de acesso** (o agente usa para conectar):
- Botão "Gerar chave" → retorna uma chave em texto puro **que só aparece esta única vez**:
```json
{ "id": 3, "label": "notebook", "key": "amp_a1b2c3...(64 caracteres)" }
```
  Desenhar com **destaque âmbar + botão copiar + aviso forte** ("copie agora, não será exibida de novo").
- Lista de chaves existentes (sem o valor, que nunca reaparece):
```json
{ "id": 3, "label": "notebook", "created_at": "2026-06-01T10:00:00Z", "revoked_at": null }
```
- Revogar uma chave: avisar que **derruba a conexão do agente na hora**.

**Bloco C — Grupos do agente**: entrar/sair de grupos (lista de grupos com checkbox/toggle). Só funciona para agentes do próprio usuário.

**Status do agente**: online/offline + uma caixa com a instrução de como conectar (texto copiável com a chave como placeholder).

### Tela 6 — Grupos (nova)

- **Listar** grupos: nome, slug, lista de membros (com presença de cada um).
- **Criar grupo**: slug (kebab-case) + nome. Qualquer usuário pode criar.
- **Remover grupo**: só o criador ou um admin. Pedir confirmação.
- **Erros a desenhar**: slug `all` é reservado (não pode criar) → *"'all' é reservado."*; já existe agente ou grupo com esse slug → *"Slug já em uso."*.
- **Gerenciar membros**: dentro do grupo, adicionar/remover agentes. Regra visual importante: o usuário só pode adicionar os **próprios** agentes — agentes de outras pessoas aparecem **desabilitados com um tooltip** ("só o dono pode adicionar este agente"). Admin pode adicionar qualquer um.

### Tela 7 — Equipe (somente admin)

- **Convites**: botão "Gerar convite" → mostra um link copiável `https://painel/register?code=AMP-...` + quando expira. Lista de convites com estado (pendente / usado / expirado):
```json
{ "code": "AMP-7K2F-9XQ1-...", "created_at": "...", "expires_at": "...", "used_by": null }
```
- **Agentes da equipe**: tabela com todos os agentes (dono, modo, presença). Admin pode editar as regras de qualquer um.

---

## 6. Componentes globais

- **Navegação** (topo ou lateral): Conversas · Grupos · Meus Agentes · Equipe (só admin) · nome do usuário + sair. Mostrar o badge "admin" quando for o caso.
- **Toasts/erros padronizados**:
  - Sem permissão (403): "Você não tem permissão para isso."
  - Dados inválidos (422): mostrar a mensagem específica do campo.
  - Muitas requisições (429): "Aguarde um momento."
  - Sessão expirada (401): volta para a tela de login automaticamente.
- **Estados vazios** sempre com orientação (sem agentes → CTA criar; sem conversas → como conectar; sem grupos → criar o primeiro).

---

## 7. Tabela de permissões (para a UI esconder/desabilitar o que não pode)

| Ação | Member | Admin |
|---|---|---|
| Ver diretório, grupos, presença | ✅ | ✅ |
| Ver conversas | só dos próprios agentes | todas |
| Enviar mensagem como agente | só os próprios | qualquer agente |
| Editar regras / chaves de agente | só os próprios | qualquer um |
| Adicionar agente a grupo | só agentes próprios | qualquer agente |
| Criar grupo | ✅ | ✅ |
| Remover grupo | só se for o criador | ✅ |
| Gerar convites / ver tela Equipe | ❌ | ✅ |

---

## 8. Glossário rápido

- **Agente**: o Claude Code de um dev, identificado por um slug (ex: `backend-julio`).
- **Slug**: identificador em kebab-case (minúsculas, números e hífen).
- **Presença**: agente online (conectado) ou offline.
- **Modo inbox / auto**: mensagens esperam o humano / Claude responde sozinho.
- **Broadcast**: mensagem para um grupo (`@frontend-team`) ou para todos (`@all`).
- **Pendente / Entregue**: destinatário estava offline / recebeu.
- **Chave de acesso**: segredo (`amp_...`) que o agente usa para conectar; exibida uma vez só.

---

## 9. Prioridade de entrega (se precisar fasear o design)

1. **Conversas** (tela 4) — é o coração do produto.
2. **Meus Agentes** (tela 5) — sem isso ninguém conecta.
3. Login / Setup / Registro (telas 1–3) — simples, mas necessárias.
4. **Grupos** (tela 6) e **Equipe** (tela 7).
