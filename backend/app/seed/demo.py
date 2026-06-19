"""Demo-mode seeder: generates a realistic synthetic dataset (reps, 90 days of calls,
transcripts, analyses, playbook scores, topics, listens, reports) so the whole app can
be evaluated before connecting RingCentral/Deepgram/Claude keys. Idempotent."""
import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..auth import hash_password
from ..models import (User, Team, Call, TranscriptTurn, CallAnalysis, CallScore,
                      CallTopic, Playbook, Topic, ListenEvent, Report, Comment)
from ..pipeline.metrics import compute_metrics

rng = random.Random(42)

REPS = [
    # (name, team, job_title, role)
    ("Alex Bain", "Value Sales Team", "Senior Account Exec", "recorder"),
    ("Ben Hedger", "Value Sales Team", "Sales Rep", "recorder"),
    ("Tom Pendlebery", "Value Sales Team", "Sales Rep", "recorder"),
    ("Sam Rolfe", "Value Sales Team", "Sales Rep", "recorder"),
    ("Joseph Jarra", "Volume Sales Team", "Sales Rep", "recorder"),
    ("Romeo Nuzi", "Volume Sales Team", "Sales Rep", "recorder"),
    ("Zain Yaqoob", "Volume Sales Team", "Sales Rep", "recorder"),
    ("David Lawal", "Volume Sales Team", "Sales Rep", "recorder"),
    ("Kamran Khanna", "Volume Sales Team", "Sales Rep", "recorder"),
    ("Alfie Potter", "Creators", "Sales Rep", "recorder"),
    ("Ben Copelin", "Creators", "Account Executive", "recorder"),
    ("Zabina Akthar", "Creators", "Account Executive", "recorder"),
    ("Freya Savage", "Volume Sales Team", "Coach", "analyst"),
    ("Elli Braybrooks", None, "Operations", "analyst"),
]
COLORS = ["#e91e63", "#7c3aed", "#2563eb", "#0891b2", "#059669", "#d97706",
          "#dc2626", "#9333ea", "#0d9488", "#ca8a04", "#4f46e5", "#be185d"]
COMPANIES = ["Royal Express", "Thames Valley Motors", "Bicester Bakery", "Aylesbury Print Co",
             "Oxford Dental Care", "Wycombe Fitness", "Banbury Builders", "Chiltern Cafe",
             "Milton Keynes Logistics", "Henley Estates", "Witney Vets", "Marlow Marketing"]

ACTIVITY_WEIGHTS = [("Outbound - Acquisition", 35), ("Outbound - In Life", 25),
                    ("Inbound - Call From Customer", 18), ("Service Call", 12),
                    ("Proposal", 6), ("Voicemail", 4)]

