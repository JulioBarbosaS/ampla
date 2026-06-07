"""Envio com allowlist aplicada no hub (Ameaça 3) e histórico autorizado."""

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

        # Allowlist do destinatário — autoridade é o hub, nunca o daemon
        if recipient.allowed_senders is not None and from_slug not in recipient.allowed_senders:
            await self._audit.record(
                "message_blocked_allowlist",
                actor=from_slug,
                detail={"to": to_slug},
            )
            raise PermissionDeniedError(f"{to_slug!r} não aceita mensagens deste agente.")

        # Threading: resposta herda a thread da mensagem referenciada,
        # que precisa pertencer à MESMA conversa (anti cross-thread injection)
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
        """Fan-out: uma DM por destinatário, reusando todo o pipeline de send().
        Allowlist do destinatário vence o broadcast → vai para `skipped`.
        Retorna (mensagens criadas, slugs pulados)."""
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
                skipped.append(recipient)  # allowlist do destinatário — já auditado em send()
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
        """Humano envia em nome do próprio agente (painel). Admin pode por qualquer um."""
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

    # ---- entrega ----

    async def pending_for(self, slug: str) -> list[Message]:
        return await self._messages.pending_for(slug)

    async def mark_delivered(self, message_ids: list[int]) -> None:
        await self._messages.mark_delivered(message_ids)

    async def ack_delivery(self, recipient_slug: str, message_id: int) -> Message | None:
        """Confirma a entrega (at-least-once). Só o próprio destinatário pode
        ackar a sua mensagem (Ameaça 3: um daemon não marca a mensagem de
        outro como entregue). Marca `delivered_at` na primeira vez e devolve a
        mensagem para o hub avisar o remetente; ack alheio/inexistente → None.
        Idempotente: re-ack apenas devolve a mensagem já entregue."""
        msg = await self._messages.get(message_id)
        if msg is None or msg.to_agent != recipient_slug:
            return None
        if msg.delivered_at is None:
            msg.delivered_at = utcnow()
            await self._messages.save(msg)
        return msg

    # ---- histórico (dono vê conversas dos próprios agentes; admin vê tudo) ----

    async def conversation(
        self, actor: User, agent_a: str, agent_b: str, limit: int = 50
    ) -> list[Message]:
        await self._authorize_view(actor, {agent_a, agent_b})
        return await self._messages.conversation(agent_a, agent_b, limit=min(limit, 200))

    async def partners(self, actor: User, slug: str) -> list[ConversationPartner]:
        """Lista de conversas do agente com a última mensagem (sidebar)."""
        await self._authorize_view(actor, {slug})
        recent = await self._messages.involving([slug])
        partners: dict[str, Message] = {}
        for msg in recent:  # recent vem em ordem decrescente
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
