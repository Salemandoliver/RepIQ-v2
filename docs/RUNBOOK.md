# Operations runbook

## Daily

Nothing. The pipeline is automatic: webhook → queue → worker. Weekly coaching reports
generate every Monday morning.

## Useful commands

```bash
docker compose ps                       # all four services should be Up
docker compose logs -f worker           # watch calls being processed
docker compose logs -f api              # watch webhooks arriving
docker compose restart worker           # safe at any time; queued calls resume
```

## Checking a stuck call

Call statuses: `queued → downloading → transcribing → analyzing → completed` (or `failed`).
Failed calls keep the error message — visible in the Library (status filter) or:

```bash
docker compose exec db psql -U calliq -c \
  "select id, status, error from calls where status='failed' order by id desc limit 10;"
```

Requeue failed calls:

```bash
docker compose exec db psql -U calliq -c \
  "update calls set status='queued', error=null where status='failed';"
```

## Backups

All state is in two Docker volumes: `pgdata` (database) and `audio` (recordings).

```bash
docker compose exec db pg_dump -U calliq calliq | gzip > backup_$(date +%F).sql.gz
```

Schedule that daily (cron) and copy off-machine.

## GDPR

- **Erasure request:** Settings → Privacy → enter the customer phone number → Erase
  (deletes calls, transcripts, analyses and audio files). Also available via API:
  `DELETE /api/admin/gdpr/erase?phone=+44...`
- **Retention:** set `RETENTION_DAYS` in `.env`; the worker purges hourly.

## RingCentral webhook expiry

Subscriptions are created with maximum expiry but can be dropped if the endpoint is
unreachable for a long period. If new calls stop arriving:

```bash
docker compose exec api python -m scripts.setup_ringcentral \
  --webhook https://YOUR-DOMAIN/api/webhooks/ringcentral
docker compose exec api python -m scripts.setup_ringcentral --backfill 2   # catch up
```

## Cost monitoring

- Deepgram: console.deepgram.com → Usage
- Anthropic: console.anthropic.com → Usage
- If costs rise, reduce scope: skip Voicemail/under-60s calls by adding a duration check
  in `webhooks_router.py`, or switch `claude_call_model` to an even cheaper model in config.

## Upgrading / changes

The app is maintained through Claude (Cowork). Open the "BT Oxford and Bucks Call
Analytics" project and describe the change; the codebase is in `calliq/`. After changes:
`docker compose up -d --build`.