# --- transcript snippet templates -----------------------------------------
OPENERS_GOOD = [
    ("rep", "Good morning, it's {rep} from BT Local Business. I'm calling because a lot of "
            "{biz} owners around {town} are losing sales when their broadband drops during "
            "card payments — in one sentence: we fix that with a business-grade line that has "
            "a 4G backup built in. Have you had any drop-outs lately?"),
]
OPENERS_WEAK = [
    ("rep", "Hi, is that the business owner? It's {rep} calling from BT, erm, just doing a "
            "bit of a courtesy call really about your account and the contract you have with us."),
]
DISCOVERY = [
    ("rep", "How many people do you have working off the connection day to day?"),
    ("customer", "We've got about {n} staff, and the card machine runs off it too."),
    ("rep", "And when it goes down, what does that actually cost you in lost trade?"),
    ("customer", "Honestly, probably a couple of hundred pounds an hour on a Saturday."),
    ("rep", "Are you tied into a contract with {comp} at the moment, or are you out of term?"),
    ("customer", "We're with {comp}, I think the contract ended a few months back."),
]
OBJECTIONS = [
    ("customer", "To be honest we're quite busy, the shop's open, can you call back another time?"),
    ("rep", "Completely understand. Thirty seconds then — if I could show you how to stop the "
            "card machine dropping out and save on the line rental at the same time, would it "
            "be worth fifteen minutes on Thursday morning?"),
    ("customer", "Maybe, what would it cost?"),
    ("rep", "It depends on the speed you need, but most shops your size end up paying about "
            "the same as now with the backup included. Shall I pencil in Thursday at nine?"),
]
SERVICE_BODY = [
    ("customer", "The broadband's been dropping out since last Tuesday and it's affecting the tills."),
    ("rep", "I'm sorry to hear that — that's clearly costing you, so let's get it sorted today. "
            "Can I run a line check while we talk?"),
    ("customer", "Yes please, it's the main line ending {digits}."),
    ("rep", "Thanks. I can see some errors on the line since Tuesday. I'm going to book an "
            "Openreach engineer, and in the meantime I'll send a Hub with 4G backup so the "
            "tills stay up. Does tomorrow morning work for the engineer?"),
    ("customer", "Tomorrow morning is fine. Will this cost anything?"),
    ("rep", "The engineer visit is covered, and the backup hub is part of your Halo add-on. "
            "I'll text you the reference now and call you Friday to confirm it's stable."),
]
CLOSES_GOOD = [
    ("rep", "So to confirm: I'll send the contract for the new broadband and two lines to your "
            "email today, you'll sign by tomorrow, and I'll place the order Friday. I'll also "
            "call you Monday to confirm the engineer date. Anything else you need from me?"),
    ("customer", "No, that covers it. Thanks for your help."),
]
CLOSES_WEAK = [
    ("rep", "Alright, well, have a think about it and maybe give us a ring back if you're "
            "interested at some point."),
    ("customer", "Will do. Bye now."),
]
MOBILE_SNIPPET = [
    ("rep", "While I've got you — your mobiles, are they with us on EE or someone else? "
            "We can usually bundle SIMs in cheaper than a consumer plan."),
    ("customer", "They're personal Vodafone SIMs at the moment actually."),
]
SECURITY_SNIPPET = [
    ("rep", "One more thing: with card payments online you really want the security package — "
            "firewall, backup and phishing protection. Shall I include the cyber bundle quote?"),
    ("customer", "Go on then, include it in the quote."),
]

TOWNS = ["Oxford", "Aylesbury", "High Wycombe", "Banbury", "Bicester", "Watford",
         "Hemel Hempstead", "Milton Keynes"]
BIZ = ["retail", "hospitality", "trade", "professional services"]


def _phone() -> str:
    return "+447" + "".join(str(rng.randint(0, 9)) for _ in range(9))


def _landline() -> str:
    return "+441" + "".join(str(rng.randint(0, 9)) for _ in range(9))


def _build_turns(activity: str, rep: str, quality: float) -> list[tuple[str, str]]:
    """quality 0..1 drives which templates are used."""
    comp = rng.choice(["Virgin Media", "TalkTalk", "Sky Business", "Plusnet"])
    fills = {"rep": rep.split()[0], "town": rng.choice(TOWNS), "biz": rng.choice(BIZ),
             "n": rng.randint(3, 14), "comp": comp, "digits": rng.randint(1000, 9999)}
    parts: list[tuple[str, str]] = []
    if activity == "Voicemail":
        parts = [("rep", f"Hi, it's {fills['rep']} calling from BT Local Business for the "
                         "owner — I'll try you again tomorrow, or call us back on the local "
                         "Oxford number. Thanks, bye.")]
    elif activity == "Service Call" or activity == "Inbound - Call From Customer":
        parts += [("rep", f"Good morning, BT Local Business, {fills['rep']} speaking — how can I help?")]
        parts += SERVICE_BODY
        if rng.random() < 0.4:
            parts += SECURITY_SNIPPET if rng.random() < 0.5 else MOBILE_SNIPPET
        parts += CLOSES_GOOD if quality > 0.5 else CLOSES_WEAK
    else:
        parts += OPENERS_GOOD if quality > 0.55 else OPENERS_WEAK
        parts += DISCOVERY
        if rng.random() < 0.6:
            parts += OBJECTIONS
        if rng.random() < 0.45:
            parts += MOBILE_SNIPPET
        if rng.random() < 0.3:
            parts += SECURITY_SNIPPET
        parts += CLOSES_GOOD if quality > 0.45 else CLOSES_WEAK
    return [(s, t.format(**fills)) for s, t in parts]


