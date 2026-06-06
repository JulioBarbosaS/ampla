"""Repositories fake em memória — mesma interface dos reais.

SQLAlchemy só aplica defaults de coluna no flush; os fakes os aplicam
no `add` para que os models se comportem como persistidos.
"""

from datetime import datetime

from app.models.agent import Agent, AgentKey
from app.models.message import Message
from app.models.user import Invite, User, utcnow


def _default(obj, attr: str, value) -> None:
    if getattr(obj, attr) is None:
        setattr(obj, attr, value)


class FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict | None]] = []

    async def record(self, event: str, actor: str = "", detail: dict | None = None) -> None:
        self.events.append((event, actor, detail))

    def has(self, event: str) -> bool:
        return any(e[0] == event for e in self.events)


class FakeUserRepository:
    def __init__(self) -> None:
        self._users: dict[int, User] = {}
        self._seq = 0

    async def count(self) -> int:
        return len(self._users)

    async def get_by_id(self, user_id: int) -> User | None:
        return self._users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._users.values() if u.email == email), None)

    async def add(self, user: User) -> User:
        self._seq += 1
        user.id = self._seq
        _default(user, "role", "member")
        _default(user, "failed_logins", 0)
        _default(user, "created_at", utcnow())
        self._users[user.id] = user
        return user

    async def save(self, user: User) -> None:
        self._users[user.id] = user


class FakeInviteRepository:
    def __init__(self) -> None:
        self._invites: dict[int, Invite] = {}
        self._seq = 0

    async def add(self, invite: Invite) -> Invite:
        self._seq += 1
        invite.id = self._seq
        _default(invite, "created_at", utcnow())
        self._invites[invite.id] = invite
        return invite

    async def get_by_code(self, code: str) -> Invite | None:
        return next((i for i in self._invites.values() if i.code == code), None)

    async def list_all(self) -> list[Invite]:
        return sorted(self._invites.values(), key=lambda i: i.created_at, reverse=True)

    async def save(self, invite: Invite) -> None:
        self._invites[invite.id] = invite


class FakeAgentRepository:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._keys: dict[int, AgentKey] = {}
        self._key_seq = 0

    async def get(self, slug: str) -> Agent | None:
        return self._agents.get(slug)

    async def list_by_user(self, user_id: int) -> list[Agent]:
        return sorted(
            (a for a in self._agents.values() if a.user_id == user_id), key=lambda a: a.slug
        )

    async def list_all(self) -> list[Agent]:
        return sorted(self._agents.values(), key=lambda a: a.slug)

    async def add(self, agent: Agent) -> Agent:
        _default(agent, "mode", "inbox")
        _default(agent, "max_auto_per_hour", 10)
        _default(agent, "auto_timeout_secs", 120)
        _default(agent, "instructions", "")
        _default(agent, "created_at", utcnow())
        self._agents[agent.slug] = agent
        return agent

    async def save(self, agent: Agent) -> None:
        self._agents[agent.slug] = agent

    async def add_key(self, key: AgentKey) -> AgentKey:
        self._key_seq += 1
        key.id = self._key_seq
        _default(key, "label", "")
        _default(key, "created_at", utcnow())
        self._keys[key.id] = key
        return key

    async def get_key_by_hash(self, key_hash: str) -> AgentKey | None:
        return next((k for k in self._keys.values() if k.key_hash == key_hash), None)

    async def get_key(self, key_id: int) -> AgentKey | None:
        return self._keys.get(key_id)

    async def list_keys(self, agent_slug: str) -> list[AgentKey]:
        return sorted(
            (k for k in self._keys.values() if k.agent_slug == agent_slug),
            key=lambda k: k.created_at,
            reverse=True,
        )

    async def save_key(self, key: AgentKey) -> None:
        self._keys[key.id] = key


class FakeMessageRepository:
    def __init__(self) -> None:
        self._messages: dict[int, Message] = {}
        self._seq = 0

    async def add(self, message: Message) -> Message:
        self._seq += 1
        message.id = self._seq
        _default(message, "created_at", utcnow())
        self._messages[message.id] = message
        return message

    async def conversation(self, agent_a: str, agent_b: str, limit: int = 50) -> list[Message]:
        pair = {agent_a, agent_b}
        found = [
            m for m in self._messages.values() if {m.from_agent, m.to_agent} == pair
        ]
        found.sort(key=lambda m: (m.created_at, m.id), reverse=True)
        return found[:limit]

    async def pending_for(self, to_agent: str) -> list[Message]:
        found = [
            m
            for m in self._messages.values()
            if m.to_agent == to_agent and m.delivered_at is None
        ]
        found.sort(key=lambda m: (m.created_at, m.id))
        return found

    async def mark_delivered(self, message_ids: list[int], when: datetime | None = None) -> None:
        for message_id in message_ids:
            if message_id in self._messages:
                self._messages[message_id].delivered_at = when or utcnow()

    async def involving(self, agent_slugs: list[str], limit: int = 200) -> list[Message]:
        slugs = set(agent_slugs)
        found = [
            m
            for m in self._messages.values()
            if m.from_agent in slugs or m.to_agent in slugs
        ]
        found.sort(key=lambda m: (m.created_at, m.id), reverse=True)
        return found[:limit]
