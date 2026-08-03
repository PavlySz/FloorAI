# Deploying

One EC2 instance, one process. No Docker, no managed services. About 15 minutes
to a URL you can send someone.

## 1. Launch the instance (AWS console)

EC2 → Launch instance:

- **AMI**: Ubuntu Server 24.04 LTS
- **Type**: `t3.small` (t2.micro works but is tight while rendering)
- **Key pair**: your existing one
- **Network settings**, the wizard defaults are almost right:
  - *Allow HTTP traffic from the internet* — **tick this**, it is the one the app
    needs. The service listens on port 80 so the URL has no port suffix.
  - *Allow SSH traffic from* — change **Anywhere** to **My IP**. This box holds
    your API keys, and port 22 open to the world attracts brute-force bots.
  - *Allow HTTPS* is harmless but unused, since there is no certificate.
- Launch, then copy the **Public IPv4 address**

To run on 8000 instead, add a Custom TCP rule for it and bootstrap with
`PORT=8000 bash deploy/bootstrap.sh`.

## 2. Bootstrap

```bash
ssh -i <your-key>.pem ubuntu@<public-ip>
curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/deploy/bootstrap.sh | bash -s -- https://github.com/<you>/<repo>.git
```

That installs Python, clones the repo, builds a venv, writes the systemd unit and
starts the service. For a private repo, clone it yourself first and then run
`bash deploy/bootstrap.sh` from inside the checkout.

## 3. Add the keys

`keys.env` is gitignored, so the bootstrap creates it from the example. The app
will not generate anything until it holds real keys:

```bash
nano ~/floorai/keys.env        # ANTHROPIC_API_KEY, GOOGLE_API_KEY
sudo systemctl restart floorai
```

## 4. Check

```bash
systemctl status floorai
journalctl -u floorai -f
curl -s localhost/api/options | head -c 200
```

Then open `http://<public-ip>` in a browser. That is the URL to send.

Verify it end to end from your own machine:

```bash
python api_client.py http://<public-ip>
```

## Notes

- **It is HTTP, not HTTPS.** Fine for a demo, but browsers show "not secure", so
  it is worth mentioning when you send the link. Real HTTPS needs a domain plus
  Caddy or nginx with certbot, which is another 20 minutes.
- **Your API keys pay for every render a visitor triggers.** A 4-viewpoint,
  2-variation run is 8 image generations. Either send the link for a limited
  window and stop the instance afterwards, or set `FLOORAI_IMAGE_QUALITY=fast`
  in `keys.env` to make the default cheaper and quicker.
- **Rendering is I/O-bound** on the two model APIs, so one uvicorn worker is fine
  for a demo. Add `--workers 2` to the unit file if several people will use it at
  once.
- `scenes/` and `static/renders/` are written at runtime on the instance and are
  not in the repo.
- To free the instance, stop it in the console. Nothing else persists.
