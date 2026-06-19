# Local pilot setup (your PC)

Everything is already configured in `.env` — all three API keys are in and verified,
demo mode is off, and the worker polls RingCentral every 5 minutes for new recorded
calls (no public webhook needed for the pilot).

## 1. Install Docker Desktop

If not already installed: https://www.docker.com/products/docker-desktop (keep default
settings, restart when asked).

## 2. Start CallIQ

Open a terminal (PowerShell) in the `calliq` folder:

```powershell
docker compose up -d --build
```

First build takes ~5 minutes. Then open **http://localhost:8080** and log in with
`admin@btlocalbusiness.co.uk` / `demo1234` — **change this password immediately**
(Settings → Users → edit).

## 3. Backfill recent calls (optional but recommended)

Pull the last 7 days of recorded calls so there's data to look at right away:

```powershell
docker compose exec api python -m scripts.setup_ringcentral --backfill 7
```

The worker will then process them one by one (watch progress with
`docker compose logs -f worker`). At your volume, expect a few hundred calls —
they'll take a few hours to chew through and cost a few pounds in API usage.

## 4. Add your reps

Settings → Users → Invite User. To map calls to reps automatically, set each user's
RingCentral **extension ID** — for now ask me to do it, or find them in the RingCentral
Admin Portal (Users → user → Ext). Calls from unmapped extensions still appear,
just without a rep attached.

## 5. During the pilot

- New recorded calls appear automatically within ~5–10 minutes of ending.
- Review the two playbooks (Settings → Playbooks) and tune the criteria to your scripts —
  scoring quality depends heavily on these.
- Add vocabulary terms for products reps mention often (Settings → Vocabulary).

## Pilot limitations (fixed when we move to a server)

- The PC must stay on for calls to be ingested (missed ones are caught by the poller's
  1-day lookback, or run a backfill).
- Only people on your office network can reach http://YOUR-PC-IP:8080.
- When you're ready for production hosting, tell Claude — the move is: copy folder,
  same `docker compose up`, register the webhook, restore a database backup.
