"""One-time RingCentral setup: create the webhook subscription and optionally backfill
recent recorded calls.

Usage (inside the api container or a local venv with .env configured):
  python -m scripts.setup_ringcentral --webhook https://your-domain/api/webhooks/ringcentral
  python -m scripts.setup_ringcentral --backfill 30
"""
import argparse
from datetime import datetime

from app.db import Base, engine, SessionLocal
from app.models import Call, User
from app.pipeline.ringcentral import RingCentralClient


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--webhook", help="Public URL of the webhook endpoint")
    ap.add_argument("--backfill", type=int, default=0, help="Backfill N days of recorded calls")
    args = ap.parse_args()

    Base.metadata.create_all(bind=engine)
    rc = RingCentralClient()

    if args.webhook:
        sub = rc.setup_subscription(args.webhook)
        print(f"Subscription created: id={sub.get('id')} expires={sub.get('expirationTime')}")

    if args.backfill:
        db = SessionLocal()
        try:
            records = rc.backfill_call_log(args.backfill)
            added = 0
            for r in records:
                if db.query(Call).filter(Call.rc_session_id == r["rc_session_id"]).first():
                    continue
                host = (db.query(User).filter(User.rc_extension_id == r["extension_id"]).first()
                        if r["extension_id"] else None)
                direction = "outbound" if r["direction"].startswith("out") else "inbound"
                db.add(Call(
                    host_id=host.id if host else None,
                    direction=direction,
                    activity_type=("Outbound - Acquisition" if direction == "outbound"
                                   else "Inbound - Call From Customer"),
                    from_number=r["from_number"], to_number=r["to_number"],
                    started_at=datetime.fromisoformat(r["started_at"].replace("Z", "+00:00"))
                    .replace(tzinfo=None) if r["started_at"] else datetime.utcnow(),
                    duration_sec=r["duration_sec"],
                    status="queued",
                    rc_session_id=r["rc_session_id"], rc_recording_id=r["rc_recording_id"],
                ))
                added += 1
            db.commit()
            print(f"Backfill queued {added} calls (worker will process them).")
        finally:
            db.close()


if __name__ == "__main__":
    main()
