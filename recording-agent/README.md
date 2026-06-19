# CallIQ recording agent

Uploads Teams call recordings from a rep's machine into CallIQ, where they're transcribed
(Deepgram) and analysed (Claude) automatically.

```
recorder saves a WAV  ─►  C:\CallIQ\recordings  ─►  agent uploads  ─►  POST /api/recordings/upload
                                                                          └─► queued ─► worker ─► CallIQ library
```

This setup: the recorder writes **extensionless WAV** files named `calliq_YYYY-MM-DD_HH-MM-SS`
into `C:\CallIQ\recordings`. The agent watches that folder, waits until each file has finished
writing, uploads it with the rep's email and the recording time, then moves it into
`C:\CallIQ\recordings\processed\` so it's never sent twice.

Two interchangeable agents — use whichever suits the machine:

- **`calliq_uploader.py`** — Python, recommended (richer logging, retries, `--inspect`).
- **`CallIQUploader.ps1`** — PowerShell, for machines with no Python installed.

### About the file format
The files have **no extension**, so the agent figures out the real audio format from the
file's contents (magic bytes) and defaults to **WAV**. It then tags each upload with the
correct extension + content-type, because the CallIQ pipeline keys the audio type off that.
You don't need to rename anything. Run `python calliq_uploader.py --inspect` to see what
format and timestamp the agent detects for each waiting file.

---

## 1. Server setup (one-time, in Railway)

In Railway → the CallIQ service → **Variables**, add:

| Variable | Value |
|---|---|
| `RECORDINGS_API_KEY` | a strong random secret (e.g. a 32-char hex string). The agent must send the same value. |
| `DEMO_MODE` | `false` — so real transcription/analysis runs |
| `DEEPGRAM_API_KEY` | from console.deepgram.com |
| `ANTHROPIC_API_KEY` | your Claude API key |

Generate a key: `python -c "import secrets; print(secrets.token_hex(16))"`.
Redeploy after setting the variables. The endpoint returns **503** until `RECORDINGS_API_KEY`
is set, and **401** if the agent's key doesn't match.

> Each rep who should own uploaded calls must already exist in CallIQ with the **same email**
> you set as `rep_email`. Unmatched uploads are still saved, just left unassigned.

---

## 2. Agent setup (on each rep's PC)

The recorder already saves to `C:\CallIQ\recordings`. Put the agent in the `callIQagent`
folder next to it.

### Option A — Python agent (recommended)

```
pip install -r requirements.txt
copy config.example.ini config.ini        # then edit config.ini
python calliq_uploader.py --check          # validates config + server reachability
python calliq_uploader.py --inspect        # shows detected format/time for waiting files
python calliq_uploader.py                  # start watching
```

In **`config.ini`** set just three things: `api_key` (same as `RECORDINGS_API_KEY`),
`rep_email` (this rep's CallIQ login), and `watch_dir` (already defaults to
`C:\CallIQ\recordings`). Everything else has sensible defaults.

### Option B — PowerShell agent (no Python)

```
powershell -ExecutionPolicy Bypass -File CallIQUploader.ps1 ^
  -ApiKey "SAME_AS_RAILWAY" -RepEmail "rep@oxfordandbucks.com" -WatchDir "C:\CallIQ\recordings"
```

---

## 3. Recording time & rep identity

**`recordedAt`** comes from the filename `calliq_2026-06-19_09-30-00` (read as local machine
time, sent as UTC). If a file isn't named that way, the file's creation time is used instead.

**Which rep** a file belongs to is decided in this order:

1. Filename prefix — `rep@oxfordandbucks.com__calliq_….` → that email.
2. Per-rep subfolder (Python: `rep_from_subfolder = true`) — `…\recordings\rep@email\calliq_…`.
3. Per-machine default — the `rep_email` / `-RepEmail` value (best for one-laptop-per-rep).

---

## 4. Run automatically at logon (Windows Task Scheduler)

```
schtasks /Create /TN "CallIQ Uploader" /SC ONLOGON /RL LIMITED /F ^
  /TR "pythonw C:\CallIQ\callIQagent\calliq_uploader.py"
```

PowerShell equivalent:

```
schtasks /Create /TN "CallIQ Uploader" /SC ONLOGON /RL LIMITED /F ^
  /TR "powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\CallIQ\callIQagent\CallIQUploader.ps1"
```

Prefer a periodic sweep over an always-on watcher? Use `--once` / `-Once` with
`/SC MINUTE /MO 5` so it processes whatever's waiting every 5 minutes and exits.

---

## 5. Test it end-to-end

```
curl -X POST https://repiq.co.uk/api/recordings/upload ^
  -H "X-Api-Key: YOUR_RECORDINGS_API_KEY" ^
  -F "file=@C:\CallIQ\recordings\calliq_2026-06-19_09-30-00;type=audio/wav" ^
  -F "repId=rep@oxfordandbucks.com" ^
  -F "recordedAt=2026-06-19T09:30:00Z"
```

Expected: `202` with `{"id": <number>, "status": "queued"}`. Within a few seconds the call
appears in CallIQ's library as a **Teams Call**, transcribed and scored. Or just let the
recorder drop a file and watch `uploader.log` (Python) / the console — the file should move
into `processed\` on success.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `503 Recordings endpoint not configured` | `RECORDINGS_API_KEY` not set on the server. |
| `401 Unauthorised` | Agent `api_key` ≠ server `RECORDINGS_API_KEY`. |
| File sits in the folder, never uploads | Still being written (size not stable) — raise `stable_seconds`. |
| Uploaded but won't transcribe | Confirm the file is really WAV: `--inspect` shows the detected format. If it shows something unexpected, set `default_ext` or check the recorder. |
| Call appears but isn't assigned to a rep | No CallIQ user with that email — check `rep_email` matches their login. |
| Files pile up in `failed\` | Open `uploader.log` — it records the HTTP status/reason for each. |

Audio on Railway is stored on the container's ephemeral disk (`AUDIO_DIR`, default `./audio/`).
Fine for the pilot; mount a Railway volume on `AUDIO_DIR` for retention.
