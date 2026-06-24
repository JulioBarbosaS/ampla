"""Sending with the allowlist enforced at the hub (Threat 3) and authorized history."""

import logging
from datetime import timedelta

from app.core.config import Settings
from app.core.mentions import parse_mentions
from app.models.agent import Agent
from app.models.message import Message
from app.models.user import User, utcnow
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.delegation_repo import DelegationRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.message import ConversationPartner, MessageOut
from app.services.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
)
from app.services.kanban_service import KanbanService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# Message types that notify the recipient's owner as a direct message.
_DM_TYPES = frozenset({"request", "notification", "alert"})


class MessageService:
    def __init__(
        self,
        messages: MessageRepository,
        agents: AgentRepository,
        audit: AuditRepository,
        settings: Settings,
        notifications: NotificationService | None = None,
        delegations: DelegationRepository | None = None,
        kanban: KanbanService | None = None,
    ) -> None:
        self._messages = messages
        self._agents = agents
        self._audit = audit
        self._settings = settings
        self._notifications = notifications
        self._delegations = delegations
        # Lifecycle: a completed delegation moves its event card to Done (Epic 07).
        self._kanban = kanban

    async def send(
        self,
        from_slug: str,
        to_slug: str,
        body: str,
        *,
        type: str = "request",
        priority: str = "normal",
        in_reply_to: int | None = None,
        group: str | None = None,
    ) -> Message:
        if not body.strip():
            raise InvalidInputError("Mensagem vazia.")
        if len(body.encode()) > self._settings.message_max_body_bytes:
            raise InvalidInputError(
                f"Mensagem excede {self._settings.message_max_body_bytes} bytes."
            )
        if from_slug == to_slug:
            raise InvalidInputError("Remetente e destinatário são o mesmo agente.")

        recipient = await self._agents.get(to_slug)
        if recipient is None:
            raise NotFoundError(f"Agente {to_slug!r} não existe.")

        # Recipient's allowlist — the authority is the hub, never the daemon
        if recipient.allowed_senders is not None and from_slug not in recipient.allowed_senders:
            await self._audit.record(
                "message_blocked_allowlist",
                actor=from_slug,
                detail={"to": to_slug},
            )
            raise PermissionDeniedError(f"{to_slug!r} não aceita mensagens deste agente.")

        # Threading: a reply inherits the thread of the referenced message,
        # which must belong to the SAME conversation (anti cross-thread injection)
        thread_id: int | None = None
        if in_reply_to is not None:
            parent = await self._messages.get(in_reply_to)
            if parent is None or {parent.from_agent, parent.to_agent} != {from_slug, to_slug}:
                raise InvalidInputError("in_reply_to não pertence a esta conversa.")
            thread_id = parent.thread_id or parent.id

        message = await self._messages.add(
            Message(
                from_agent=from_slug,
                to_agent=to_slug,
                body=body,
                type=type,
                priority=priority,
                group_slug=group,
                thread_id=thread_id,
                in_reply_to=in_reply_to,
                expires_at=utcnow() + timedelta(days=self._settings.pending_ttl_days),
            )
        )
        await self._audit_security_send(message, recipient)
        await self._generate_notifications(message, recipient)
        # A reply may answer a delegated task (Epic 04 · 4.4) — close the loop.
        if in_reply_to is not None:
            await self._maybe_complete_delegation(message)
        return message

    async def _audit_security_send(self, message: Message, recipient: Agent) -> None:
        """Audit only sends with security weight (audit_log = the trail of notable
        actions, not raw traffic): an `alert`, or a message crossing ownership
        boundaries (one user's agent → another's). Routine same-owner DMs live in
        the `messages` table alone; broadcast is already audited as `broadcast_sent`."""
        if message.group_slug is not None:
            return  # broadcast — covered by broadcast_sent
        sender = await self._agents.get(message.from_agent)
        cross_owner = sender is not None and sender.user_id != recipient.user_id
        if message.type == "alert" or cross_owner:
            await self._audit.record(
                "message_sent",
                actor=message.from_agent,
                detail={"to": message.to_agent, "type": message.type, "cross_owner": cross_owner},
            )

    async def _maybe_complete_delegation(self, message: Message) -> None:
        """If this reply answers a delegated task (delegate → delegator, in the
        delegated thread), mark the delegation completed and notify the delegator.
        Best-effort: the reply is already committed, so a failure here must never
        propagate and drop it."""
        if self._delegations is None or message.thread_id is None:
            return
        try:
            delegation = await self._delegations.find_open_for_reply(
                delegator=message.to_agent,
                delegate=message.from_agent,
                root_message_id=message.thread_id,
            )
            if delegation is None:
                return
            delegation.status = "completed"
            delegation.result_message_id = message.id
            delegation.updated_at = utcnow()
            await self._delegations.save(delegation)
            # Lifecycle (Epic 07): move the delegation's event card to Done. No-op
            # if no board opted in (no card exists) or the card is blocked.
            if self._kanban is not None:
                await self._kanban.complete_card_for_event(kind="delegation", ref_id=delegation.id)
            if self._notifications is not None:
                delegator = await self._agents.get(delegation.from_agent)
                if delegator is not None:
                    await self._notifications.notify(
                        delegator.user_id,
                        subject_type="dm",
                        subject_key=f"dm:{delegation.from_agent}:{delegation.to_agent}",
                        reason="task_assigned",
                        title=f"{delegation.to_agent} respondeu à tarefa que você delegou",
                        link=(
                            f"/?perspective={delegation.from_agent}"
                            f"&partner={delegation.to_agent}&msg={message.id}"
                        ),
                        actor=delegation.to_agent,
                        agent_slug=delegation.from_agent,
                    )
        except Exception:
            logger.warning("delegation completion failed for message %s", message.id, exc_info=True)

    async def _generate_notifications(self, message: Message, recipient: Agent) -> None:
        """Inbox notifications (Epic 02) as a side effect of a send. Best-effort:
        the message is already committed, so a notification failure must never
        propagate and drop it."""
        if self._notifications is None:
            return
        try:
            convo_link = (
                f"/?perspective={message.to_agent}&partner={message.from_agent}&msg={message.id}"
            )
            # Recipient's owner: a DM / task / broadcast to their agent. Collapse
            # per conversation (recipient-agent + sender), not per message.
            if message.group_slug:
                spec = (
                    "broadcast",
                    "broadcast",
                    f"{message.from_agent} transmitiu para {message.group_slug}",
                )
            elif message.type == "task":
                spec = (
                    "task",
                    "task_assigned",
                    f"{message.from_agent} atribuiu uma tarefa a {message.to_agent}",
                )
            elif message.type in _DM_TYPES:
                spec = (
                    "dm",
                    "direct_message",
                    f"{message.from_agent} enviou uma mensagem para {message.to_agent}",
                )
            else:
                spec = None  # response/status/ack are low-signal — no recipient notification
            if spec is not None:
                subject_type, reason, title = spec
                await self._notifications.notify(
                    recipient.user_id,
                    subject_type=subject_type,
                    subject_key=f"dm:{message.to_agent}:{message.from_agent}",
                    reason=reason,
                    title=title,
                    link=convo_link,
                    actor=message.from_agent,
                    agent_slug=message.to_agent,
                )
            # @mentions in the body notify each mentioned agent's owner.
            for slug in parse_mentions(message.body):
                if slug in (message.from_agent, message.to_agent):
                    continue  # sender self-mention / recipient already covered above
                mentioned = await self._agents.get(slug)
                if mentioned is None:
                    continue
                await self._notifications.notify(
                    mentioned.user_id,
                    subject_type="mention",
                    subject_key=f"dm:{slug}:{message.from_agent}",
                    reason="mention",
                    title=f"{message.from_agent} mencionou @{slug}",
                    link=f"/?perspective={slug}&partner={message.from_agent}&msg={message.id}",
                    actor=message.from_agent,
                    agent_slug=slug,
                )
        except Exception:
            logger.warning(
                "notification generation failed for message %s", message.id, exc_info=True
            )

    async def send_broadcast(
        self,
        from_slug: str,
        group_ref: str,
        recipients: list[str],
        body: str,
        *,
        type: str = "request",
        priority: str = "normal",
    ) -> tuple[list[Message], list[str]]:
        """Fan-out: one DM per recipient, reusing the entire send() pipeline.
        The recipient's allowlist wins over the broadcast → goes to `skipped`.
        Returns (created messages, skipped slugs)."""
        if not recipients:
            raise InvalidInputError(f"{group_ref!r} não tem outros membros para receber.")
        sent: list[Message] = []
        skipped: list[str] = []
        for recipient in recipients:
            try:
                message = await self.send(
                    from_slug, recipient, body, type=type, priority=priority, group=group_ref
                )
            except PermissionDeniedError:
                skipped.append(recipient)  # recipient's allowlist — already audited in send()
                continue
            sent.append(message)
        await self._audit.record(
            "broadcast_sent",
            actor=from_slug,
            detail={"group": group_ref, "sent": len(sent), "skipped": len(skipped)},
        )
        return sent, skipped

    async def send_as_user(
        self,
        actor: User,
        from_slug: str,
        to_slug: str,
        body: str,
        *,
        type: str = "request",
        priority: str = "normal",
        in_reply_to: int | None = None,
    ) -> Message:
        """A human sends on behalf of their own agent (panel). An admin can send for anyone."""
        await self._assert_sender_owned(actor, from_slug)
        return await self.send(
            from_slug, to_slug, body, type=type, priority=priority, in_reply_to=in_reply_to
        )

    async def broadcast_as_user(
        self,
        actor: User,
        from_slug: str,
        group_ref: str,
        recipients: list[str],
        body: str,
        *,
        type: str = "request",
        priority: str = "normal",
    ) -> tuple[list[Message], list[str]]:
        await self._assert_sender_owned(actor, from_slug)
        return await self.send_broadcast(
            from_slug, group_ref, recipients, body, type=type, priority=priority
        )

    async def assert_sender_owned(self, actor: User, from_slug: str) -> None:
        """Public: authorize that `actor` owns `from_slug` (or is admin). Lets a
        route verify ownership BEFORE consuming a per-agent rate limit, so a client
        can't exhaust another agent's bucket by naming it (anti-spoof)."""
        await self._assert_sender_owned(actor, from_slug)

    async def _assert_sender_owned(self, actor: User, from_slug: str) -> None:
        sender = await self._agents.get(from_slug)
        if sender is None:
            raise NotFoundError(f"Agente {from_slug!r} não existe.")
        if sender.user_id != actor.id and actor.role != "admin":
            raise PermissionDeniedError("Você não envia mensagens por este agente.")

    # ---- delivery ----

    async def pending_for(self, slug: str) -> list[Message]:
        return await self._messages.pending_for(slug)

    async def mark_delivered(self, message_ids: list[int]) -> None:
        await self._messages.mark_delivered(message_ids)

    async def ack_delivery(self, recipient_slug: str, message_id: int) -> Message | None:
        """Confirms delivery (at-least-once). Only the recipient itself can ack
        its own message (Threat 3: a daemon cannot mark someone else's message
        as delivered). Sets `delivered_at` the first time and returns the
        message so the hub can notify the sender; ack from another/nonexistent → None.
        Idempotent: a re-ack just returns the already-delivered message."""
        msg = await self._messages.get(message_id)
        if msg is None or msg.to_agent != recipient_slug:
            return None
        if msg.delivered_at is None:
            msg.delivered_at = utcnow()
            await self._messages.save(msg)
        return msg

    # ---- history (owner sees their own agents' conversations; admin sees everything) ----

    async def conversation(
        self, actor: User, agent_a: str, agent_b: str, limit: int = 50
    ) -> list[Message]:
        await self._authorize_view(actor, {agent_a, agent_b})
        return await self._messages.conversation(agent_a, agent_b, limit=min(limit, 200))

    async def partners(self, actor: User, slug: str) -> list[ConversationPartner]:
        """List of the agent's conversations with the last message (sidebar)."""
        await self._authorize_view(actor, {slug})
        recent = await self._messages.involving([slug])
        partners: dict[str, Message] = {}
        for msg in recent:  # recent comes in descending order
            other = msg.to_agent if msg.from_agent == slug else msg.from_agent
            partners.setdefault(other, msg)
        return [
            ConversationPartner(agent=other, last_message=MessageOut.model_validate(msg))
            for other, msg in partners.items()
        ]

    async def _authorize_view(self, actor: User, slugs: set[str]) -> None:
        if actor.role == "admin":
            return
        owned = {agent.slug for agent in await self._agents.list_by_user(actor.id)}
        if not (owned & slugs):
            raise PermissionDeniedError("Você não participa desta conversa.")

    # ---- origin resolution (Epic 07: surface a card's source conversation) ----

    async def resolve_origin(self, actor: User, origin: dict | None) -> dict:
        """Resolve a kanban card's `origin` into a panel deep-link the viewer is
        authorized to open. Conversation authorization lives here (MessageService
        owns conversations/delegations), so a card on a shared board can never leak
        a private conversation: an unauthorized or vanished source resolves to
        `available: false` (never an error, never an existence leak)."""
        kind = origin.get("kind") if isinstance(origin, dict) else None
        if kind is None:
            return _origin_out(None, "Sem origem", None, available=False)
        try:
            if kind == "delegation":
                deleg = await self._delegations.get(origin["id"]) if self._delegations else None
                if deleg is None:
                    return _origin_out(kind, "Delegação indisponível", None, available=False)
                await self._authorize_view(actor, {deleg.from_agent, deleg.to_agent})
                link = f"/?perspective={deleg.from_agent}&partner={deleg.to_agent}"
                if deleg.root_message_id is not None:
                    link += f"&msg={deleg.root_message_id}"
                return _origin_out(kind, f"Delegação para {deleg.to_agent}", link)
            if kind == "escalation":
                agent, sender = origin.get("agent"), origin.get("from")
                if not agent or not sender:
                    return _origin_out(kind, "Escalação", None, available=False)
                await self._authorize_view(actor, {agent, sender})
                return _origin_out(
                    kind, f"Escalação de {sender}", f"/?perspective={agent}&partner={sender}"
                )
            if kind in ("message", "thread"):
                msg = await self._messages.get(origin["id"])
                if msg is None:
                    return _origin_out(kind, "Conversa indisponível", None, available=False)
                await self._authorize_view(actor, {msg.from_agent, msg.to_agent})
                link = f"/?perspective={msg.to_agent}&partner={msg.from_agent}&msg={msg.id}"
                return _origin_out(kind, "Conversa", link)
        except (PermissionDeniedError, KeyError, TypeError):
            return _origin_out(kind, "Origem indisponível", None, available=False)
        return _origin_out(kind, "Origem desconhecida", None, available=False)


def _origin_out(
    kind: str | None, label: str, deep_link: str | None, *, available: bool = True
) -> dict:
    return {"kind": kind, "label": label, "deep_link": deep_link, "available": available}
