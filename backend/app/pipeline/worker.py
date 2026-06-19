"""Background worker: processes queued calls through the full pipeline and runs
scheduled jobs (polling ingestion, weekly reports, retention purge).

Run with:  python -m app.pipeline.worker   (or in-process via RUN_WORKER_IN_APP=true)
"""
import logging
import threading
import time
from datetime import datetime, timedelta

from ..config import settings
from ..db import Base, engine, SessionLocal
from ..models import (Call, TranscriptTurn, CallAnalysis, CallScore, CallTopic,
                      Playbook, Topic, VocabularyTerm, Setting, Report)
from .metrics import compute_metrics
from .transcriber import get_transcriber, assign_roles
from .analyzer import analyze_call
from .ringcentral import RingCentralClient

log = logging.getLogger("calliq.worker")
POLL_SECONDS = 5

# Liveness timestamps so /api/admin/calls/queue-status can show the worker is actually alive.
_HEARTBEAT = {"processing": None, "ingestion": None}


def worker_heartbeat() -> dict:
    return {k: (v.isoformat() + "Z" if v else None) for k, v in _HEARTBEAT.items()}

# One shared client so the OAuth token is fetched once per hour, not once per call
# (RingCentral rate-limits the token endpoint hard).
_rc: RingCentralClient | None = None


def shared_rc() -> RingCentralClient:
    global _rc
    if _rc is None:
        _rc = RingCentralClient()
    return _rc


def _delete_call(db, call) -> None:
    """Remove a call and everything attached to it (used for dead / no-answer dials)."""
    import os
    from ..models import Comment, ListenEvent
    cid = call.id
    for M in (TranscriptTurn, CallAnalysis, CallScore, CallTopic):
        db.query(M).filter(M.call_id == cid).delete()
    db.query(Comment).filter(Comment.call_id == cid).delete()
    db.query(ListenEvent).filter(ListenEvent.call_id == cid).delete()
    if call.audio_path and os.path.exists(call.audio_path):
        try:
            os.remove(call.audio_path)
        except OSError:
            pass
    db.delete(call)
    db.commit()


def _dir_size(path: str) -> int:
    import os
    total = 0
    if not os.path.isdir(path):
        return 0
    for name in os.listdir(path):
        try:
            total += os.path.getsize(os.path.join(path, name))
        except OSError:
            pass
    return total


def _disk_guard(db) -> None:
    """Keep enough disk FREE so downloads never fail with 'No space left on device'. Uses the
    real filesystem free space (the container disk is small and its size varies). When free
    space is low we delete orphan files first, then trim the OLDEST already-completed calls'
    audio — those re-download on demand when someone plays them back."""
    import os, shutil
    d = settings.audio_dir
    os.makedirs(d, exist_ok=True)
    try:
        free = shutil.disk_usage(d).free
    except OSError:
        return
    min_free = max(200, settings.audio_min_free_mb) * 1024 * 1024
    if free >= min_free:
        return
    need = min_free - free
    freed = 0
    referenced = {p for (p,) in db.query(Call.audio_path).filter(Call.audio_path.isnot(None)).all()}
    entries = []
    for name in os.listdir(d):
        fp = os.path.join(d, name)
        try:
            entries.append((fp, os.path.getsize(fp), os.path.getmtime(fp)))
        except OSError:
            pass
    entries.sort(key=lambda x: x[2])  # oldest first
    # 1) orphan files first (no call references them — pure waste)
    for fp, sz, _ in entries:
        if freed >= need:
            break
        if fp not in referenced:
            try:
                os.remove(fp); freed += sz
            except OSError:
                pass
    # 2) still need room: drop oldest completed calls' audio (transcript/scores kept; re-downloadable)
    if freed < need:
        for c in (db.query(Call).filter(Call.status == "completed", Call.audio_path.isnot(None))
                  .order_by(Call.started_at.asc()).all()):
            if freed >= need:
                break
            try:
                if c.audio_path and os.path.exists(c.audio_path):
                    freed += os.path.getsize(c.audio_path)
                    os.remove(c.audio_path)
            except OSError:
                pass
            c.audio_path = None
        db.commit()
    if freed:
        log.info("Disk guard freed %.0f MB (free was %.0f MB, target %.0f MB)",
                 freed / 1e6, free / 1e6, min_free / 1e6)


