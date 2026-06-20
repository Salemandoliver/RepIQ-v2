# RepIQ — Organisational Intelligence & Continuous Learning

**The intent.** RepIQ should be the brain of the business: it sees every call, every sale, every
number, and turns that into *wisdom* — developing each rep's skill over time, helping managers find
trends and run better 1‑to‑1s, and answering questions nobody even knew to ask. The decisive
requirement is that **RepIQ keeps getting smarter as time passes — through data, knowledge and
feedback — not by us constantly writing new features.** This document is how we make that real.

---

## 1. The principle: intelligence from data + knowledge, not code

A normal app's "intelligence" is hardcoded rules that someone has to keep editing. That ceilings out.
RepIQ's intelligence instead **emerges** from four things that all grow on their own:

1. **More data** — every call, sale, coaching note and outcome accumulates.
2. **Learned baselines** — the system continuously recomputes what "good" looks like for *this* team.
3. **Curated knowledge** — discovered truths and winning patterns are saved to a store the AI always consults.
4. **Feedback loops** — what advice actually worked feeds back in and tunes the next answer.

Because all four are **data and configuration, not code**, RepIQ becomes more capable every week with
no engineering. The job of the code is to build the *machine that learns*, once. After that, time and
usage do the rest. This is the flywheel: **more usage → more data + feedback → sharper intelligence →
more trust → more usage.**

---

## 2. The RepIQ Brain — architecture

### 2.1 A unified knowledge layer (the foundation everything reasons over)
Three stores, one mind:

- **Facts warehouse** — a clean, denormalised, time‑series view of everything: calls, scores, skill
  metrics, outcomes, sales (from the Sales Tracker), activity, leave, campaigns, HR reviews/goals.
  Any question can be sliced by rep / team / product / customer / period. (We already ingest most of
  this; this formalises it into one queryable layer.)
- **Semantic memory (vector store)** — every transcript, coaching note, review and key call moment is
  **embedded** (pgvector on the existing Postgres). This is what lets RepIQ *retrieve evidence* to
  answer anything ("show me how Kunle handled the price objection") and is the single biggest reason
  the system improves with time: the more it has seen, the better it retrieves and reasons.
- **Entity graph** — links rep ↔ call ↔ customer ↔ product ↔ outcome ↔ campaign, so RepIQ can reason
  about *relationships*: which customer profiles a rep converts best, which products drag, where a
  technique works.

### 2.2 Learned baselines & benchmarks (auto‑calibrating)
A rollup engine (runs on the existing worker) continuously recomputes, per skill / product / segment:
team averages, percentiles, personal bests, trends, conversion norms, ramp curves. Nothing is
hardcoded — **the bar rises automatically as the team improves**, so "above average" always means
above *today's* team. This directly powers the comparative charts (§5) and every "vs average" claim.

