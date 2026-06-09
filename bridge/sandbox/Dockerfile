# Sandbox image for the auto-responder. The daemon runs an ephemeral container
# (one per auto-respond) so `claude -p` only ever sees the mounted project dir —
# nothing else of the host's filesystem exists inside. Kernel-enforced, unlike
# the in-process deny-rules. The Anthropic OAuth credential is bind-mounted
# read-only at run time; no other host secret is reachable.
FROM debian:trixie-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl ripgrep git \
    && rm -rf /var/lib/apt/lists/*

# Non-root. uid 10002 to avoid clashing with the hub image's amp (10001).
RUN useradd --create-home --uid 10002 amp
USER amp
ENV PATH="/home/amp/.local/bin:${PATH}"

# claude is baked in at build time (network is available here); at run time the
# container needs egress only to the Anthropic API.
RUN curl -fsSL https://claude.ai/install.sh | bash

WORKDIR /work
ENTRYPOINT []
