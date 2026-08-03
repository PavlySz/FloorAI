#!/usr/bin/env bash
# One-paste setup for a fresh Ubuntu EC2 instance.
#
#   curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/deploy/bootstrap.sh | bash -s -- <repo-url>
#
# or after cloning manually:  bash deploy/bootstrap.sh
set -euo pipefail

REPO="${1:-}"
APP_DIR="$HOME/floorai"

echo "==> packages"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip git

if [ -n "$REPO" ]; then
  echo "==> clone"
  rm -rf "$APP_DIR"
  git clone -q "$REPO" "$APP_DIR"
else
  APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$APP_DIR"

echo "==> venv"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

if [ ! -f keys.env ]; then
  cp keys.env.example keys.env
  chmod 600 keys.env
  echo
  echo "!! keys.env created from the example. Put the real keys in it now:"
  echo "     nano $APP_DIR/keys.env"
  echo "   then re-run:  sudo systemctl restart floorai"
  echo
fi

echo "==> systemd"
sudo tee /etc/systemd/system/floorai.service >/dev/null <<UNIT
[Unit]
Description=FloorAI
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/keys.env
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable -q --now floorai
sleep 3
sudo systemctl restart floorai
sleep 3

IP="$(curl -fsS --max-time 5 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo '<public-ip>')"
echo
if systemctl is-active --quiet floorai; then
  echo "==> running:  http://$IP:8000"
else
  echo "==> NOT running. Check:  journalctl -u floorai -n 40 --no-pager"
fi
