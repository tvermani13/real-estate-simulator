#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DGX_SSH="${DGX_SSH:-tvermani13@100.72.234.104}"
DGX_DIR="${DGX_DIR:-/home/tvermani13/projects/real-estate-simulator}"
DGX_SSH_CONFIG="${DGX_SSH_CONFIG:-}"

SSH_ARGS=(-o BatchMode=yes)
RSYNC_SSH=(ssh -o BatchMode=yes)
if [[ -n "$DGX_SSH_CONFIG" ]]; then
  SSH_ARGS=(-F "$DGX_SSH_CONFIG" "${SSH_ARGS[@]}")
  RSYNC_SSH=(ssh -F "$DGX_SSH_CONFIG" -o BatchMode=yes)
fi

printf 'Syncing Hearthline to %s:%s\n' "$DGX_SSH" "$DGX_DIR"
ssh "${SSH_ARGS[@]}" "$DGX_SSH" "mkdir -p '$DGX_DIR'"
ssh "${SSH_ARGS[@]}" "$DGX_SSH" \
  "if test -f '$DGX_DIR/infra/.env' && test -f '$DGX_DIR/infra/docker-compose.yml'; then cd '$DGX_DIR' && docker compose --env-file infra/.env -f infra/docker-compose.yml --profile jobs run --rm backup; fi"
rsync -az \
  --exclude '.DS_Store' \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '**/__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'backend/.env' \
  --exclude 'backend/data/' \
  --exclude 'frontend/.env.local' \
  --exclude 'frontend/.next/' \
  --exclude 'frontend/node_modules/' \
  --exclude 'infra/.env' \
  -e "${RSYNC_SSH[*]}" \
  "$ROOT_DIR/" "$DGX_SSH:$DGX_DIR/"

ssh "${SSH_ARGS[@]}" "$DGX_SSH" \
  "cd '$DGX_DIR' && test -f infra/.env || cp infra/.env.dgx.example infra/.env"
ssh "${SSH_ARGS[@]}" "$DGX_SSH" \
  "cd '$DGX_DIR' && docker compose --env-file infra/.env -f infra/docker-compose.yml --profile jobs config --quiet"
ssh "${SSH_ARGS[@]}" "$DGX_SSH" \
  "cd '$DGX_DIR' && docker compose --env-file infra/.env -f infra/docker-compose.yml build backend frontend"
ssh "${SSH_ARGS[@]}" "$DGX_SSH" \
  "cd '$DGX_DIR' && docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --wait --wait-timeout 180"
ssh "${SSH_ARGS[@]}" "$DGX_SSH" \
  "curl -fsS http://127.0.0.1:8083/api/ready"

printf '\nHearthline is healthy on DGX loopback. One-time tailnet publication:\n'
printf '  sudo tailscale serve --bg --https=8445 http://127.0.0.1:8083\n'