def _coaching_fields(c: dict) -> dict:
    """Map the analyzer's 'coaching' block to CallAnalysis columns, defensively (the model
    may omit or malform fields)."""
    qb = c.get("question_breakdown") or {}
    bm = c.get("best_moment") or {}
    def _slist(v):
        return [str(x) for x in v][:5] if isinstance(v, list) else []
    objs = c.get("objections") if isinstance(c.get("objections"), list) else []
    return {
        "one_thing": str(c.get("one_thing") or "")[:2000],
        "strengths": _slist(c.get("strengths")),
        "improvements": _slist(c.get("improvements")),
        "question_breakdown": {k: int(qb.get(k) or 0) for k in ("discovery", "closing", "clarifying")},
        "objections": objs[:12],
        "energy_note": str(c.get("energy_note") or "")[:1000],
        "best_moment": {"start_sec": float(bm.get("start_sec") or 0),
                        "end_sec": float(bm.get("end_sec") or 0),
                        "quote": str(bm.get("quote") or "")[:600],
                        "reason": str(bm.get("reason") or "")[:400]} if bm.get("quote") else {},
    }


def _followups(f) -> dict:
    """Commitments extracted from the call (for the rep's daily action plan)."""
    f = f if isinstance(f, dict) else {}
    keys = ("callback", "email_promised", "missing_info", "proposal_needed", "next_step")
    return {k: str(f.get(k) or "").strip()[:400] for k in keys}


