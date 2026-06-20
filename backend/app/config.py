"""Central configuration. Everything is set via environment variables (see .env.example)."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core
    app_name: str = "RepIQ"
    database_url: str = "sqlite:///./calliq.db"
    jwt_secret: str = "change-me-in-production"
    jwt_expiry_hours: int = 12
    # Public URL of the app (used to build invite / password-reset links). If blank, links are
    # built from the incoming request's host, which is correct for the single-origin deploy.
    public_base_url: str = ""
    invite_link_hours: int = 168     # new-user invite links valid for 7 days
    reset_link_hours: int = 24       # password-reset links valid for 24 hours
    audio_dir: str = "./audio"
    # The worker trims old recordings to keep at least this much disk FREE (based on actual
    # filesystem free space, not a fixed cap — the container disk is small and varies). When
    # free space drops below this, oldest already-completed calls' audio is deleted (they
    # re-download on demand for playback). Set a Railway volume on audio_dir to avoid this.
    audio_min_free_mb: int = 800
    cors_origins: str = "*"

    # Demo mode: app runs fully on synthetic data, no external APIs needed
    demo_mode: bool = True

    # Transcription (Deepgram)
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"
    deepgram_language: str = "en-GB"

    # LLM (Anthropic Claude)
    anthropic_api_key: str = ""
    claude_call_model: str = "claude-haiku-4-5-20251001"   # per-call analysis (cheap, fast)
    claude_report_model: str = "claude-sonnet-4-6"          # weekly coaching reports

    # RingCentral
    ringcentral_server_url: str = "https://platform.ringcentral.com"
    ringcentral_client_id: str = ""
    ringcentral_client_secret: str = ""
    ringcentral_jwt: str = ""
    ringcentral_webhook_secret: str = ""  # validation token we set on the subscription
    # Poll the call log every N minutes as a safety net alongside the webhook, so calls
    # still come in if the webhook subscription is disabled (e.g. after a redeploy).
    # 0 = disabled. Default 5 (looks back a short window each time — see worker.py).
    rc_poll_minutes: int = 5
    # CallIQ Agent (Teams recordings) — shared secret the local recording agent sends as the
    # X-Api-Key header on POST /api/recordings/upload. Blank = endpoint disabled (503).
    recordings_api_key: str = ""
    # How many calls the worker transcribes/analyses in parallel. Higher = calls clear
    # faster when reps are busy, at the cost of more CPU + API concurrency.
    worker_concurrency: int = 4
    # Calls shorter than this (no-answer / dead dials with no real conversation) are not
    # ingested and are removed during cleanup — there's nothing to transcribe.
    min_call_seconds: int = 5
    # Auto-retry a call that errors (e.g. its recording wasn't downloadable yet) up to this
    # many times, spaced a few minutes apart, before giving up and flagging it Failed.
    max_call_retries: int = 4

    # ---- Secure document storage (HR documents, brief §13) ----
    # Cloudflare R2 (S3-compatible). When all four are set, HR documents are stored in R2;
    # otherwise they fall back to durable storage in the database (fine for the current scale,
    # capped per file). Set these in Railway env to use R2.
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    max_document_mb: int = 15            # per-file upload cap

    # ---- Semantic memory / embeddings (Roadmap Phase 0 — RepIQ's "brain") ----
    # When an embeddings provider + key are set, RepIQ embeds call analyses so Ask RepIQ can
    # retrieve relevant evidence across the whole history (gets smarter the longer it runs).
    # Provider: "openai" (text-embedding-3-small) or "voyage" (voyage-3). Off until a key is set.
    embeddings_provider: str = ""        # openai | voyage
    embeddings_api_key: str = ""
    embeddings_model: str = ""           # blank = sensible default per provider
    embeddings_batch: int = 16           # calls embedded per worker tick

    # Microsoft Teams (Graph) — meeting recording ingestion from OneDrive Recordings folders
    ms_tenant_id: str = ""
    ms_client_id: str = ""
    ms_client_secret: str = ""
    ms_poll_minutes: int = 10  # 0 = disabled
    ms_lookback_days: int = 3  # how far back each poll scans for new recordings

    # ---- AI Performance Videos (Feature 8) ----
    # The AI weekly briefing (Claude script) always works; the talking-presenter video activates
    # when a HeyGen key is set. Without it, the rep/manager sees the written briefing (the brief's
    # documented fallback). HeyGen = turnkey script -> avatar video (async, polled to 'ready').
    videos_dir: str = "./data/videos"
    heygen_api_key: str = ""
    heygen_api_base: str = "https://api.heygen.com"
    heygen_avatar_id: str = "Daisy-inskirt-20220818"   # a HeyGen stock presenter (override in env)
    heygen_voice_id: str = "2d5b0e6cf36f460aa7fc47e3eee4ba54"  # a HeyGen stock voice (override in env)
    # Only RENDER HeyGen videos (which cost credits) for users whose team name contains one of
    # these comma-separated substrings; empty = everyone. Phased rollout — start with Volume.
    video_teams: str = "volume"

    # Compliance
    retention_days: int = 0  # 0 = keep forever; >0 = worker purges audio+transcripts older than N days

    # ---- CompanyIQ — in-call intelligence (Section 06 of the feature brief) ----
    # Each external source is optional. When a key is blank the orchestrator returns a
    # clean "not configured" section for that source and the rest of the panel still works.
    companyiq_cache_ttl: int = 86400      # seconds — full enriched payload (24h)
    companyiq_phone_ttl: int = 604800     # seconds — phone→CH number map (7 days)
    redis_url: str = ""                   # optional; falls back to an in-process TTL cache
    # Companies House (free, rate-limited) — the one source we can run live out of the box
    ch_api_key: str = ""
    # Apollo.io — decision-maker enrichment
    apollo_api_key: str = ""
    # Hunter.io — email verification / contact discovery
    hunter_api_key: str = ""
    # Lemlist — outreach / sequence status
    lemlist_api_key: str = ""
    # Google Places (New) — branch/trading locations
    google_places_key: str = ""

    # Master companies directory — a Google Sheet (~37k rows, refreshed daily from
    # Apollo/CH). Used as a 6th CompanyIQ source: matched by CH number or name to fill
    # employees/revenue/SIC and any extra enrichment the live APIs miss.
    master_sheet_id: str = ""
    master_sheet_tab: str = "Companies"
    mastersheet_ttl: int = 60 * 60 * 6  # in-memory cache of the sheet (6h)
    # Sales Tracker — order history (replaces the old NetSuite customer-status feed).
    # An Excel workbook with one tab per month (named like "May 26 - Total LB MTD").
    # Preferred: SALES_TRACKER_URL — an "anyone with the link" SharePoint share that the
    # app turns into a guestaccess download (no auth). Falls back to a Graph fetch
    # (SALES_TRACKER_SHARE_URL, reuses MS_* creds) then a local file path.
    sales_tracker_url: str = ""          # anonymous SharePoint share link (download path)
    sales_tracker_share_url: str = ""    # SharePoint link fetched via Graph (alt)
    sales_tracker_xlsx: str = ""         # local file fallback
    sales_tracker_ttl: int = 60 * 15  # in-memory cache of parsed orders/trackers (15 min);
    # a "Refresh" button force-reloads instantly so newly-placed orders show right away.

    # SalesIQ — the other three trackers. Two ways to reach each file:
    #  (a) Anonymous SharePoint share link (*_url) — same no-auth path as SALES_TRACKER_URL.
    #  (b) Microsoft Graph (Sites.Selected) when the tenant blocks anonymous sharing — set
    #      SHAREPOINT_* creds + the *_path of each file inside the document library below.
    # Whichever is configured for a given tracker wins (path via Graph preferred).
    lead_tracker_url: str = ""
    activity_tracker_url: str = ""
    holiday_tracker_url: str = ""
    # Graph (Sites.Selected) access to a single SharePoint site. Dedicated app registration;
    # falls back to the Teams MS_* creds if these are blank.
    sharepoint_tenant_id: str = ""
    sharepoint_client_id: str = ""
    sharepoint_client_secret: str = ""
    sharepoint_site_id: str = ""    # optional; else resolved from sharepoint_site_path
    sharepoint_site_path: str = "synvestmentcouk.sharepoint.com:/sites/Synvestment"
    sharepoint_library: str = "Office Docs"   # document library holding the trackers
    # File paths *within* the library (folder/filename). Blank -> use the *_url share instead.
    lead_tracker_path: str = ""
    activity_tracker_path: str = ""
    holiday_tracker_path: str = ""
    # Service-account credentials: either a path to the JSON key file, or the JSON
    # itself in an env var (recommended on Railway — set GOOGLE_SERVICE_ACCOUNT_JSON).
    google_service_account_file: str = "config/google-service-account.json"
    google_service_account_json: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