### 2.3 The insight engine (proactive — finds things nobody asked about)
A scheduled "analyst" reasons over the facts + retrieved evidence and **surfaces insights unprompted**:
emerging weaknesses, rising stars, decaying skills, recurring objections it can't beat, product gaps,
coaching opportunities, anomalies ("Team's discovery scores dropped 12% since the new starters
joined"). Each insight is stored with **severity, evidence (linked calls), and a suggested action**,
and shown on Today / SalesIQ / Command Centre and in a weekly digest. As data accumulates, the
insights sharpen — no code change. This is the answer to *"sometimes a rep doesn't know where to look —
RepIQ tells them."*

### 2.4 The learning flywheel (how it gets wiser without new code)
This is the crux. Four mechanisms, all data‑driven:

- **What‑works mining (outcome attribution).** Correlate *behaviours* (from call analysis) with
  *outcomes* (sales). RepIQ discovers which techniques actually convert — for **your** team, products
  and customers — and then coaches with patterns it learned from your own wins, not generic advice.
  Refines every time an outcome lands.
- **Knowledge store ("company wisdom").** When something true is discovered — by RepIQ or a manager
  ("objection X is best met with Y", "use Kunle's discovery as the exemplar") — it's saved to a
  durable store the AI always consults. **Adding knowledge = getting smarter, with zero code.** This
  is RepIQ's growing institutional memory.
- **Exemplar library.** RepIQ auto‑curates gold‑standard moments (best discovery, best objection
  handling, best promo intro) into a living training library reps learn from. It grows as great calls
  happen.
- **Feedback signals.** A thumbs‑up/down + "this worked / didn't" on every insight and coaching tip
  feeds a preference store; RepIQ learns which advice lands and adjusts. Usage itself becomes training.

### 2.5 Config, not code
The things that shape RepIQ's judgement — the **skill taxonomy**, **scoring rubrics**, **coaching
prompts**, **playbooks**, **insight thresholds** — are stored as **editable configuration/knowledge**,
not buried in code. Managers can evolve what RepIQ measures and how it advises as the business changes.
The LLM does the reasoning; the data + config steer it.

---

## 3. Ask RepIQ — the organisational oracle

Ask RepIQ graduates from "questions about one call/rep" to **retrieval‑augmented Q&A over the whole
company**: it pulls the right structured aggregates + semantic evidence + learned patterns + knowledge
into the model and answers, **always citing the calls/data behind the answer** (trust, not
hallucination). It's permission‑aware — reps ask about themselves, managers about their team, leaders
strategically — and confidence‑aware (won't over‑claim on thin data).

**Worked example — hiring (the one you raised):**
> *"Should we hire experienced reps or train juniors, and what should we look for?"*
RepIQ retrieves the **skill profiles that separate your top from bottom performers**, the
**tenure‑to‑competency curve** (how fast juniors ramp here), **win/loss by customer profile and which
rep traits win which segments**, and home‑grown vs lateral‑hire performance where data exists. It
answers with evidence and caveats — e.g. *"Your best closers index high on discovery and objection
handling but only average on talk‑ratio; coachable juniors reach competency in ~N weeks via your
in‑house program and then outperform lateral hires on product knowledge — so a junior‑plus‑training
strategy looks stronger, except for [segment X] where experience pays."* — and can generate an
**interview scorecard** of the exact competencies to probe, derived from what predicts success **in
your own data**. The same engine answers "what's dragging Q3?", "who's ready for promotion?",
"which product needs a refresh?".

---

## 4. Intelligence woven into every surface

Not a separate "AI page" — the intelligence shows up where people already work:
- **Today (rep):** your trend vs team, one proactive insight, your next skill to focus on with your
  own best/worst example, and a nudge to *ask* ("ask me how to lift your discovery").
- **SalesIQ:** trends, anomalies, campaign intelligence, and "ask about these numbers" inline.
- **Command Centre (manager):** an insights feed, rising/declining reps, and **auto‑generated 1‑to‑1
  briefs** — per rep: strengths, the one focus area, the evidence calls, suggested questions to ask,
  and progress since last time (feeds straight into the HR Performance/Reviews tab).
- **Universal Ask:** a consistent, context‑aware "Ask RepIQ" on every page.

---

## 5. Skill development & healthy competition

- **Longitudinal skill graph** per rep — discovery, qualifying, objection handling, SPIN, closing,
  talk‑ratio, filler, etc. tracked over time vs team and vs personal best.
- **Personalised development path** — RepIQ picks the next skill to work on, pairs it with the rep's
  own example calls + a teammate exemplar, and tracks the improvement curve (a real learning loop).
- **Comparative time‑charts (your technique):** each rep's sales and call‑quality over time **with
  their line against the team average** and a **percentile rank / league position**. On Today it's
  motivational (me vs the team); on Command Centre it's the whole squad, plus **"most improved"** so
  effort — not just raw talent — is celebrated. Evidence‑based competition that pulls everyone up.

---

## 6. Trust & governance (so people rely on its wisdom)
- **Evidence‑linked** — every insight and answer cites the source calls/numbers.
- **Permission‑scoped** — retrieval respects the existing RBAC/field projection.
- **Confidence‑aware** — sample size gates how strongly RepIQ claims; it says when it doesn't know.
- **Auditable** — insights, advice and the knowledge store are versioned, so you can see how RepIQ's
  thinking evolved.

---

## 7. Technical enablers (build the machine once)
- **pgvector** on the existing Postgres for embeddings → semantic search / RAG.
- **Embedding pipeline** — on each call analysis, embed the transcript + key moments + notes.
- **Rollup/benchmark jobs** on the existing worker — baselines, skill series, ramp/cohort curves.
- **New stores:** Insights, Knowledge, Exemplars, Feedback, Skill‑timeseries (all additive tables).
- **Retrieval‑augmented Ask service** — assembles structured aggregates + semantic evidence +
  knowledge + learned patterns into the model prompt, scoped by permission.
- **Scheduled analyst** — periodic insight generation + weekly intelligence digest.
- Reasoning by Claude; vectors by an embeddings model. All within the current architecture.

---

## 8. How RepIQ matures (ordered, not time‑boxed)
- **Foundations:** facts warehouse + embeddings + benchmark rollups + comparative charts (immediate,
  visible value, and the motivational lever you asked for).
- **Proactive:** the insight engine + weekly digest + 1‑to‑1 briefs.
- **Oracle:** org‑wide retrieval‑augmented Ask (strategic questions, hiring, product).
- **Flywheel:** what‑works mining + knowledge store + exemplar library + feedback — the parts that make
  it *learn*.
- **Compounding:** with the machine built, every passing week of calls and feedback makes it sharper —
  no new features required. That is the end goal.

---

## 9. Quick wins to start (high value, low risk)
1. **Comparative trend charts** (rep vs team average + rank) on Today & Command Centre — the
   motivational technique, and it needs only the benchmark rollups.
2. **Weekly intelligence digest** — one proactive insight per rep + one per team, evidence‑linked.
3. **Auto 1‑to‑1 brief** per rep in Command Centre (feeds the Reviews tab).
4. **pgvector + embeddings** quietly switched on, so the semantic memory starts accumulating from day
   one — the longer it runs, the smarter Ask becomes.