def process_call(db, call: Call) -> None:
    import os as _os
    rc = shared_rc()

    # Dead / no-answer dial (too short to hold a conversation) — drop it, don't process.
    if call.duration_sec and call.duration_sec < settings.min_call_seconds:
        _delete_call(db, call)
        return

    # 1. Download audio (also re-download if the file vanished, e.g. after a
    # container restart without a persistent volume)
    if call.audio_path and not _os.path.exists(call.audio_path):
        call.audio_path = None
    if not call.audio_path and (call.rc_recording_id or "").startswith("ms:"):
        call.status = "downloading"
        db.commit()
        from .msteams import redownload
        call.audio_path = redownload(call.rc_recording_id, settings.audio_dir)
        db.commit()
    elif not call.audio_path and call.rc_recording_id:
        call.status = "downloading"
        db.commit()
        call.audio_path = rc.download_recording(call.rc_recording_id, settings.audio_dir)
        db.commit()

    # 2. Transcribe with diarization + custom vocabulary
    call.status = "transcribing"
    db.commit()
    keyterms = [v.term for v in db.query(VocabularyTerm).all()]
    raw_turns = get_transcriber().transcribe(call.audio_path, keyterms)
    turns = assign_roles(raw_turns)
    if not turns:
        _delete_call(db, call)     # no speech at all = dead / no-answer dial — remove it
        return

    db.query(TranscriptTurn).filter(TranscriptTurn.call_id == call.id).delete()
    rep_name = call.host.name if call.host else "Rep"
    for t in turns:
        db.add(TranscriptTurn(call_id=call.id, speaker=t["speaker"],
                              speaker_name=rep_name if t["speaker"] == "rep" else "Customer",
                              start_sec=t["start_sec"], end_sec=t["end_sec"], text=t["text"]))
    if not call.duration_sec:
        call.duration_sec = int(turns[-1]["end_sec"])
    db.commit()

    # 3. Analyse with Claude
    call.status = "analyzing"
    db.commit()
    playbooks = [{"id": p.id, "name": p.name, "description": p.description,
                  "criteria": p.criteria}
                 for p in db.query(Playbook).filter(Playbook.active == True).all()  # noqa: E712
                 if not p.activity_types or call.activity_type in p.activity_types]
    topics = [{"id": t.id, "name": t.name, "keywords": t.keywords}
              for t in db.query(Topic).filter(Topic.active == True).all()]  # noqa: E712
    ai_ctx = (db.get(Setting, "ai_context") or Setting(value={})).value.get("text", "")

    result = analyze_call(turns, rep_name, call.activity_type, playbooks, topics, ai_ctx)

    # 4. Persist analysis + computed engagement metrics
    m = compute_metrics(turns)
    db.query(CallAnalysis).filter(CallAnalysis.call_id == call.id).delete()
    db.add(CallAnalysis(
        call_id=call.id,
        summary_intro=result.get("summary_intro", ""),
        summary_points=result.get("summary_points", []),
        action_items=result.get("action_items", []),
        key_points=result.get("key_points", []),
        themes=result.get("themes", []),
        sentiment=result.get("sentiment", "neutral"),
        **{k: m.get(k, 0) for k in ("talk_ratio", "longest_monologue_sec",
                                    "longest_customer_story_sec", "talking_speed_wpm",
                                    "patience_sec", "question_rate",
                                    "interruptions", "filler_count")},
        **_coaching_fields(result.get("coaching") or {}),
        followups=_followups(result.get("followups")),
    ))
    db.query(CallTopic).filter(CallTopic.call_id == call.id).delete()
    for dt in result.get("detected_topics", []):
        if db.get(Topic, dt.get("topic_id")):
            db.add(CallTopic(call_id=call.id, topic_id=dt["topic_id"],
                             mentions=dt.get("mentions", 1),
                             first_mention_sec=dt.get("first_mention_sec", 0)))
    db.query(CallScore).filter(CallScore.call_id == call.id).delete()
    for s in result.get("scores", []):
        if db.get(Playbook, s.get("playbook_id")):
            crits = s.get("criteria", [])
            # Normalise: criteria must be 1-5 (models sometimes use other scales,
            # e.g. /25 for SPIN); overall is always recomputed from criteria.
            for c in crits:
                sc = float(c.get("score", 0) or 0)
                if sc > 5:
                    sc = sc / 5
                c["score"] = int(max(1, min(5, round(sc))))
            overall = (round(sum(c["score"] for c in crits) / len(crits), 1)
                       if crits else float(s.get("overall", 0)))
            db.add(CallScore(call_id=call.id, playbook_id=s["playbook_id"],
                             overall=min(5.0, overall),
                             criteria=crits,
                             coaching=s.get("coaching", "")))
    call.status = "completed"
    call.error = None
    db.commit()
    log.info("Call %s completed", call.id)


def poll_ringcentral(db) -> int:
    """Safety net alongside the webhook: pull recently recorded calls from the call log.
    Looks back a short window (12h) so frequent polling stays light on the RC API."""
    from .ringcentral import queue_backfill
    added = queue_backfill(db, days=0.5)
    if added:
        log.info("Poller queued %d new calls", added)
    return added


def retention_purge(db) -> None:
    if settings.retention_days <= 0:
        return
    import os
    from ..models import Comment, ListenEvent
    cutoff = datetime.utcnow() - timedelta(days=settings.retention_days)
    old = db.query(Call).filter(Call.started_at < cutoff).all()
    for c in old:
        if c.audio_path and os.path.exists(c.audio_path):
            try:
                os.remove(c.audio_path)
            except OSError:
                pass
        db.query(Comment).filter(Comment.call_id == c.id).delete()
        db.query(ListenEvent).filter(ListenEvent.call_id == c.id).delete()
        db.delete(c)
    if old:
        db.commit()
        log.info("Retention purge removed %d calls", len(old))


def maybe_weekly_reports(db) -> None:
    """Each Monday, generate last week's coaching profile reports per team."""
    now = datetime.utcnow()
    if now.weekday() != 0:
        return
    end = datetime(now.year, now.month, now.day)
    start = end - timedelta(days=7)
    exists = db.query(Report).filter(Report.period_start == start,
                                     Report.report_type == "coaching_profiles").first()
    if exists:
        return
    from ..services.reports import generate_coaching_report
    try:
        generate_coaching_report(db, start, end, None)
        log.info("Weekly coaching report generated")
    except Exception:
        log.exception("Weekly report generation failed")


