"""SalesIQ role mapping (by job title), tracker name matching, and target settings.

Targets come from the job-title pay plans (monthly SOV per pillar). Resolution order for a
user: per-user override (Settings) > job-title target > rep default. Operations / unknown
non-sales roles get no SalesIQ access.
"""
from __future__ import annotations

import re

from ...models import Setting, Team, User

TARGETS_KEY = "salesiq_targets"

# Monthly SOV (£) targets per pillar, from the 2026/27 pay plans.
JOB_TITLE_TARGETS = {
    "sales executive": {"connectivity": 27500, "cloud": 18000, "mobile": 5000, "leads": 5},
    "senior sales executive": {"connectivity": 50000, "cloud": 25000, "mobile": 5000},
    "business development manager": {"connectivity": 75000, "cloud": 25000, "mobile": 5000, "leads": 5},
    "business creator": {"leads": 40},
    "head of sales": {"connectivity": 153939, "cloud": 90178, "mobile": 46624},
    "sales director": {"connectivity": 153939, "cloud": 90178, "mobile": 46624},
    "sales manager": {"connectivity": 153939, "cloud": 90178, "mobile": 46624},
}

# Opportunities-created target (Activity Tracker): every sales rep, 2 per working day.
OPPS_TARGET_PER_DAY = 2

_ALIASES = {
    "sales rep": "sales executive", "rep": "sales executive", "salesperson": "sales executive",
    "sales exec": "sales executive", "snr sales executive": "senior sales executive",
    "senior sales exec": "senior sales executive",
    "bdm": "business development manager", "business dev manager": "business development manager",
    "business creators": "business creator", "lead generator": "business creator", "bc": "business creator",
    "md": "managing director", "managing director": "head of sales",
}

MANAGER_TITLES = {"head of sales", "sales director", "managing director", "sales manager"}
REP_TITLES = {"sales executive", "senior sales executive", "business development manager"}

# Activity targets — all reps (pay-plan KPIs)
ACTIVITY_TARGET = {"talkMinsPerDay": 90, "dialsPerDay": 80}


def _norm_title(t: str | None) -> str:
    t = re.sub(r"\s+", " ", (t or "").strip().lower())
    return _ALIASES.get(t, t)


def salesiq_role(role: str, job_title: str | None, team_name: str | None) -> str | None:
    """rep | bc | manager, or None for no SalesIQ access (e.g. Operations)."""
    if role == "admin":
        return "manager"
    t = _norm_title(job_title)
    tm = (team_name or "").lower()
    if t in MANAGER_TITLES:
        return "manager"
    if t == "business creator" or "creator" in tm:
        return "bc"
    if "operation" in t or t == "ops" or "operation" in tm:
        return None
    if t in REP_TITLES or any(k in tm for k in ("sales", "value", "volume")):
        return "rep"
    return None      # unknown non-sales role -> no SalesIQ


def role_for_user(db, user: User) -> str | None:
    team_name = None
    if user.team_id:
        team = db.get(Team, user.team_id)
        team_name = team.name if team else None
    return salesiq_role(user.role, user.job_title, team_name)


# ------------------------------------------------------------- name matching
# First-name nicknames -> canonical, so "Matt Evans" matches "Matthew Evans" and the
# tracker abbreviations match CallIQ user names. Extend as needed.
NAME_ALIASES = {
    "matt": "matthew", "matty": "matthew", "tom": "thomas", "tommy": "thomas",
    "ben": "benjamin", "benny": "benjamin", "sam": "samuel", "sammy": "samuel",
    "dave": "david", "dan": "daniel", "danny": "daniel", "mike": "michael", "mick": "michael",
    "chris": "christopher", "joe": "joseph", "joey": "joseph", "jon": "jonathan",
    "jono": "jonathan", "jonny": "jonathan", "alex": "alexander", "andy": "andrew",
    "rob": "robert", "bob": "robert", "will": "william", "nick": "nicholas",
    "steve": "stephen", "kam": "kamran", "maggie": "margaret", "meg": "margaret",
}


