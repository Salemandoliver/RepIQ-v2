# CallIQ — Call Analytics for BT Local Business Oxford & Bucks

A self-hosted Jiminny-style call analytics platform: every RingCentral call is recorded,
transcribed (Deepgram), and analysed by AI (Claude) — summaries, action items, playbook
scoring with timestamped evidence, topic detection, rep coaching, team statistics and
weekly coaching reports.

## Quick start (demo mode — no API keys needed)

```bash
cp .env.example .env        # edit JWT_SECRET and POSTGRES_PASSWORD
docker compose up -d --build
```

Open http://localhost:8080 and log in:

| | |
|---|---|
| Email | `admin@btlocalbusiness.co.uk` |
| Password | `demo1234` |

Demo mode seeds 90 days of realistic synthetic calls so every screen has data.
All demo reps share the password `demo1234` (e.g. `alex.bain@btlocalbusiness.co.uk`).

## Going live

1. Fill in `DEEPGRAM_API_KEY`, `ANTHROPIC_API_KEY` and the `RINGCENTRAL_*` values in `.env`
   (see `docs/GO_LIVE.md` for click-by-click instructions).
2. Set `DEMO_MODE=false`, then `docker compose up -d --build` on a fresh database
   (or keep demo data and just connect the pipeline).
3. Register the webhook + backfill recent calls:
   ```bash
   docker compose exec api python -m scripts.setup_ringcentral \
       --webhook https://YOUR-DOMAIN/api/webhooks/ringcentral --backfill 30
   ```
4. In Settings → Users, set each user's RingCentral extension ID so calls map to reps.

## Architecture

```
RingCentral ──webhook──▶ api (FastAPI) ──status:queued──▶ worker
                                │                           │ 1. download recording
                                ▼                           │ 2. Deepgram transcription
                            PostgreSQL ◀────────────────────┘ 3. Claude analysis + scoring
                                ▲
                            web (React + nginx, port 8080)
```

- `backend/app/routers/` — REST API (auth, calls, insights, admin, reports, webhooks)
- `backend/app/pipeline/` — worker, transcriber (swappable), Claude analyzer, RingCentral client
- `backend/app/seed/` — bootstrap (teams/topics/playbooks) + demo data generator
- `frontend/` — React app (Home, Library, Call page, Insights, Reports, Settings)

## Tests

```bash
cd backend && pip install -r requirements.txt pytest && python -m pytest tests -q
```

## Key documents

- `../PROJECT_PLAN.md` — goals, milestones, decisions
- `docs/GO_LIVE.md` — getting the three API keys and deploying
- `docs/RUNBOOK.md` — day-to-day operations, troubleshooting, GDPR tools