def maybe_weekly_videos(db) -> None:
    """Early Monday (>= 03:00 UTC / 04:00 BST): pre-generate this week's AI performance videos
    for enabled teams so the whole batch has time to finish rendering on HeyGen before the
    working day starts (~9am). Submission happens here; HeyGen then renders asynchronously, so
    we kick off early to leave a comfortable margin. Runs once per week."""
    now = datetime.utcnow()
    if now.weekday() != 0 or now.hour < 3:
        return
    from datetime import date
    from ..models import Setting
    from ..services.intelligence.videos import _this_monday, generate_all_weekly
    wk = _this_monday(date.today()).isoformat()
    row = db.get(Setting, "video_batch_week")
    if row and isinstance(row.value, dict) and row.value.get("week") == wk:
        return                                      # already generated this week
    try:
        generate_all_weekly(db)
    except Exception:
        log.exception("Weekly video pre-generation failed")
    if row:
        row.value = {"week": wk}
    else:
        db.add(Setting(key="video_batch_week", value={"week": wk}))
    db.commit()


# Transient states a call passes through while a worker thread owns it. If the process
# restarts mid-flight, these are re-queued on startup so no call is left stranded.
_INPROGRESS = ("processing", "downloading", "transcribing", "analyzing")


def _process_one(call_id: int) -> None:
    """Process a single already-claimed call on its own DB session (thread-safe)."""
    db = SessionLocal()
    try:
        call = db.get(Call, call_id)
        if not call:
            return
        try:
            process_call(db, call)
        except Exception as e:
            log.exception("Call %s failed", call_id)
            db.rollback()
            call = db.get(Call, call_id)
            if call:                                   # may have been deleted (dead dial)
                call.process_attempts = (call.process_attempts or 0) + 1
                call.error = str(e)[:2000]
                # Most failures are transient (recording not downloadable yet, an API
                # hiccup) — leave it 'failed'; the retry sweep re-queues it shortly. Only
                # give up after max_call_retries.
                call.status = "failed"
                db.commit()
    finally:
        db.close()


def _retry_failed(db) -> None:
    """Re-queue failed calls that still have retries left (spaced by the sweep interval),
    so transient failures self-heal once the recording/API is available."""
    n = (db.query(Call)
         .filter(Call.status == "failed",
                 Call.process_attempts < settings.max_call_retries)
         .update({Call.status: "queued"}, synchronize_session=False))
    if n:
        db.commit()
        log.info("Retry sweep re-queued %d failed call(s)", n)


def _expire_placeholders(db) -> None:
    """A call shown at call-end but with no recording after ~2h (e.g. recording disabled
    for that call) is marked 'no_recording' so it doesn't sit 'awaiting' forever."""
    cutoff = datetime.utcnow() - timedelta(hours=2)
    n = (db.query(Call).filter(Call.status == "awaiting_recording",
                               Call.rc_recording_id.is_(None),
                               Call.started_at < cutoff)
         .update({Call.status: "no_recording"}, synchronize_session=False))
    if n:
        db.commit()
        log.info("Marked %d placeholder(s) as no_recording", n)


def _requeue_interrupted(db) -> None:
    n = (db.query(Call).filter(Call.status.in_(_INPROGRESS))
         .update({Call.status: "queued"}, synchronize_session=False))
    if n:
        db.commit()
        log.info("Re-queued %d interrupted call(s)", n)


