"""Sending with the allowlist enforced at the hub (Threat 3) and authorized history."""

from datetime import timedelta

from app.core.config import Settings
from app.models.message import Message
from app.models.user import User, utcnow
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.message import ConversationPartner, MessageOut
from app.services.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
)


class MessageService:
    def __init__(
        self,
        messages: MessageRepository,
        agents: AgentRepository,
        audit: AuditRepository,
        settings: Settings,
    ) -> None:
        self._messages = messages
        self._agents = agents
        self._audit = audit
        self._settings = settings

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

        return await self._messages.add(
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
