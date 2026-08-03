# Deploying to a single EC2 instance

One instance, one process. No Docker, no ECR, no managed services.

## 1. Launch

Ubuntu 22.04, `t3.small` or larger. Security group: inbound **22** from your IP
and **8000** from anywhere (or from your IP while demoing).

## 2. Install

```bash
sudo apt update && sudo apt install -y python3-venv git
git clone <repo> floorai && cd floorai
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3. Keys

```bash
cp keys.env.example keys.env
nano keys.env          # ANTHROPIC_API_KEY, GOOGLE_API_KEY
chmod 600 keys.env
```

`keys.env` is gitignored and read by `app/config.py`. Real environment variables
take precedence, so the systemd unit below can supply them instead.

## 4. Run under systemd

```bash
sudo cp deploy/floorai.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now floorai
systemctl status floorai
```

Logs: `journalctl -u floorai -f`

The app is then on `http://<public-ip>:8000/`, API docs at `/docs`.

## Notes

- `scenes/` and `static/renders/` are written at runtime and are gitignored.
  They live on the instance's disk; nothing else persists.
- Generation is I/O-bound on the two model APIs, so one uvicorn worker is
  plenty for a demo. Add `--workers N` if you expect concurrent users.
- To put it on port 80 without a proxy:
  `sudo setcap 'cap_net_bind_service=+ep' .venv/bin/python3` and change the port
  in the unit file.