def _ingestion_loop() -> None:
    """Polling + housekeeping in its OWN thread, so a slow/hanging RingCentral poll can
    never stall call processing (the previous single-loop design could)."""
    last_poll = datetime.min
    last_ms_poll = datetime.min
    last_housekeeping = datetime.min
    last_holiday_sync = datetime.min
    while True:
        try:
            db = SessionLocal()
            try:
                if (settings.rc_poll_minutes > 0 and settings.ringcentral_client_id
                        and datetime.utcnow() - last_poll
                        > timedelta(minutes=settings.rc_poll_minutes)):
                    last_poll = datetime.utcnow()
                    try:
                        poll_ringcentral(db)
                    except Exception:
                        log.exception("RingCentral poll failed")
                if (settings.ms_poll_minutes > 0 and settings.ms_client_id
                        and datetime.utcnow() - last_ms_poll
                        > timedelta(minutes=settings.ms_poll_minutes)):
                    last_ms_poll = datetime.utcnow()
                    try:
                        from .msteams import poll_teams_recordings
                        poll_teams_recordings(db)
                    except Exception:
                        log.exception("Teams poll failed")
                # Keep in-app leave data fresh from the Holiday Tracker (the app now reads its
                # own LeaveRecord rows everywhere, not the tracker directly). Runs on boot + 6-hourly.
                if datetime.utcnow() - last_holiday_sync > timedelta(hours=6):
                    last_holiday_sync = datetime.utcnow()
                    try:
                        from ..modules.hr.imports import sync_holiday_from_tracker
                        from ..services.salesiq import trackers as _trk
                        if _trk.holiday_configured():
                            sync_holiday_from_tracker(db, None, None)
                    except Exception:
                        log.exception("holiday sync failed")
                if datetime.utcnow() - last_housekeeping > timedelta(hours=1):
                    last_housekeeping = datetime.utcnow()
                    try:
                        retention_purge(db)
                        _expire_placeholders(db)
                        maybe_weekly_reports(db)
                        maybe_weekly_videos(db)
                    except Exception:
                        log.exception("housekeeping failed")
            finally:
                db.close()
            _HEARTBEAT["ingestion"] = datetime.utcnow()
        except Exception:
            log.exception("ingestion loop tick failed")
        time.sleep(20)


def _processing_loop(conc: int) -> None:
    """Claim queued calls (newest first) and process up to `conc` in parallel. Does NO
    network polling, so it always keeps draining the queue."""
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=conc, thread_name_prefix="calliq-proc")
    inflight: set = set()
    last_retry = datetime.min
    last_disk = datetime.min
    while True:
        try:
            db = SessionLocal()
            try:
                if datetime.utcnow() - last_disk > timedelta(seconds=30):
                    last_disk = datetime.utcnow()
                    try:
                        _disk_guard(db)                 # keep the disk from filling up
                    except Exception:
                        log.exception("disk guard failed")
                if datetime.utcnow() - last_retry > timedelta(minutes=5):
                    last_retry = datetime.utcnow()
                    try:
                        _retry_failed(db)               # self-heal transient failures
                    except Exception:
                        log.exception("retry sweep failed")
                inflight = {f for f in inflight if not f.done()}
                while len(inflight) < conc:
                    call = (db.query(Call).filter(Call.status == "queued")
                            .order_by(Call.started_at.desc()).first())
                    if not call:
                        break
                    call.status = "processing"          # claim it
                    db.commit()
                    inflight.add(pool.submit(_process_one, call.id))
            finally:
                db.close()
            _HEARTBEAT["processing"] = datetime.utcnow()
        except Exception:
            log.exception("processing loop tick failed")   # never let the worker die
        time.sleep(POLL_SECONDS)


def run_forever() -> None:
    Base.metadata.create_all(bind=engine)
    conc = max(1, getattr(settings, "worker_concurrency", 3))
    log.info("Worker started (concurrency=%d, demo_mode=%s)", conc, settings.demo_mode)
    db0 = SessionLocal()
    try:
        _disk_guard(db0)              # free disk immediately on boot (downloads were failing)
    except Exception:
        log.exception("startup disk guard failed")
    try:
        _requeue_interrupted(db0)
    except Exception:
        log.exception("startup re-queue failed")
    finally:
        db0.close()
    threading.Thread(target=_ingestion_loop, daemon=True, name="calliq-ingest").start()
    _processing_loop(conc)   # main loop


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
