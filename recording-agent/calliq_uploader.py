#!/usr/bin/env python3
"""CallIQ recording uploader — watches a folder for new call recordings and uploads each
one to the CallIQ ingestion endpoint (POST /api/recordings/upload).

Built for the BT Local Business setup: a recorder saves Teams call audio to
C:\\CallIQ\\recordings as WAV files named like `calliq_2026-06-19_09-30-00` (no extension).
This agent watches that folder, waits until a file has finished being written, uploads it
with the rep's email + the recording time, then moves it into `processed\\` so it is never
sent twice.

The files have no extension, so the agent works out the real format from the file's
contents (magic bytes) and defaults to WAV; it tags the upload with the correct filename
extension + content-type so transcription gets the right audio type.

Configuration (lowest to highest priority): defaults -> config.ini next to this file ->
environment variables (CALLIQ_*). See config.example.ini and the README.

Run continuously (recommended, via Task Scheduler at logon):
    python calliq_uploader.py
Process whatever is waiting and exit:
    python calliq_uploader.py --once
Validate config + server reachability (uploads nothing):
    python calliq_uploader.py --check
Show each waiting file's detected format + parsed recording time (uploads nothing):
    python calliq_uploader.py --inspect
"""
from __future__ import annotations

import argparse
import configparser
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("The 'requests' library is required. Install it with:  pip install requests")

# Known audio extensions (files may also arrive with NO extension — handled by sniffing).
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".webm"}
SKIP_SUFFIXES = (".tmp", ".part", ".partial", ".crdownload", ".download", ".log", ".ini",
                 ".txt", ".json", ".db")
EXT_CTYPE = {"wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4",
             "mp4": "video/mp4", "ogg": "audio/ogg", "webm": "audio/webm"}
# Recording filename pattern: calliq_2026-06-19_09-30-00 (date_time, local machine time).
TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[_ T](\d{2})[-:](\d{2})[-:](\d{2})")
HERE = Path(__file__).resolve().parent

DEFAULTS = {
    "api_url": "https://repiq.co.uk/api/recordings/upload",
    "api_key": "",
    "rep_email": "",
    "watch_dir": r"C:\CallIQ\recordings",
    "processed_subdir": "processed",  # successful uploads moved here
    "default_ext": "wav",             # used when content can't be sniffed (files are WAV)
    "poll_seconds": "10",
    "stable_seconds": "15",           # file size must hold steady this long = recorder finished
    "rep_from_subfolder": "false",    # true => each immediate subfolder is a rep's email
    "max_attempts": "5",              # transient (network/5xx) retries before moving to failed/
    "timeout_seconds": "300",
}

log = logging.getLogger("calliq.uploader")


# --------------------------------------------------------------------------- config
def load_config() -> dict:
    cfg = dict(DEFAULTS)
    ini = HERE / "config.ini"
    if ini.exists():
        parser = configparser.ConfigParser()
        parser.read(ini)
        if parser.has_section("uploader"):
            for k, v in parser.items("uploader"):
                if v != "":
                    cfg[k.lower()] = v
    for k in list(cfg.keys()):                       # env overrides win (per-machine setup)
        env = os.environ.get("CALLIQ_" + k.upper())
        if env not in (None, ""):
            cfg[k] = env
    cfg["poll_seconds"] = int(cfg["poll_seconds"])
    cfg["stable_seconds"] = int(cfg["stable_seconds"])
    cfg["max_attempts"] = int(cfg["max_attempts"])
    cfg["timeout_seconds"] = int(cfg["timeout_seconds"])
    cfg["rep_from_subfolder"] = str(cfg["rep_from_subfolder"]).lower() in ("1", "true", "yes", "on")
    cfg["default_ext"] = (cfg.get("default_ext") or "").lstrip(".").lower()
    cfg["processed_subdir"] = cfg.get("processed_subdir") or "processed"
    return cfg


def setup_logging() -> None:
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)
    try:
        fh = RotatingFileHandler(HERE / "uploader.log", maxBytes=1_000_000, backupCount=3)
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass


# ---------------------------------------------------------------------- file helpers
def is_candidate(p: Path) -> bool:
    """A file we should consider uploading: a known audio extension OR no extension at all
    (the recorder writes extensionless WAVs). Skips temp/partial/hidden and non-audio files."""
    name = p.name.lower()
    if name.startswith((".", "~")) or name.endswith(SKIP_SUFFIXES):
        return False
    suffix = p.suffix.lower()
    return suffix in AUDIO_EXTS or suffix == ""