def _make_timed_turns(parts: list[tuple[str, str]]) -> list[dict]:
    turns, t = [], 0.0
    for speaker, text in parts:
        words = len(text.split())
        dur = max(2.0, words / 2.6) * rng.uniform(0.85, 1.2)
        turns.append({"speaker": speaker, "start_sec": round(t, 1),
                      "end_sec": round(t + dur, 1), "text": text})
        t += dur + rng.uniform(0.4, 2.2)
    return turns


def _score_for(quality: float, crit: dict) -> int:
    base = 1 + quality * 4 + rng.uniform(-0.8, 0.8)
    return max(1, min(5, round(base)))


FEEDBACK = {
    5: "Excellent execution — {name} was handled exactly as the framework describes, with a "
       "clear, confident structure the rest of the team can copy.",
    4: "Strong: the rep covered {name} well, with only minor polish needed on phrasing.",
    3: "Partially done: elements of {name} were present but inconsistent; tighten the "
       "structure and make it deliberate rather than incidental.",
    2: "The rep touched on {name} but missed the key behaviours; the moment passed without "
       "the framework being applied.",
    1: "Missing: no evidence of {name} on this call — this is the first thing to rehearse "
       "in the next 1:1.",
}


def seed_demo_if_empty(db: Session) -> None:
    if db.query(Call).first():
        return

    teams = {t.name: t for t in db.query(Team).all()}
    users = []
    for i, (name, team, title, role) in enumerate(REPS):
        email = name.lower().replace(" ", ".") + "@btlocalbusiness.co.uk"
        u = db.query(User).filter(User.email == email).first()
        if not u:
            u = User(name=name, email=email, password_hash=hash_password("demo1234"),
                     role=role, job_title=title,
                     team_id=teams[team].id if team else None,
                     avatar_color=COLORS[i % len(COLORS)])
            db.add(u)
        users.append(u)
    db.commit()
    sellers = [u for u in users if u.role == "recorder"]
    playbooks = db.query(Playbook).all()
    topics = {t.name: t for t in db.query(Topic).all()}
    admin = db.query(User).filter(User.role == "admin").first()
    listeners = [u for u in users if u.role == "analyst"] + ([admin] if admin else [])

    # Rep skill levels (some better than others, like real teams)
    skill = {u.id: rng.uniform(0.3, 0.85) for u in sellers}

    now = datetime.utcnow()
    calls = []
    for day_off in range(90, -1, -1):
        day = now - timedelta(days=day_off)
        if day.weekday() >= 5:  # weekends quiet
            n_calls = rng.randint(0, 2)
        else:
            n_calls = rng.randint(4, 9)
        for _ in range(n_calls):
            rep = rng.choice(sellers)
            activity = rng.choices([a for a, _ in ACTIVITY_WEIGHTS],
                                   [w for _, w in ACTIVITY_WEIGHTS])[0]
            quality = min(1.0, max(0.0, skill[rep.id] + rng.uniform(-0.25, 0.25)))
            direction = "inbound" if activity.startswith("Inbound") else "outbound"
            started = day.replace(hour=rng.randint(9, 17), minute=rng.randint(0, 59),
                                  second=0, microsecond=0)
            parts = _build_turns(activity, rep.name, quality)
            turns = _make_timed_turns(parts)
            duration = int(turns[-1]["end_sec"]) + rng.randint(5, 90)
            company = rng.choice(COMPANIES)
            call = Call(host_id=rep.id, direction=direction, activity_type=activity,
                        from_number=_landline() if direction == "inbound" else _landline(),
                        to_number=_phone(), customer_name="Unknown Customer",
                        customer_company=company if rng.random() < 0.4 else "",
                        started_at=started, duration_sec=duration, status="completed")
            db.add(call)
            db.flush()

            rep_first = rep.name
            for t in turns:
                db.add(TranscriptTurn(call_id=call.id, speaker=t["speaker"],
                                      speaker_name=rep_first if t["speaker"] == "rep" else "Customer",
                                      start_sec=t["start_sec"], end_sec=t["end_sec"],
                                      text=t["text"]))

            m = compute_metrics(turns)
            text_all = " ".join(t["text"].lower() for t in turns)
            db.add(CallAnalysis(
                call_id=call.id,
                summary_intro=f"A sales representative from BT Business spoke with a customer "
                              f"about {activity.lower()} matters.",
                summary_points=[
                    "The customer discussed their current broadband and phone setup.",
                    "The representative explored the impact of connectivity issues on the business.",
                    "Options for business-grade broadband with 4G backup were presented.",
                    "Next steps were agreed at the end of the call." if quality > 0.45
                    else "The call ended without a firm commitment.",
                ],
                action_items=([{"owner": "Customer", "text": "Review the emailed quote and confirm."},
                               {"owner": rep.name, "text": "Send contract and follow up."}]
                              if quality > 0.4 and activity != "Voicemail" else []),
                key_points=[{"heading": "Broadband and Telephone Service",
                             "points": ["Customer relies on the connection for card payments.",
                                        "Business-grade line with backup discussed."]}],
                themes=[{"name": "Reliability", "description":
                         "Customer's main concern is connection reliability during trading hours."}],
                sentiment="positive" if quality > 0.6 else ("negative" if quality < 0.35 else "neutral"),
                **{k: m.get(k, 0) for k in ("talk_ratio", "longest_monologue_sec",
                                            "longest_customer_story_sec", "talking_speed_wpm",
                                            "patience_sec", "question_rate")},
            ))

            # Topic tagging by keyword scan
            for tname, topic in topics.items():
                hits = sum(text_all.count(k.lower()) for k in topic.keywords)
                if hits:
                    first = next((t["start_sec"] for t in turns
                                  if any(k.lower() in t["text"].lower() for k in topic.keywords)), 0)
                    db.add(CallTopic(call_id=call.id, topic_id=topic.id,
                                     mentions=hits, first_mention_sec=first))

            # Playbook scoring
            if activity != "Voicemail":
                for p in playbooks:
                    if p.activity_types and activity not in p.activity_types:
                        continue
                    crits = []
                    for c in p.criteria:
                        sc = _score_for(quality, c)
                        ev_turn = rng.choice(turns)
                        crits.append({
                            "key": c["key"], "name": c["name"], "score": sc,
                            "feedback": FEEDBACK[sc].format(name=c["name"].lower()),
                            "evidence": [{"speaker": rep_first if ev_turn["speaker"] == "rep"
                                          else "Customer",
                                          "at_sec": ev_turn["start_sec"]}],
                        })
                    overall = round(sum(c["score"] for c in crits) / len(crits), 1)
                    db.add(CallScore(
                        call_id=call.id, playbook_id=p.id, overall=overall, criteria=crits,
                        coaching=f"{rep_first} showed "
                                 f"{'strong' if overall >= 3.5 else 'developing'} fundamentals "
                                 f"on this call. Strengths: clear product knowledge and a "
                                 f"polite, professional manner. Focus areas: "
                                 f"{', '.join(c['name'].lower() for c in sorted(crits, key=lambda x: x['score'])[:2])}. "
                                 f"Recommended: role-play the opener and practise closing with "
                                 f"a specific, time-bound next step."))
            calls.append(call)

    db.commit()

    # Listen events for live feed / trending / coaching stats
    recent = [c for c in calls if c.started_at > now - timedelta(days=30)]
    for _ in range(min(400, len(recent) * 2)):
        c = rng.choice(recent)
        listener = rng.choice(listeners + sellers)
        db.add(ListenEvent(user_id=listener.id, call_id=c.id,
                           listened_at=c.started_at + timedelta(hours=rng.randint(1, 96))))
        c.plays += 1
    db.commit()

    # A few comments
    for _ in range(40):
        c = rng.choice(calls)
        db.add(Comment(call_id=c.id, user_id=rng.choice(listeners + sellers).id,
                       body=rng.choice(["Great objection handling here 👏",
                                        "Listen to the opener — textbook.",
                                        "We should use this in Friday's team coaching.",
                                        "Customer gave a strong buying signal at the midpoint."]),
                       at_sec=rng.uniform(10, 300)))
    db.commit()

    # Historic weekly reports
    from ..services.reports import generate_coaching_report
    for w in range(4, 0, -1):
        end = (now - timedelta(days=now.weekday())) - timedelta(weeks=w - 1)
        end = end.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=7)
        try:
            generate_coaching_report(db, start, end, None)
        except Exception:
            pass
    db.commit()
