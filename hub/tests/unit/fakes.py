"""In-memory fake repositories — same interface as the real ones.

SQLAlchemy only applies column defaults on flush; the fakes apply them
on `add` so the models behave as if persisted.
"""

from datetime import datetime

from app.models.agent import Agent, AgentKey
from app.models.autorespond_run import AutorespondRun
from app.models.group import Group
from app.models.hub_state import HubState
from app.models.message import Message
from app.models.notification import Notification
from app.models.user import Invite, PasswordReset, User, utcnow


class FakeGroupRepository:
    def __init__(self) -> None:
        self._groups: dict[str, Group] = {}
        self._members: dict[str, set[str]] = {}

    async def get(self, slug: str) -> Group | None:
        return self._groups.get(slug)

    async def list_all(self) -> list[Group]:
        return sorted(self._groups.values(), key=lambda g: g.slug)

    async def add(self, group: Group) -> Group:
        _default(group, "created_at", utcnow())
        self._groups[group.slug] = group
        self._members.setdefault(group.slug, set())
        return group

    async def remove(self, group: Group) -> None:
        self._groups.pop(group.slug, None)
        self._members.pop(group.slug, None)

    async def members_of(self, group_slug: str) -> list[str]:
        return sorted(self._members.get(group_slug, set()))

    async def is_member(self, group_slug: str, agent_slug: str) -> bool:
        return agent_slug in self._members.get(group_slug, set())

    async def add_member(self, group_slug: str, agent_slug: str) -> None:
        self._members.setdefault(group_slug, set()).add(agent_slug)

    async def remove_member(self, group_slug: str, agent_slug: str) -> None:
        self._members.get(group_slug, set()).discard(agent_slug)


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
        self._resets: dict[str, PasswordReset] = {}
        self._reset_seq = 0

    async def count(self) -> int:
        return len(self._users)

    async def count_admins(self) -> int:
        return sum(1 for u in self._users.values() if u.role == "admin")

    async def list_all(self) -> list[User]:
        return sorted(self._users.values(), key=lambda u: u.id)

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

    async def add_reset(self, reset: PasswordReset) -> PasswordReset:
        self._reset_seq += 1
        reset.id = self._reset_seq
        _default(reset, "created_at", utcnow())
        _default(reset, "used_at", None)
        self._resets[reset.token_hash] = reset
        return reset

    async def get_reset_by_hash(self, token_hash: str) -> PasswordReset | None:
        return self._resets.get(token_hash)

    async def save_reset(self, reset: PasswordReset) -> None:
        self._resets[reset.token_hash] = reset


class FakeHubStateRepository:
    def __init__(self) -> None:
        self._state = HubState(id=1, auto_responder_enabled=True)

    async def get(self) -> HubState:
        return self._state

    async def set_auto_responder_enabled(self, enabled: bool) -> HubState:
        self._state.auto_responder_enabled = enabled
        return self._state


class FakeAutorespondRunRepository:
    def __init__(self) -> None:
        self._runs: list[AutorespondRun] = []
        self._seq = 0
        self.last_limit: int | None = None  # records the clamped limit passed in

    async def add(self, run: AutorespondRun) -> AutorespondRun:
        self._seq += 1
        run.id = self._seq
        _default(run, "created_at", utcnow())
        self._runs.append(run)
        return run

    async def list_for_agent(self, agent_slug: str, limit: int) -> list[AutorespondRun]:
        self.last_limit = limit
        rows = [r for r in self._runs if r.agent_slug == agent_slug]
        return list(reversed(rows))[:limit]

    async def list_all(self, limit: int) -> list[AutorespondRun]:
        self.last_limit = limit
        return list(reversed(self._runs))[:limit]


class FakeNotificationRepository:
    def __init__(self) -> None:
        self._items: dict[int, Notification] = {}
        self._seq = 0

    async def add(self, notification: Notification) -> Notification:
        self._seq += 1
        notification.id = self._seq
        _default(notification, "unread", True)
        _default(notification, "status", "inbox")
        _default(notification, "created_at", utcnow())
        _default(notification, "updated_at", utcnow())
        self._items[notification.id] = notification
        return notification

    async def save(self, notification: Notification) -> None:
        self._items[notification.id] = notification

    async def get(self, notification_id: int) -> Notification | None:
        return self._items.get(notification_id)

    async def get_by_subject(self, user_id: int, subject_key: str) -> Notification | None:
        return next(
            (
                n
                for n in self._items.values()
                if n.user_id == user_id and n.subject_key == subject_key
            ),
            None,
        )

    async def list_for_user(
        self,
        user_id: int,
        *,
        status: str | None = None,
        unread: bool | None = None,
        reason: str | None = None,
        agent_slug: str | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        found = [n for n in self._items.values() if n.user_id == user_id]
        if status is not None:
            found = [n for n in found if n.status == status]
        if unread is not None:
            found = [n for n in found if n.unread == unread]
        if reason is not None:
            found = [n for n in found if n.reason == reason]
        if agent_slug is not None:
            found = [n for n in found if n.agent_slug == agent_slug]
        found.sort(key=lambda n: (n.updated_at, n.id), reverse=True)
        return found[:limit]

    async def unread_count(self, user_id: int) -> int:
        return sum(1 for n in self._items.values() if n.user_id == user_id and n.unread)

    async def mark_all_read(self, user_id: int) -> None:
        for n in self._items.values():
            if n.user_id == user_id and n.unread:
                n.unread = False
                n.last_read_at = utcnow()


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
        _default(agent, "auto_paused", False)
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
        if message.thread_id is None:
            message.thread_id = message.id  # the root starts its own thread
        _default(message, "type", "request")
        _default(message, "priority", "normal")
        _default(message, "created_at", utcnow())
        self._messages[message.id] = message
        return message

    async def get(self, message_id: int) -> Message | None:
        return self._messages.get(message_id)

    async def save(self, message: Message) -> None:
        self._messages[message.id] = message

    async def conversation(self, agent_a: str, agent_b: str, limit: int = 50) -> list[Message]:
        pair = {agent_a, agent_b}
        found = [m for m in self._messages.values() if {m.from_agent, m.to_agent} == pair]
        found.sort(key=lambda m: (m.created_at, m.id), reverse=True)
        return found[:limit]

    async def pending_for(self, to_agent: str) -> list[Message]:
        now = utcnow()
        found = [
            m
            for m in self._messages.values()
            if m.to_agent == to_agent
            and m.delivered_at is None
            and (m.expires_at is None or m.expires_at > now)
        ]
        found.sort(key=lambda m: (m.created_at, m.id))
        return found

    async def mark_delivered(self, message_ids: list[int], when: datetime | None = None) -> None:
        for message_id in message_ids:
            if message_id in self._messages:
                self._messages[message_id].delivered_at = when or utcnow()

    async def involving(self, agent_slugs: list[str], limit: int = 200) -> list[Message]:
        slugs = set(agent_slugs)
        found = [m for m in self._messages.values() if m.from_agent in slugs or m.to_agent in slugs]
        found.sort(key=lambda m: (m.created_at, m.id), reverse=True)
        return found[:limit]
