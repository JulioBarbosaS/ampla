"""@mention parsing for message bodies (Epic 02 generation).

Matches `@slug` tokens that fit the public agent slug pattern. Returns unique
slugs in first-seen order. Pure text in → slug list out: it never resolves or
trusts anything, so it can't be an injection vector (the caller resolves slugs
to owners and applies authz)."""

import re

# @ followed by a valid agent slug (same shape as SLUG_PATTERN, sans anchors).
_MENTION_RE = re.compile(r"@([a-z][a-z0-9-]{1,48}[a-z0-9])")


def parse_mentions(body: str) -> list[str]:
    seen: dict[str, None] = {}
    for match in _MENTION_RE.finditer(body):
        seen.setdefault(match.group(1), None)
    return list(seen)