def sniff_ext(p: Path) -> str | None:
    """Detect the real audio format from the file's magic bytes (extension may be missing)."""
    try:
        with open(p, "rb") as f:
            head = f.read(16)
    except OSError:
        return None
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "mp3"
    if head[4:8] == b"ftyp":
        return "m4a" if head[8:11] == b"M4A" else "mp4"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    return None


def resolve_ext(p: Path, cfg: dict) -> str:
    """The extension to upload the file as: real (allowed) suffix, else sniffed, else the
    configured default, else wav."""
    suffix = p.suffix.lower().lstrip(".")
    if ("." + suffix) in AUDIO_EXTS:
        return suffix
    return sniff_ext(p) or cfg.get("default_ext") or "wav"


def is_stable(p: Path, stable_seconds: int) -> bool:
    """True if the file hasn't changed size and hasn't been touched for `stable_seconds`."""
    try:
        size1 = p.stat().st_size
    except OSError:
        return False
    if size1 == 0:
        return False
    time.sleep(min(stable_seconds, 3))
    try:
        st = p.stat()
        return st.st_size == size1 and (time.time() - st.st_mtime) >= stable_seconds
    except OSError:
        return False


def recorded_at_iso(p: Path) -> str:
    """ISO-8601 UTC timestamp. Prefer the time encoded in the `calliq_<date>_<time>` filename
    (interpreted as local machine time), else the file's creation/modification time."""
    m = TS_RE.search(p.name)
    if m:
        try:
            local = datetime.strptime(f"{m.group(1)} {m.group(2)}-{m.group(3)}-{m.group(4)}",
                                      "%Y-%m-%d %H-%M-%S")
            return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    st = p.stat()
    ts = getattr(st, "st_birthtime", None) or st.st_ctime or st.st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rep_for(p: Path, watch: Path, cfg: dict) -> str | None:
    stem = p.stem
    if "__" in stem and "@" in stem.split("__", 1)[0]:          # rep@email__file
        return stem.split("__", 1)[0].strip().lower()
    if cfg["rep_from_subfolder"]:                                # <watch>/rep@email/file
        try:
            rel = p.relative_to(watch)
        except ValueError:
            rel = None
        if rel and len(rel.parts) >= 2 and "@" in rel.parts[0]:
            return rel.parts[0].strip().lower()
    return (cfg["rep_email"] or "").strip().lower() or None      # one rep per machine


# --------------------------------------------------------------------------- upload
def upload(p: Path, rep: str, cfg: dict) -> tuple[bool, bool]:
    """Returns (ok, permanent_failure). permanent_failure=True means don't retry."""
    ext = resolve_ext(p, cfg)
    send_name = p.name if p.suffix.lower().lstrip(".") == ext else f"{p.name}.{ext}"
    ctype = EXT_CTYPE.get(ext, "audio/wav")
    try:
        with open(p, "rb") as fh:
            files = {"file": (send_name, fh, ctype)}
            data = {"repId": rep, "recordedAt": recorded_at_iso(p)}
            r = requests.post(cfg["api_url"], headers={"X-Api-Key": cfg["api_key"]},
                              files=files, data=data, timeout=cfg["timeout_seconds"])
    except requests.RequestException as e:
        log.warning("  network error uploading %s: %s", p.name, str(e)[:160])
        return False, False
    if r.status_code in (200, 202):
        try:
            body = r.json()
        except ValueError:
            body = {}
        log.info("  uploaded %s (%s) -> call id=%s status=%s", p.name, ext,
                 body.get("id"), body.get("status"))
        return True, False
    permanent = r.status_code in (400, 401, 403, 404, 413, 415, 422)
    log.error("  upload failed %s: HTTP %s %s%s", p.name, r.status_code, r.text[:160],
              "" if permanent else " (will retry)")
    return False, permanent


def move_into(p: Path, watch: Path, sub: str) -> None:
    try:
        rel = p.relative_to(watch)
        dest = watch / sub / rel
    except ValueError:
        dest = watch / sub / p.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    target, n = dest, 1
    while target.exists():
        target = dest.with_name(f"{dest.stem}_{n}{dest.suffix}")
        n += 1
    try:
        p.rename(target)
    except OSError as e:
        log.warning("  couldn't move %s -> %s: %s", p.name, sub, e)


