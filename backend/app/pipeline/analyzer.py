"""LLM analysis of a transcribed call using the Claude API.

One structured call produces: summary, action items, key points, themes,
topic detection, playbook scoring with timestamped evidence, and coaching notes.
"""
import json
import logging

import httpx

from ..config import settings

log = logging.getLogger("calliq.analyzer")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def _format_transcript(turns: list[dict], rep_name: str, max_chars: int = 60000) -> str:
    lines = []
    for t in turns:
        mm, ss = divmod(int(t["start_sec"]), 60)
        who = rep_name if t["speaker"] == "rep" else "Customer"
        lines.append(f"[{mm:02d}:{ss:02d}] {who}: {t['text']}")
    text = "\n".join(lines)
    return text[:max_chars]


def _claude(system: str, user: str, model: str, max_tokens: int = 4000) -> str:
    resp = httpx.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def _extract_json(text: str) -> dict:
    """Tolerant JSON extraction (Claude sometimes wraps in ```json fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def analyze_call(turns: list[dict], rep_name: str, activity_type: str,
                 playbooks: list[dict], topics: list[dict],
                 ai_context: str = "") -> dict:
    """playbooks: [{id, name, description, criteria:[{key,name,description,weight}]}]
    topics: [{id, name, keywords}]
    Returns {analysis:{...}, topic_ids:[{topic_id, mentions, first_mention_sec}],
             scores:[{playbook_id, overall, criteria:[...], coaching}]}"""
    transcript = _format_transcript(turns, rep_name)

    system = (
        "You are a sales call quality analyst for BT Local Business Oxford & Bucks, "
        "a UK telecom call centre selling BT broadband, phone lines, mobile and security "
        "products to small businesses in Oxfordshire, Buckinghamshire and Hertfordshire. "
        "You analyse call transcripts and return STRICT JSON only — no prose outside JSON. "
        "Be specific, cite real moments from the call, use UK English. "
        + (f"\nOrganisation context: {ai_context}" if ai_context else "")
    )

    playbook_desc = json.dumps([
        {"playbook_id": p["id"], "name": p["name"], "description": p["description"],
         "criteria": p["criteria"]}
        for p in playbooks
    ], indent=1)
    topics_desc = json.dumps([{"topic_id": t["id"], "name": t["name"],
                               "keywords": t["keywords"]} for t in topics])

    user = f"""Analyse this {activity_type} call. Rep: {rep_name}.

TRANSCRIPT (timestamps are mm:ss from call start):
{transcript}

SCORING PLAYBOOKS (score every criterion of every playbook listed, 1-5 integers,
where 1=missing entirely, 3=partially done, 5=excellent):
{playbook_desc}

TOPICS to detect (only include topics genuinely discussed):
{topics_desc}

Return JSON exactly in this shape:
{{
 "summary_intro": "one sentence describing the call",
 "summary_points": ["5-8 bullet points of what happened"],
 "action_items": [{{"owner": "Customer|{rep_name}", "text": "..."}}],
 "key_points": [{{"heading": "topic heading", "points": ["..."]}}],
 "themes": [{{"name": "...", "description": "..."}}],
 "sentiment": "positive|neutral|negative",
 "detected_topics": [{{"topic_id": 1, "mentions": 3, "first_mention_sec": 120}}],
 "scores": [
   {{"playbook_id": 1, "overall": 2.6,
     "criteria": [{{"key": "...", "name": "...", "score": 2,
       "feedback": "2-4 sentences: what the rep did, what was missing",
       "evidence": [{{"speaker": "{rep_name}|Customer", "at_sec": 0}}]}}],
     "coaching": "A short coaching paragraph for the rep: 2 strengths, 2 improvements, phrased constructively."
   }}
 ],
 "coaching": {{
   "one_thing": "ONE single specific, actionable instruction for the rep's NEXT call — the most important change. Not a list. Reference a concrete moment. E.g. 'The prospect mentioned budget twice and you moved past it both times — address budget directly on your next call before they raise it at the close.'",
   "strengths": ["1-3 specific things the rep did well, each with a concrete example"],
   "improvements": ["1-3 specific areas to improve, constructive, never harsh"],
   "question_breakdown": {{"discovery": 0, "closing": 0, "clarifying": 0}},
   "objections": [{{"type": "price|timing|incumbent|decision_maker|not_interested|other", "rep_response": "short transcript excerpt of how the rep responded", "assessment": "handled|partial|missed", "suggested": "a better response, only if partial/missed else empty"}}],
   "energy_note": "one sentence on energy & pacing — did the rep rush the value prop or pricing, did energy drop in the second half? Empty string if nothing notable.",
   "best_moment": {{"start_sec": 0, "end_sec": 0, "quote": "the single best 10-30s moment the rep delivered", "reason": "why it was strong"}}
 }},
 "followups": {{
   "callback": "if the rep promised to call back, a short phrase with when + what e.g. 'Tue 2pm — revised quote on 20 mobiles'; else empty string",
   "email_promised": "if the rep promised to send something by email, what e.g. 'FTTP pricing + install timeline'; else empty",
   "missing_info": "any key detail the rep should have captured but didn't, that they need for the deal e.g. 'current contract end date'; else empty",
   "proposal_needed": "if this call should result in a written proposal/quote, a short description e.g. '15-line cloud phone + FTTP'; else empty",
   "next_step": "the single most useful next action on this opportunity in a short phrase; else empty"
 }}
}}
"overall" is the weighted mean of criterion scores to 1 decimal. Only score playbooks
whose activity types match this call; if none match, score the most relevant single playbook.
For "coaching": classify every question the rep asked into discovery/closing/clarifying counts;
detect every objection the customer raised; pick exactly ONE primary coaching point. Use the
real transcript — never invent moments or numbers. Tone: supportive coach, UK English."""

    raw = _claude(system, user, settings.claude_call_model, max_tokens=12000)
    return _extract_json(raw)


def ask_about_call(turns: list[dict], rep_name: str, question: str,
                   call_context: str = "") -> str:
    """Ask CallIQ: free-form Q&A about a single call's transcript."""
    transcript = _format_transcript(turns, rep_name)
    system = (
        "You are CallIQ, a call-analysis assistant for BT Local Business Oxford & Bucks, "
        "a UK telecom sales call centre. You answer managers' and reps' questions about a "
        "specific call transcript. Be direct, concise and concrete. Quote or reference "
        "specific moments with their mm:ss timestamps as evidence. If the transcript does "
        "not contain the answer, say so plainly rather than guessing. UK English. "
        "Use short paragraphs or a brief list; no preamble."
    )
    user = f"""CALL CONTEXT: {call_context or 'n/a'}

TRANSCRIPT (timestamps mm:ss; Rep is {rep_name}):
{transcript}

QUESTION: {question}"""
    return _claude(system, user, settings.claude_call_model, max_tokens=1500)


def generate_weekly_report_md(team_summaries: str) -> str:
    """Sonnet-written weekly coaching profile report (markdown)."""
    system = ("You are a sales coaching analyst writing a weekly coaching profile report "
              "for managers at BT Local Business Oxford & Bucks. UK English. Markdown. "
              "Be concrete and actionable, reference the data given, no invented numbers.")
    user = f"""Write a weekly coaching profile report from this data.

{team_summaries}

Structure:
# Weekly Coaching Profiles
## Team overview (volumes, average scores, engagement trends)
## Per-rep profiles (for each rep: 2-3 sentence profile, strengths, focus areas, suggested coaching action)
## Recommended team coaching session topic for next week (pick the weakest common skill)
Keep it under 1200 words."""
    return _claude(system, user, settings.claude_report_model, max_tokens=8000)
