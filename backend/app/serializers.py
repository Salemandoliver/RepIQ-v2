"""Convert ORM objects to schema dicts shared across routers."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Call, Comment
from .schemas import CallListItem, CallDetail, CallTopicOut, UserOut, TurnOut, AnalysisOut, ScoreOut


def _topics(call: Call) -> list[CallTopicOut]:
    return [
        CallTopicOut(topic_id=ct.topic_id, name=ct.topic.name, color=ct.topic.color,
                     mentions=ct.mentions, first_mention_sec=ct.first_mention_sec)
        for ct in call.topics
    ]


def _overall(call: Call) -> float | None:
    if not call.scores:
        return None
    return round(sum(s.overall for s in call.scores) / len(call.scores), 1)


def comment_count(db: Session, call_id: int) -> int:
    return db.query(func.count(Comment.id)).filter(Comment.call_id == call_id).scalar() or 0


def contact_number(call: Call) -> str:
    """The customer-side phone number of a call."""
    return call.to_number if call.direction == "outbound" else call.from_number


def contact_call_counts(db: Session, numbers: set[str]) -> dict[str, int]:
    """How many calls exist (either direction) for each customer number — one batch query
    per column so call lists don't trigger N+1 lookups."""
    counts: dict[str, int] = {}
    nums = {n for n in numbers if n}
    if not nums:
        return counts
    for col in (Call.to_number, Call.from_number):
        for num, n in (db.query(col, func.count(Call.id))
                       .filter(col.in_(nums)).group_by(col).all()):
            counts[num] = counts.get(num, 0) + n
    return counts


def to_list_item(db: Session, call: Call, contact_calls: int | None = None) -> CallListItem:
    return CallListItem(
        id=call.id,
        host=UserOut.model_validate(call.host) if call.host else None,
        direction=call.direction,
        activity_type=call.activity_type,
        from_number=call.from_number,
        to_number=call.to_number,
        customer_name=call.customer_name,
        started_at=call.started_at,
        duration_sec=call.duration_sec,
        status=call.status,
        plays=call.plays,
        likes=call.likes,
        shares=call.shares,
        comments=comment_count(db, call.id),
        overall_score=_overall(call),
        contact_calls=contact_calls,
        topics=_topics(call),
    )


def to_detail(db: Session, call: Call) -> CallDetail:
    n = contact_call_counts(db, {contact_number(call)}).get(contact_number(call))
    base = to_list_item(db, call, contact_calls=n).model_dump()
    return CallDetail(
        **base,
        audio_url=f"/api/calls/{call.id}/audio" if call.audio_path else None,
        error=call.error,
        turns=[TurnOut.model_validate(t) for t in call.turns],
        analysis=AnalysisOut.model_validate(call.analysis) if call.analysis else None,
        scores=[ScoreOut.model_validate(s) for s in call.scores],
    )
