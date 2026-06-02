# Deploying to a DigitalOcean droplet

The production stack is two containers wired by `docker-compose.yml`:

- **backend** — FastAPI (uvicorn) on an internal port `8000`.
- **web** — nginx serving the built React app on port **80**, proxying
  `/api`, `/auth`, `/uploads`, `/webhook`, `/internal`, `/docs` to the backend.

The frontend talks to the API on the **same origin** (relative `/api` paths),
so there's no `VITE_API_URL` to configure and no CORS to worry about.

---

## 1. Create the droplet

- Ubuntu 22.04+, at least **2 GB RAM** (WeasyPrint + the build need headroom).
- Add your SSH key, then SSH in as root.

```bash
# install Docker + the compose plugin
curl -fsSL https://get.docker.com | sh
# firewall: allow SSH + HTTP (+ HTTPS if you add TLS)
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

## 2. Clone the repo

```bash
git clone <your-repo-url> lettingauto
cd lettingauto
git checkout dev_extended_v2   # or whichever branch you pushed
```

## 3. Provide the secrets (these are gitignored — not in the repo)

```bash
cp backend/.env.example backend/.env
nano backend/.env
```

Set at least:

| Key | Value |
|---|---|
| `APP_ENV` | `production` (real DocuSign) or `test` (mock signer) |
| `FRONTEND_BASE_URL` | `http://<droplet-ip>` or `https://<your-domain>` — used in the emails sent to landlords/tenants, so it must be the public URL |
| `JWT_SECRET` | a long random string |
| `AGENT_BOOTSTRAP_EMAIL` / `AGENT_BOOTSTRAP_PASSWORD` | your admin login |
| `AIRTABLE_TOKEN` / `AIRTABLE_BASE_ID` + the `AIRTABLE_TABLE_*` ids | from Airtable |
| `DOCUSIGN_*`, `SMTP_*`, `PARAGON_*` | as applicable |

Then drop in the DocuSign private key (mounted read-only, never baked into an image):

```bash
nano backend/docusign_rsa.key   # paste the RSA private key, or scp it up
```

## 4. Launch

```bash
docker compose up -d --build
```

The app is now live at **`http://<droplet-ip>/`**. Log in with the
`AGENT_BOOTSTRAP_*` credentials.

Useful commands:

```bash
docker compose logs -f            # tail logs
docker compose ps                 # status
docker compose up -d --build      # redeploy after a git pull
docker compose down               # stop (volumes/data preserved)
```

Persistent data lives in named volumes (`uploads`, `signatures`) and survives
rebuilds. Airtable is the real datastore.

---

## 5. Domain + HTTPS (recommended before real use)

Over plain HTTP the landlord/tenant forms transmit PII in the clear, and
DocuSign Connect requires an HTTPS webhook URL. Two easy options:

**A. Caddy in front (auto Let's Encrypt).** Point an `A` record at the droplet,
then run a Caddy container that reverse-proxies `:80/:443` to the `web` service
— Caddy fetches and renews certs automatically. (Ask and I'll add a
`docker-compose.tls.yml` overlay.)

**B. certbot on the host.** Install nginx/certbot on the host, proxy `:443` to
`localhost:80`, and run `certbot --nginx`.

## 6. DocuSign Connect

Once you have HTTPS, set your DocuSign Connect webhook URL to
`https://<your-domain>/webhook/docusign` and the HMAC key to
`DOCUSIGN_CONNECT_HMAC_SECRET` in `.env`. Without a public webhook the signing
status updates won't arrive (use `POST /webhook/docusign/poll/{envelope_id}` to
pull manually).

## 7. Diary scheduler (optional)

The diary alerts (PG_06) fire when `/api/forms/scheduler/run?token=<SCHEDULER_INTERNAL_TOKEN>`
is hit. Add a daily host cron:

```bash
# crontab -e
0 7 * * * curl -s "http://localhost/api/forms/scheduler/run?token=<token>" >/dev/null
```

## 8. First-run Airtable tables

If this is a brand-new Airtable base, create the app-managed tables once:

```bash
docker compose exec backend python -m scripts.create_offers_table
docker compose exec backend python -m scripts.create_sent_documents_table
# then copy the printed ids into backend/.env and `docker compose up -d`
```

(For the existing base these already exist — the scripts are idempotent and
just print the ids.)

---

## Local development

The hot-reload stack is separate:

```bash
docker compose -f docker-compose.dev.yml up
# backend :8000, frontend dev server :5173
```
