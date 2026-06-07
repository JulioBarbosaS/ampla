"""Property-based tests (hypothesis) — invariantes que valem para QUALQUER
entrada, não só os exemplos que lembramos de escrever.

Foco nos pontos de pressão adversarial: rate limiters, validação de slug
e round-trip do protocolo WS.
"""

import re

from hypothesis import given
from hypothesis import strategies as st

from app.core.ratelimit import SlidingWindowLimiter, TokenBucket
from app.schemas.agent import SLUG_PATTERN
from app.schemas.ws import SendMessageFrame, client_frame_adapter

_SLUG_RE = re.compile(SLUG_PATTERN)

# ---------------------------------------------------------------- limiters


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, secs: float) -> None:
        self.now += secs


@given(
    deltas=st.lists(st.floats(min_value=0.0, max_value=5.0), min_size=1, max_size=200),
    max_events=st.integers(min_value=1, max_value=20),
    window=st.floats(min_value=1.0, max_value=60.0),
)
def test_sliding_window_nunca_excede_o_maximo_em_nenhuma_janela(deltas, max_events, window):
    """Invariante: para qualquer sequência de chegadas, o número de eventos
    PERMITIDOS dentro de qualquer janela nunca passa de max_events."""
    clock = FakeClock()
    limiter = SlidingWindowLimiter(max_events, window, clock=clock)
    allowed_times: list[float] = []

    for delta in deltas:
        clock.advance(delta)
        if limiter.allow("ip"):
            allowed_times.append(clock.now)

    for i, start in enumerate(allowed_times):
        in_window = [t for t in allowed_times[i:] if t - start <= window]
        assert len(in_window) <= max_events


@given(
    deltas=st.lists(st.floats(min_value=0.0, max_value=10.0), min_size=1, max_size=300),
    rate=st.integers(min_value=1, max_value=120),
)
def test_token_bucket_respeita_burst_mais_taxa(deltas, rate):
    """Invariante: permitidos ≤ capacidade inicial + taxa × tempo decorrido."""
    clock = FakeClock()
    bucket = TokenBucket(rate, clock=clock)
    capacity = max(rate // 4, 5)

    allowed = 0
    elapsed = 0.0
    for delta in deltas:
        clock.advance(delta)
        elapsed += delta
        if bucket.allow():
            allowed += 1

    assert allowed <= capacity + (rate / 60.0) * elapsed + 1e-6


# ---------------------------------------------------------------- slug


@given(slug=st.from_regex(SLUG_PATTERN, fullmatch=True))
def test_slug_valido_tem_as_propriedades_garantidas(slug):
    assert slug == slug.lower()
    assert 3 <= len(slug) <= 50
    assert not slug.startswith("-") and not slug.endswith("-")


@given(text=st.text(min_size=1, max_size=60))
def test_slug_aceito_implica_caracteres_seguros(text):
    """Qualquer string aceita pelo pattern só contém [a-z0-9-] — nunca
    espaços, maiúsculas, unicode ou metacaracteres."""
    if _SLUG_RE.fullmatch(text):
        assert re.fullmatch(r"[a-z0-9-]+", text)


# ---------------------------------------------------------------- protocolo


@given(
    to=st.from_regex(SLUG_PATTERN, fullmatch=True),
    body=st.text(min_size=1, max_size=2000),
    msg_type=st.sampled_from(
        ["request", "response", "notification", "task", "alert", "status", "ack"]
    ),
    priority=st.sampled_from(["urgent", "high", "normal", "low"]),
    in_reply_to=st.one_of(st.none(), st.integers(min_value=1, max_value=10**9)),
)
def test_send_frame_roundtrip_serializa_e_volta_identico(to, body, msg_type, priority, in_reply_to):
    """Round-trip: qualquer frame válido sobrevive a serializar→parsear,
    inclusive bodies com unicode, aspas, controle e emoji."""
    frame = SendMessageFrame(
        to=to, body=body, msg_type=msg_type, priority=priority, in_reply_to=in_reply_to
    )
    parsed = client_frame_adapter.validate_json(frame.model_dump_json())
    assert parsed == frame
