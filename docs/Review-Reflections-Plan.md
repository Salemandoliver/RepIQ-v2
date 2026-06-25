# Review Reflections — turning the AI review into a two-way coaching conversation

**Feature:** After a rep gets their weekly (Oliver) or monthly/quarterly (Gary) AI performance review, they can **reflect with the same presenter in a guided dialogue** — the AI asks them what they think, probes deeper, surfaces blockers, and helps them commit to specific improvements. The conversation (and the structured signal mined from it) then feeds **every** intelligence surface: performance analysis, Smart Alerts, 1-to-1 briefs, Ask RepIQ, the Oracle, and the insight engine.

**Goal:** get reps to actually engage with their reviews, deepen their understanding of how to improve, and capture the rep's *own voice* (what they think, what's blocking them, what they'll do) as first-class data alongside the numbers.

**Status:** Plan for approval. No code written yet.

---

## 1. Confirmed decisions (your answers)

1. **Visibility:** managers see the **full transcript + the AI summary.** Reps are told up front the conversation is shared with their manager and used to help them improve — so it stays honest but professional.
2. **Expectation:** **encouraged, with nudges** — optional, but prompted (a reminder/alert if a fresh review hasn't been reflected on, and managers can see who has reflected). Supportive, not policing.
3. **Coach persona:** the **same presenter as the video** continues the conversation — **Oliver** for the weekly, **Gary** for the monthly/quarterly. Continuity from watching into talking.
4. **Engagement model:** the reflection is **always open**, and the AI's opening + follow-up questions **reference specifics from the review** ("Gary pointed out your Cloud discovery slipped — what's your take?"), so to answer well they're naturally pulled into watching/reading it. Low friction.

## 2. What a "reflection" is (the experience)

Under each review video sits a **"Reflect with Oliver / Gary"** button. Opening it starts a short, warm, adaptive chat:

1. **Opening** — grounded in *their* review: the AI opens with the review's headline insight and an open question ("…what's your read on the week?").
2. **Adaptive probing** — 4–7 exchanges (rep answers by text *or voice*, reusing the existing mic). The AI digs into vague answers, asks what drove the result, surfaces blockers, and checks understanding — one question at a time, never a lecture.
3. **Commit** — it guides the rep to **1–3 concrete commitments** for next period and reflects them back to confirm.
4. **Close** — a short, encouraging summary; the conversation is saved.

The **next** review's reflection re-opens the loop: *"Last month you committed to 5 discovery calls a week — how did that go?"* — creating accountability and a coaching thread over time. This longitudinal callback is the heart of "help them understand how to improve."

## 3. What we capture (the gold for the intelligence layer)

When a reflection completes, a second LLM pass extracts structured fields from the transcript:

- **selfAssessment** — the rep's own read of the period, in their words.
- **blockers** — named obstacles, each tagged (lead quality / time / product knowledge / confidence / process / external), with an `needsManager` flag where they've asked for help.
- **commitments** — 1–3 specific actions, each with a category and (where stated) a measurable target. These become trackable against next period.
- **understanding & self-awareness** — does the rep grasp the coaching, and crucially **does their self-assessment match the data?** (e.g. they feel Cloud went well but the numbers say otherwise → a self-awareness coaching signal). Stored as a 0–100 alignment read + a note.
- **engagement** — how thoughtfully/openly they engaged (depth, motivation, confidence), 0–100.
- **themes** — recurring topics, for cross-rep pattern-mining.

This turns soft, qualitative reflection into structured signal — without ever inventing numbers.

## 4. The reflection signal backbone (single source)

Mirroring the forecast's `rep_signal`, one function `reflection_signal(db, user)` is the single source every surface reads. It returns: latest reflection status (done / not / stale), date, the summary, open commitments, blockers needing help, engagement + self-awareness scores, **commitment follow-through rate** over recent periods, behaviour flags (`disengaged`, `growthMindset`, `lowSelfAwareness`, `commitmentSlipping`, `blockerFlagged`, `notReflected`), and a one-line human `summary`. Plus `team_reflection_summary(db)` for managers. This keeps the language and logic consistent everywhere.

## 5. Data model (new)

A small `reflections` module (`backend/app/modules/reflections/`), same pattern as forecast/orders/hr.

**`review_reflections`** — one per (rep, review video):
| Field | Notes |
|---|---|
| id | PK |
| user_id | FK users |
| video_id | FK performance_videos (the weekly/monthly/quarterly review) |
| period_type, period_key | weekly / monthly / quarterly + the period it covers |
| status | not_started \| in_progress \| complete |
| started_at, completed_at | |
| turns | JSON: ordered list of `{role: "ai"\|"rep", text, at}` (the full transcript) |
| summary | AI summary of the conversation |
| self_assessment, blockers, commitments, themes | extracted structured fields (JSON/text) |
| understanding_score, self_awareness_gap, engagement_score | 0–100 + note |
| asked_for_help | bool |
| shared | bool (true — see decision 1) |
| extracted_at | when the structured pass ran |

**`reflection_commitments`** (optional, Phase 4) — promotes commitments to first-class rows for clean cross-period tracking: `id, user_id, reflection_id, text, category, target, due_period, status (open/met/missed/partial), assessed_at`. (v1 can keep commitments in JSON and assess at the next reflection; a dedicated table makes the longitudinal loop and Smart Alerts cleaner.)

Additive `create_all` (brand-new tables) — no destructive migration.

## 6. The dialogue engine

`modules/reflections/dialogue.py`:
- **Persona prompt** built from the presenter (Oliver weekly / Gary monthly), the **review payload** (so questions reference real specifics), the rep's **metrics + forecast signal**, and the **prior reflection's commitments**. Rules: warm, curious, non-judgmental; one question at a time; probe vague answers; surface blockers; guide to 1–3 concrete commitments; never lecture; ~4–7 exchanges, then summarise. UK English, second person.
- **Turn loop:** rep message → append to `turns` → LLM returns the next question, or a closing summary + a `done` flag once there's enough depth (or the rep wraps up).
- **Extraction pass** on completion → the structured fields (§3), including the **self-awareness gap** computed by comparing the rep's self-assessment to the actual review numbers.
- Uses the existing `_claude` helper; gated on the Anthropic key (graceful fallback: a simple fixed 3-question script + store transcript, no AI probing, if the key is absent).

## 7. API endpoints (`/api/reflection`)

| Method & path | Who | Purpose |
|---|---|---|
| `GET /video/{videoId}` | rep/self | get-or-create the reflection for a review (status + transcript + summary) |
| `POST /{id}/message` | rep | send a message → returns the AI's next message + `done` |
| `POST /{id}/complete` | rep | finalise + run extraction (also auto-runs when `done`) |
| `GET /me/pending` | rep | is there a fresh review I haven't reflected on? (drives the nudge) |
| `GET /rep/{userId}` | manager | a rep's reflections — transcript + summary + commitments |
| `GET /team` | manager | who's reflected, open commitments/blockers, themes, engagement |

Permissions reuse `_is_manager` / `role_for_user`; reps see only their own; managers see the team (full transcript, per decision 1).

## 8. Frontend

**Rep:**
- **"Reflect with Oliver / Gary"** CTA directly under `ReviewVideo` and `WeeklyVideo` (with a one-line note that it's shared with their manager to help them improve).
- A **chat panel** in the existing dark "Ask" style with the mic for voice answers; shows the running conversation, then the summary + commitments on completion. If already done, shows the summary with an "add more" option.
- A **Today nudge**: a small card ("Reflect on last week's review with Oliver →") when a fresh review is unreflected (leave-aware).

**Manager:**
- In the Command Centre performance-videos area (and/or a "Reflections" panel): each rep's latest reflection — summary, commitments, blockers, engagement, "not yet reflected" list, with drill-in to the full transcript.
- The reflection is **embedded in the 1-to-1 brief** (§9).

## 9. Deep integration — making reflections matter everywhere (your core ask)

- **Insight engine / detectors** — new evidence-linked signals: *didn't reflect* (disengaged from development); *blocker flagged, wants help*; *self-assessment diverges from the data* (self-awareness coaching opp); *commitments repeatedly not met*; *thoughtful, growth-minded reflection* (recognition); *recurring team-wide blocker theme* (team insight). These flow into the Command Centre feed + weekly digest with the existing dedupe/feedback flywheel.
- **Smart Alerts** — "X hasn't reflected on last week's review", "X flagged a blocker (lead quality) and wants help", "X didn't meet last month's commitment".
- **1-to-1 briefs** — the rep's reflection summary **in their own words**, their commitments, understanding gaps, and blockers go straight into the manager's prep — so they walk in already knowing what the rep thinks and where to coach. (Biggest single uplift.)
- **Ask RepIQ (rep)** — becomes their personal coach that *remembers their commitments* and nudges toward them ("you said you'd focus on Cloud discovery — here are 3 prospects").
- **Ask the Oracle (manager)** — cross-rep qualitative intelligence: "what are reps saying blocks them?", "who's disengaged from their development?", "which commitments are slipping?", "what themes came up this month?".
- **The next AI review** — Oliver/Gary's next script references the prior reflection + commitments ("last month you told me you'd… and you did — here's the proof"), closing the loop in the video itself.
- **HR Performance & Reviews** — reflections + commitment follow-through become part of the performance record (the "what the rep thinks and does about it" dimension).

## 10. Engagement mechanics (driving watch/read — your stated goal)

- The CTA sits right under the video; the AI's first question references review specifics, so engaging is the easy path to a good answer.
- A Today nudge + a Smart Alert when a fresh review is unreflected.
- A light **reflection streak / completion** indicator.
- The **longitudinal callback** gives them a real reason to come back ("how did last week's commitment go?").

## 11. Edge cases & guardrails

- **Tone:** warm, curious, never punishing — same guardrails as the Oliver/Gary scripts (no "you underperformed").
- **On leave / no review yet:** no nudge; nothing to reflect on.
- **Incomplete dialogue:** saved as `in_progress`; the rep can resume; partial reflections still yield a partial summary.
- **No Anthropic key:** graceful fallback to a fixed short-question form (still captures the rep's words), no AI probing.
- **Privacy/transparency:** reps see a clear, persistent note that the reflection is shared with their manager and used to support them. Never framed as surveillance.
- **Wellbeing:** if a rep expresses real distress, the AI stays supportive and does not push performance talk; it suggests speaking to their manager/HR.

## 12. Phased delivery (each phase verified before the next)

- **Phase 1 — Engine & data:** module + tables, the dialogue engine (persona prompts, turn loop, extraction), and `reflection_signal` backbone. Verify prompts + extraction logic in isolation.
- **Phase 2 — Rep experience:** endpoints + the "Reflect with Oliver/Gary" chat (voice-enabled) under the videos + summary view + Today nudge.
- **Phase 3 — Manager experience:** reflections in the 1-to-1 brief, the manager reflections panel + "not yet reflected" list, and Smart Alerts.
- **Phase 4 — Deep intelligence:** detectors/insights, Ask RepIQ + Oracle context, the longitudinal commitment loop + next-review callback, HR Reviews.
- **Phase 5 — Engagement polish & verify:** streak/completion indicators, nudges, end-to-end check, deploy.

## 13. Open defaults to confirm (else I'll proceed with these)

1. **Dialogue length:** ~4–7 exchanges then an auto-summary; the rep can keep going.
2. **Commitments:** 1–3 per reflection, tracked to the next period.
3. **Self-awareness read:** computed by comparing the rep's self-assessment to the review's actual numbers.
4. **Nudge window:** prompt if a weekly review from the last 7 days, or the current month's review, is unreflected (leave-aware).
5. **Persona = video presenter** (Oliver/Gary); BCs (no SOV forecast, but they do get weekly videos) — include BCs in reflections too unless you'd rather reps-only. *(Tell me if BCs should be excluded.)*

If those defaults are right, I'll start Phase 1 on your word. If you'd tweak any (especially #5 on BCs), tell me and I'll adjust before building.
