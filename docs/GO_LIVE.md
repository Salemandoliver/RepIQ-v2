# Go-live guide

Three accounts/keys are needed. Total setup time ≈ 1 hour.

## 1. Deepgram (transcription)

1. Sign up at https://console.deepgram.com (pay-as-you-go; £200 free credit at signup).
2. Create an API key → paste into `.env` as `DEEPGRAM_API_KEY`.
3. Cost guide: nova-3 is ~$0.0043/min. At ~2,500 recorded minutes/day ≈ **£8–12/day**.

## 2. Anthropic Claude (AI analysis)

1. Sign up at https://console.anthropic.com → API Keys → create key.
2. Paste into `.env` as `ANTHROPIC_API_KEY`.
3. CallIQ uses Haiku for per-call analysis and Sonnet for weekly reports.
   Estimated **£5–15/day** at current call volume.

## 3. RingCentral (call ingestion)

1. Go to https://developers.ringcentral.com → Console → Create App:
   - App type: **REST API App (No UI)**
   - Auth: **JWT auth flow**
   - Permissions: **Read Call Log**, **Read Call Recording**, **Webhook Subscriptions**
2. Note the **Client ID** and **Client Secret** → `.env`.
3. Under Credentials, create a **JWT** for the production environment → `RINGCENTRAL_JWT`.
4. Graduate the app to Production (RingCentral requires a short review for call-recording scope).
5. Make sure **Automatic Call Recording** is enabled in the RingCentral admin portal for all
   sales extensions (Admin Portal → Phone System → Auto-Receptionist → Call Recording).

## 4. Deploy

Any Docker host works. Recommended starting point: a 4 vCPU / 8 GB VM
(AWS London `eu-west-2` or Azure UK South for data residency), Caddy or nginx in front
for HTTPS on your domain.

```bash
git clone <this folder> && cd calliq
cp .env.example .env   # fill everything in, set DEMO_MODE=false
docker compose up -d --build
docker compose exec api python -m scripts.setup_ringcentral \
    --webhook https://calls.yourdomain.co.uk/api/webhooks/ringcentral --backfill 30
```

## 5. Map reps to extensions

Settings → Users: for each rep set their RingCentral extension ID
(Admin Portal → Users → user → Ext.). Calls from unmapped extensions still ingest,
just without a host attached.

## 6. First-week checklist

- [ ] Change the admin password (Settings → Users)
- [ ] Create real user accounts, deactivate demo reps (or start with a fresh DB)
- [ ] Review the two seeded playbooks and edit criteria to match your scripts
- [ ] Add custom vocabulary terms (product names, local town names)
- [ ] Set `RETENTION_DAYS` per your GDPR policy
- [ ] Verify a test call flows: queued → transcribing → analyzing → completed
