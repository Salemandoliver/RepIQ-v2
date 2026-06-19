# Deploying CallIQ to Railway

Your service domain: `https://successful-delight-production-a2f8.up.railway.app`

The repo includes a root `Dockerfile` + `railway.json` that run everything as ONE
Railway service (frontend + API + worker in-process) plus Railway's managed Postgres.

## 1. Add Postgres

Railway dashboard → your project → **+ New** → **Database** → **PostgreSQL**.

## 2. Set service variables

Open your app service → **Variables** → add (copy values from `calliq/.env`):

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (reference to the DB you just added) |
| `JWT_SECRET` | from `.env` |
| `DEMO_MODE` | `false` |
| `DEEPGRAM_API_KEY` | from `.env` |
| `ANTHROPIC_API_KEY` | from `.env` |
| `RINGCENTRAL_SERVER_URL` | `https://platform.ringcentral.com` |
| `RINGCENTRAL_CLIENT_ID` | from `.env` |
| `RINGCENTRAL_CLIENT_SECRET` | from `.env` |
| `RINGCENTRAL_JWT` | from `.env` |
| `RC_POLL_MINUTES` | `10` (safety net; the webhook does the real-time work) |
| `AUDIO_DIR` | `/data/audio` |
| `RETENTION_DAYS` | `0` |

## 3. Add a volume (audio storage)

Service → right-click / settings → **Attach Volume** → mount path `/data`.
Without this, audio files are lost on each redeploy (transcripts/analyses live in
Postgres and are safe either way).

## 4. Deploy the code

Easiest is the Railway CLI from your PC:

```powershell
npm install -g @railway/cli
railway login
cd "calliq folder path"
railway link        # pick your existing project + service
railway up          # uploads and builds the Dockerfile
```

(Alternative: push `calliq/` to a GitHub repo and connect it in the service settings —
Railway then redeploys automatically on every push.)

## 5. After first deploy

1. Open `https://successful-delight-production-a2f8.up.railway.app` → log in
   `admin@btlocalbusiness.co.uk` / `demo1234` → **change the password immediately**
   (the app is now on the public internet).
2. Register the webhook + backfill last 7 days — one API call from the browser is
   fiddly, so tell Claude "register the webhook" and it will call:
   `POST /api/admin/ringcentral/setup?webhook_url=https://successful-delight-production-a2f8.up.railway.app/api/webhooks/ringcentral&backfill_days=7`
3. Check `GET /api/admin/ringcentral/status` shows the subscription as Active.

## Notes

- **Region/GDPR:** in service settings choose **EU (Amsterdam)** region. Railway has no
  UK region; EU storage is fine under the UK adequacy decision — note it in your
  privacy documentation.
- **Costs:** Hobby plan ($5/mo) likely insufficient at your volume; Pro ($20/mo) with
  usage-based compute should land around $25–50/month all-in.
- **Scaling:** if the in-process worker can't keep up with call volume, split it into a
  second Railway service from the same image with start command
  `python -m app.pipeline.worker` and remove `RUN_WORKER_IN_APP`.