def _tokens(s: str | None) -> list[str]:
    return [t for t in re.sub(r"[^a-z ]", " ", (s or "").lower()).split() if t]


def _canon(tok: str) -> str:
    return NAME_ALIASES.get(tok, tok)


def _name_part_match(x: str, y: str) -> bool:
    """Two name parts match if equal, alias-equal, or one is a prefix/initial of the other
    (handles 'Matt'/'Matthew', 'E'/'Evans')."""
    cx, cy = _canon(x), _canon(y)
    if cx == cy:
        return True
    return min(len(x), len(y)) >= 1 and (cx.startswith(cy) or cy.startswith(cx)
                                         or x.startswith(y) or y.startswith(x))


def agent_matches(user_name: str, agent_name: str | None) -> bool:
    """Tolerant match between a CallIQ user name and a tracker agent name: same first name
    (incl. nicknames), and same surname (incl. initials/abbreviations) when both are given."""
    u, a = _tokens(user_name), _tokens(agent_name)
    if not u or not a:
        return False
    if u == a:
        return True
    if not _name_part_match(u[0], a[0]):            # first names must reconcile
        return False
    if len(u) == 1 or len(a) == 1:                 # one side first-name-only -> accept
        return True
    return _name_part_match(u[-1], a[-1])          # else surnames must reconcile


def user_agent_match(user, agent_name: str | None) -> bool:
    """Match a CallIQ user to a tracker agent name, trying their full name and the optional
    admin-set short_name (the name used in the trackers)."""
    if agent_matches(getattr(user, "name", None), agent_name):
        return True
    sn = getattr(user, "short_name", None)
    return bool(sn) and agent_matches(sn, agent_name)


# ------------------------------------------------------------- targets
def _seed_by_title() -> dict:
    return {t: dict(v) for t, v in JOB_TITLE_TARGETS.items()}


def get_all_targets(db) -> dict:
    row = db.get(Setting, TARGETS_KEY)
    val = row.value if (row and isinstance(row.value, dict)) else {}
    by_title = _seed_by_title()
    for t, v in (val.get("byTitle") or {}).items():
        by_title[_norm_title(t)] = {**by_title.get(_norm_title(t), {}), **(v or {})}
    return {"byTitle": by_title, "reps": val.get("reps") or {}, "activity": dict(ACTIVITY_TARGET)}


def targets_for(db, user: User, role: str | None = None) -> dict:
    """Resolved monthly target for a user: job-title pillars (+ per-user override) +
    derived monthly/quarterly/annual SOV + activity targets."""
    data = get_all_targets(db)
    title = _norm_title(user.job_title)
    base = data["byTitle"].get(title)
    if base is None and role == "rep":
        base = data["byTitle"].get("sales executive", {})
    base = dict(base or {})
    base.update(data["reps"].get(str(user.id)) or {})

    conn = float(base.get("connectivity") or 0)
    cloud = float(base.get("cloud") or 0)
    mobile = float(base.get("mobile") or 0)
    monthly = conn + cloud + mobile
    return {
        "title": title or None,
        "connectivity": conn, "cloud": cloud, "mobile": mobile,
        "monthlySov": monthly, "quarterlySov": monthly * 3, "annualSov": monthly * 12,
        "leads": base.get("leads"),
        "talkMinsPerDay": ACTIVITY_TARGET["talkMinsPerDay"],
        "dialsPerDay": ACTIVITY_TARGET["dialsPerDay"],
    }


def save_targets(db, by_title: dict | None, reps: dict | None) -> dict:
    row = db.get(Setting, TARGETS_KEY)
    current = row.value if (row and isinstance(row.value, dict)) else {}
    if by_title is not None:
        current["byTitle"] = {_norm_title(t): v for t, v in by_title.items()}
    if reps is not None:
        current["reps"] = reps
    if row:
        row.value = current
    else:
        db.add(Setting(key=TARGETS_KEY, value=current))
    db.commit()
    return get_all_targets(db)
