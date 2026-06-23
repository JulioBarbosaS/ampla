"""Scheduling algebra (Epic 08 · 8.1). Computes the next fire time of a schedule
from a kind + spec, given the current instant.

Pure and deterministic — time is passed in, never read from the clock — so it
unit-tests like the kanban rank helper and never breaks workflow resume. The
engine loop and the schedule service call into this; it has no I/O.

Kinds:
- ``interval`` — spec is a positive integer number of seconds.
- ``once`` — spec is an ISO-8601 instant (UTC assumed if naive); fires once.
- ``cron`` — spec is a 5-field cron expression ``m h dom mon dow`` (UTC),
  supporting ``*``, ranges ``a-b``, steps ``*/n`` / ``a-b/n`` and lists ``a,b``.
"""

from datetime import UTC, datetime, timedelta

# A bounded search horizon for cron: a valid expression always matches within a
# year, so this only ever caps a pathological/never-matching spec.
_CRON_HORIZON = timedelta(days=366)

_CRON_BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))  # m h dom mon dow (Sun=0)


def parse_interval(spec: str) -> int:
    """Seconds for an ``interval`` schedule (positive int)."""
    try:
        secs = int(spec)
    except (TypeError, ValueError) as exc:
        raise ValueError("intervalo deve ser um número de segundos") from exc
    if secs < 1:
        raise ValueError("intervalo deve ser de pelo menos 1 segundo")
    return secs


def parse_instant(spec: str) -> datetime:
    """Parse a ``once`` ISO-8601 instant; a naive value is read as UTC."""
    try:
        dt = datetime.fromisoformat(spec)
    except (TypeError, ValueError) as exc:
        raise ValueError("instante 'once' inválido (use ISO-8601)") from exc
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def validate_spec(kind: str, spec: str) -> None:
    """Raise ValueError if (kind, spec) is not a schedulable expression. Used by
    the service to 422 a bad schedule before it is stored."""
    if kind == "interval":
        parse_interval(spec)
    elif kind == "once":
        parse_instant(spec)
    elif kind == "cron":
        _parse_cron(spec)
    else:
        raise ValueError(f"tipo de agendamento inválido: {kind!r}")


def next_run(kind: str, spec: str, after: datetime) -> datetime | None:
    """The first fire time strictly after ``after``, or None when the schedule
    has no future occurrence (a past ``once``, or a cron with no match in a year)."""
    if kind == "interval":
        return after + timedelta(seconds=parse_interval(spec))
    if kind == "once":
        instant = parse_instant(spec)
        return instant if instant > after else None
    if kind == "cron":
        return _cron_next(spec, after)
    raise ValueError(f"tipo de agendamento inválido: {kind!r}")


# ---- cron ----


def _parse_cron(spec: str) -> tuple[set[int], ...]:
    parts = spec.split()
    if len(parts) != 5:
        raise ValueError("cron precisa de 5 campos: m h dom mon dow")
    return tuple(_parse_field(p, lo, hi) for p, (lo, hi) in zip(parts, _CRON_BOUNDS, strict=True))


def _parse_field(field: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for part in field.split(","):
        rng, _, step_s = part.partition("/")
        step = int(step_s) if step_s else 1
        if step < 1:
            raise ValueError(f"passo inválido em {part!r}")
        if rng == "*":
            start, end = lo, hi
        elif "-" in rng:
            a, _, b = rng.partition("-")
            start, end = int(a), int(b)
        else:
            start = end = int(rng)
        if start < lo or end > hi or start > end:
            raise ValueError(f"campo cron fora do intervalo: {part!r}")
        out.update(range(start, end + 1, step))
    if not out:
        raise ValueError("campo cron vazio")
    return out


def _cron_next(spec: str, after: datetime) -> datetime | None:
    minutes, hours, doms, months, dows = _parse_cron(spec)
    dom_restricted = spec.split()[2] != "*"
    dow_restricted = spec.split()[4] != "*"
    # Start at the next whole minute after `after`.
    t = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = t + _CRON_HORIZON
    while t <= limit:
        if t.minute in minutes and t.hour in hours and t.month in months:
            cron_dow = (t.weekday() + 1) % 7  # py Mon=0..Sun=6 → cron Sun=0..Sat=6
            dom_ok = t.day in doms
            dow_ok = cron_dow in dows
            matched = (
                (dom_ok or dow_ok) if (dom_restricted and dow_restricted) else (dom_ok and dow_ok)
            )
            if matched:
                return t
        t += timedelta(minutes=1)
    return None
