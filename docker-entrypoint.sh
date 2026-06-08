#!/bin/sh
# Batteries-included startup (GitLab-style): if no AMP_JWT_SECRET is provided,
# generate a strong one on first run and persist it on the data volume so
# sessions survive restarts. The operator never has to manage a secret.
set -e

if [ -z "$AMP_JWT_SECRET" ]; then
  mkdir -p /data
  secret_file=/data/jwt_secret
  if [ ! -f "$secret_file" ]; then
    head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$secret_file"
    chmod 600 "$secret_file"
  fi
  AMP_JWT_SECRET="$(cat "$secret_file")"
  export AMP_JWT_SECRET
fi

exec "$@"