def iter_candidates(watch: Path, cfg: dict):
    holding = {cfg["processed_subdir"], "failed", "uploaded"}
    for root, dirs, names in os.walk(watch):
        dirs[:] = [d for d in dirs if d not in holding]
        for name in names:
            p = Path(root) / name
            if is_candidate(p):
                yield p


# --------------------------------------------------------------------------- run loop
def process_once(watch: Path, cfg: dict, attempts: dict) -> int:
    done = 0
    for p in iter_candidates(watch, cfg):
        if not is_stable(p, cfg["stable_seconds"]):
            continue
        rep = rep_for(p, watch, cfg)
        if not rep:
            log.error("  no rep email for %s — set rep_email (or use a rep@email subfolder/prefix).", p.name)
            move_into(p, watch, "failed")
            continue
        ok, permanent = upload(p, rep, cfg)
        key = str(p)
        if ok:
            attempts.pop(key, None)
            move_into(p, watch, cfg["processed_subdir"])
            done += 1
        elif permanent:
            attempts.pop(key, None)
            move_into(p, watch, "failed")
        else:
            attempts[key] = attempts.get(key, 0) + 1
            if attempts[key] >= cfg["max_attempts"]:
                log.error("  giving up on %s after %d attempts", p.name, attempts[key])
                attempts.pop(key, None)
                move_into(p, watch, "failed")
    return done


def inspect(watch: Path, cfg: dict) -> int:
    files = list(iter_candidates(watch, cfg))
    if not files:
        log.info("No candidate files in %s", watch)
        return 0
    log.info("Found %d file(s) in %s:", len(files), watch)
    for p in files:
        log.info("  %-40s format=%-5s recordedAt=%s rep=%s", p.name, resolve_ext(p, cfg),
                 recorded_at_iso(p), rep_for(p, watch, cfg) or "(none!)")
    return 0


def check(cfg: dict, watch: Path) -> int:
    problems = []
    if not cfg["api_key"]:
        problems.append("api_key is empty (must match RECORDINGS_API_KEY on the server)")
    if not cfg["rep_email"] and not cfg["rep_from_subfolder"]:
        problems.append("rep_email is empty and rep_from_subfolder is off — uploads can't be attributed")
    if not watch.exists():
        problems.append(f"watch_dir does not exist: {watch}")
    log.info("api_url   : %s", cfg["api_url"])
    log.info("watch_dir : %s", watch)
    log.info("rep_email : %s", cfg["rep_email"] or ("(per-subfolder)" if cfg["rep_from_subfolder"] else "(none!)"))
    log.info("default_ext: %s", cfg["default_ext"] or "wav")
    try:
        base = cfg["api_url"].split("/api/")[0]
        r = requests.get(base + "/api/health", timeout=15)
        log.info("server    : %s -> HTTP %s %s", base, r.status_code, r.text[:80])
    except requests.RequestException as e:
        problems.append(f"could not reach server: {str(e)[:120]}")
    if problems:
        for pb in problems:
            log.error("CONFIG: %s", pb)
        return 1
    log.info("Config looks good. Drop a recording into the watch folder and run without --check.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="CallIQ recording uploader")
    ap.add_argument("--once", action="store_true", help="process current files then exit")
    ap.add_argument("--check", action="store_true", help="validate config + server, upload nothing")
    ap.add_argument("--inspect", action="store_true", help="list waiting files + detected format/time")
    args = ap.parse_args()

    setup_logging()
    cfg = load_config()
    if not cfg["watch_dir"]:
        log.error("watch_dir is not set. Edit config.ini (or set CALLIQ_WATCH_DIR).")
        return 2
    watch = Path(cfg["watch_dir"]).expanduser().resolve()

    if args.inspect:
        watch.mkdir(parents=True, exist_ok=True)
        return inspect(watch, cfg)
    if args.check:
        return check(cfg, watch)
    if not cfg["api_key"]:
        log.error("api_key is not set. Edit config.ini (or set CALLIQ_API_KEY).")
        return 2
    watch.mkdir(parents=True, exist_ok=True)

    attempts: dict[str, int] = {}
    if args.once:
        n = process_once(watch, cfg, attempts)
        log.info("Done — uploaded %d file(s).", n)
        return 0

    log.info("Watching %s every %ss (Ctrl+C to stop)…", watch, cfg["poll_seconds"])
    try:
        while True:
            process_once(watch, cfg, attempts)
            time.sleep(cfg["poll_seconds"])
    except KeyboardInterrupt:
        log.info("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
