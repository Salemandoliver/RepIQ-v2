"""Baseline data that must always exist: admin user, teams, topics, playbooks, vocabulary.
Idempotent — safe to run on every startup."""
from sqlalchemy.orm import Session

from ..auth import hash_password
from ..models import User, Team, Topic, Playbook, VocabularyTerm, Setting, AskPreset

DEFAULT_ASK_PRESETS = [
    ("Deal blockers", "What are the deal blockers or obstacles preventing this customer "
     "from moving forward? List each with the moment it came up."),
    ("Will they sign?", "Based on this conversation, how likely is the customer to sign or "
     "proceed? Give a percentage estimate with the buying signals and risks you base it on."),
    ("SPIN check", "Briefly evaluate this call against the SPIN framework: which Situation, "
     "Problem, Implication and Need-Payoff questions were asked (credit intent over exact "
     "wording), and what was missed?"),
    ("Next steps", "What next steps were agreed on this call, who owns each one, and by when?"),
    ("Customer sentiment", "How did the customer feel during this call? Note any frustration, "
     "hesitation or buying signals, with timestamps."),
    ("Objections raised", "What objections did the customer raise and how well did the rep "
     "handle each one?"),
]

DEFAULT_TOPICS = [
    ("Connectivity", ["broadband", "fibre", "leased line", "wifi", "internet", "connection",
                      "router", "speed", "outage", "downtime"], "#ef4444"),
    ("Mobile", ["mobile", "sim", "handset", "5g", "roaming", "data plan", "ee"], "#f97316"),
    ("Security", ["security", "firewall", "cyber", "antivirus", "phishing", "backup"], "#dc2626"),
    ("Competitors", ["virgin", "sky", "talktalk", "vodafone", "o2", "plusnet", "competitor"],
     "#b91c1c"),
]

COLD_CALL_CRITERIA = [
    {"key": "first15", "name": "First-15-second relevance",
     "description": "Opens with a persona-tied pain point and a one-sentence value "
                    "proposition within the first moments, not a procedural intro.",
     "weight": 1},
    {"key": "signal", "name": "Signal capture",
     "description": "Asks structured diagnostic questions, tests problem relevance, "
                    "distinguishes polite acquiescence from genuine interest.",
     "weight": 1},
    {"key": "objection", "name": "Objection pivot",
     "description": "When brushed off, restates relevance concisely and reframes value "
                    "before exiting; collaborative not confrontational.",
     "weight": 1},
    {"key": "next_step", "name": "Concrete next step",
     "description": "Closes with a specific, time-bound next action agreed by the customer.",
     "weight": 1},
]

SERVICE_CRITERIA = [
    {"key": "diagnose", "name": "Issue diagnosis",
     "description": "Establishes the full picture of the fault/request before solutioning.",
     "weight": 1},
    {"key": "ownership", "name": "Ownership & empathy",
     "description": "Acknowledges impact on the customer's business, takes clear ownership.",
     "weight": 1},
    {"key": "resolution", "name": "Resolution & expectations",
     "description": "Sets clear expectations on what happens next and when.", "weight": 1},
    {"key": "opportunity", "name": "Opportunity spotting",
     "description": "Identifies legitimate upsell/cross-sell signals without being pushy.",
     "weight": 1},
]

SPIN_CRITERIA = [
    {"key": "situation", "name": "Situation questions",
     "description": "Establishes the customer's current setup (provider, contract, sites, "
                    "usage) with efficient fact-finding, without over-interrogating.",
     "weight": 1},
    {"key": "problem", "name": "Problem questions",
     "description": "Surfaces difficulties and dissatisfactions with the current situation "
                    "(outages, cost, support, coverage) the customer actually feels.",
     "weight": 1},
    {"key": "implication", "name": "Implication questions",
     "description": "Develops the cost/consequence of those problems (lost revenue, downtime, "
                    "compliance risk) so the customer feels the impact.",
     "weight": 1},
    {"key": "need_payoff", "name": "Need-payoff questions",
     "description": "Gets the customer to articulate the value of a solution themselves, "
                    "building desire before any pitch.",
     "weight": 1},
]

DEFAULT_VOCAB = ["BT Business", "BTnet", "EE", "Openreach", "Cloud Voice", "Halo",
                 "leased line", "SoGEA", "FTTP", "ATA adapter", "Hub", "digital voice"]


def ensure_bootstrap(db: Session) -> None:
    if not db.query(Team).first():
        for name in ("Creators", "Value Sales Team", "Volume Sales Team"):
            db.add(Team(name=name))
        db.commit()

    if not db.query(User).filter(User.email == "admin@btlocalbusiness.co.uk").first():
        db.add(User(name="Salem Zerti", email="admin@btlocalbusiness.co.uk",
                    password_hash=hash_password("demo1234"), role="admin",
                    job_title="Managing Director", avatar_color="#7c3aed"))
        db.commit()

    if not db.query(Topic).first():
        for name, kw, color in DEFAULT_TOPICS:
            db.add(Topic(name=name, keywords=kw, color=color))
        db.commit()

    if not db.query(Playbook).first():
        db.add(Playbook(
            name="Cold Call",
            description="Outbound acquisition cold-call framework.",
            activity_types=["Outbound - Acquisition"],
            criteria=COLD_CALL_CRITERIA))
        db.add(Playbook(
            name="Service & In-Life",
            description="Service call and in-life account management framework.",
            activity_types=["Service Call", "Outbound - In Life",
                            "Inbound - Call From Customer", "Proposal"],
            criteria=SERVICE_CRITERIA))
        db.add(Playbook(
            name="SPIN Selling",
            description="SPIN questioning framework: Situation, Problem, Implication, "
                        "Need-payoff. The benchmark for our best discovery calls.",
            activity_types=["Outbound - Acquisition", "Outbound - In Life",
                            "Inbound - Call From Customer", "Proposal", "Teams Meeting"],
            criteria=SPIN_CRITERIA))
        db.commit()

    if not db.query(VocabularyTerm).first():
        for t in DEFAULT_VOCAB:
            db.add(VocabularyTerm(term=t))
        db.commit()

    if not db.query(AskPreset).first():
        for i, (name, prompt) in enumerate(DEFAULT_ASK_PRESETS):
            db.add(AskPreset(name=name, prompt=prompt, position=i))
        db.commit()

    if not db.get(Setting, "ai_context"):
        db.add(Setting(key="ai_context", value={
            "text": "We are BT Local Business Oxford & Bucks (Synvestment Ltd), selling BT "
                    "broadband, phone, mobile (EE) and security products to small businesses "
                    "in Oxfordshire, Buckinghamshire and Hertfordshire."}))
        db.commit()
