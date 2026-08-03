#!/usr/bin/env bash
# Push local changes to a running deployment and restart it.
#
#   bash deploy/push.sh <host> <key.pem>
#   bash deploy/push.sh 3.141.23.162 ~/floorai-key.pem
#
# Uses tar over ssh rather than scp: scp -r has no exclude support and no delta,
# so it would re-upload .git, .history, every cached render and the venv each
# time. rsync would be ideal but is not in Git Bash on Windows.
#
# This is a full copy of the source each run, but the source is small (~1 MB
# without the excludes) so it takes a second or two.
set -euo pipefail

HOST="${1:-}"
KEY="${2:-}"
USER_AT="${SSH_USER:-ubuntu}"
APP_DIR="${APP_DIR:-floorai}"

if [ -z "$HOST" ] || [ -z "$KEY" ]; then
  echo "usage: bash deploy/push.sh <host> <key.pem>" >&2
  exit 1
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Everything that must not travel: local tooling, caches, generated output, and
# the server's own runtime state (renders and scenes live on the box).
EXCLUDES=(
  --exclude=.git
  --exclude=.history
  --exclude=.claude
  --exclude=.vscode
  --exclude=.venv
  --exclude=venv
  --exclude=__pycache__
  --exclude=*.pyc
  --exclude=scenes
  --exclude=static/renders
  --exclude=api_outputs
  --exclude=server.log
  # documentation images the server never serves
  --exclude=experiments
  --exclude=docs
)

echo "==> uploading to $USER_AT@$HOST:~/$APP_DIR"
tar czf - "${EXCLUDES[@]}" . \
  | ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$USER_AT@$HOST" \
      "mkdir -p ~/$APP_DIR && tar xzf - -C ~/$APP_DIR"

echo "==> installing any new dependencies"
ssh -i "$KEY" "$USER_AT@$HOST" \
  "cd ~/$APP_DIR && .venv/bin/pip install -q -r requirements.txt"

echo "==> restarting"
ssh -i "$KEY" "$USER_AT@$HOST" "sudo systemctl restart floorai && sleep 3 && \
  systemctl is-active --quiet floorai && echo '    service is up' || \
  (echo '    FAILED, last 20 log lines:'; journalctl -u floorai -n 20 --no-pager)"

echo "==> done: http://$HOST"
