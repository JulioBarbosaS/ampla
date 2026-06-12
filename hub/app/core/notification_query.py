"""Filter-qualifier parser for the inbox search box (Epic 02).

Parses a GitHub-style query string (`is:unread reason:mention from:bob
agent:backend-julio`) into a structured filter. Hardened to **never raise** on
arbitrary input: unknown qualifiers, bare words and junk are simply ignored —
the worst a malformed query can do is match nothing.
"""

from dataclasses import dataclass

from app.schemas.notification import REASONS

_STATUSES = frozenset({"inbox", "saved", "done"})
# `is:` shortcuts for the subject_type column (friendly names only).
_SUBJECT_TYPES = frozenset({"dm", "mention", "task", "broadcast", "approval"})
_MAX_VALUE = 64  # ignore absurdly long values (a slug/sender never needs more)


@dataclass(frozen=True)
class ParsedFilter:
    status: str | None = None
    unread: bool | None = None
    reason: str | None = None
    agent_slug: str | None = None
    actor: str | None = None
    subject_type: str | None = None


def parse_filter_query(query: str | None) -> ParsedFilter:
    """Map known `key:value` qualifiers onto a ParsedFilter. Last write wins for
    a repeated qualifier; everything unrecognized is dropped (never raises)."""
    if not query:
        return ParsedFilter()
    fields: dict[str, str | bool] = {}
    for token in query.split():
        key, sep, value = token.partition(":")
        if not sep or not value:
            continue  # bare word / free text — ignored
        key = key.lower()
        value = value.lower()
        if len(value) > _MAX_VALUE:
            continue
        if key == "is":
            if value in _STATUSES:
                fields["status"] = value
            elif value == "unread":
                fields["unread"] = True
            elif value == "read":
                fields["unread"] = False
            elif value in _SUBJECT_TYPES:
                fields["subject_type"] = value
        elif key == "reason" and value in REASONS:
            fields["reason"] = value
        elif key == "agent":
            fields["agent_slug"] = value
        elif key == "from":
            fields["actor"] = value
    return ParsedFilter(**fields)
