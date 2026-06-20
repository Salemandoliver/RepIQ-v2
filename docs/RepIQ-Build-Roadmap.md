# RepIQ Build Roadmap — Campaigns + Organisational Intelligence

The execution plan that folds two designs into one ordered build:
- **Campaigns** (BT Promotions + Sales Incentives) — see `docs/Promotions-Incentives-Plan.md`
- **Organisational Intelligence** (continuous learning) — see `docs/RepIQ-Intelligence-Design.md`

**Why one roadmap.** They share the same seams, so building them separately would touch the same code
twice and produce two half‑smart systems instead of one. Specifically they share:
- the **per‑call analyser** (campaign detection *and* behaviour/skill mining come out of the same pass),
- the **facts + benchmark layer** (powers campaign analytics *and* the comparative charts/insights),
- **Ask RepIQ context** (campaigns, benchmarks and knowledge all plug into one context framework),
- the **dashboards** (Today, SalesIQ, Command Centre) where both surface.

Building the shared machine first means each later phase is small and reinforces the other. Ordered by
dependency and value, not by time (per the brief: the end goal matters, not the clock). Governance —
evidence‑linked, permission‑scoped, confidence‑aware — runs through every phase.

---

## Dependency view (build the machine once, then layer)

```
Phase 0  Shared foundations ───────────────┐
  facts warehouse · benchmarks · pgvector   │ everything depends on these
  product reference · Ask context framework │
                                            ▼
Phase 1  Campaigns CRUD (in SalesIQ)   +   Comparative trend charts
Phase 2  ★ Analyser seam: campaign detection + behaviour/skill mining (one pass)
Phase 3  Proactive: insight engine + campaign dashboards + 1‑to‑1 briefs + digest
Phase 4  In‑flow: Today "Live now" + skill focus · Ask everywhere · alerts
Phase 5  Compounding: org oracle · what‑works · knowledge store · exemplars · feedback · ROI
```

---

## Phase 0 — Shared foundations (the learning machine)
*Mostly invisible, unlocks everything; start the data compounding immediately.*
- **Facts/metrics warehouse** — one denormalised, time‑series view of calls, scores, skill metrics,
  outcomes, sales (from the Sales Tracker), activity, leave, campaigns.
- **Benchmark/rollup engine** on the existing worker — team averages, percentiles, personal bests,
  trends, ramp/cohort curves; recomputed continuously.
- **pgvector + embedding pipeline** — embed each transcript + key moments + notes at analysis time, so
  the semantic memory starts accumulating from day one (the longer it runs, the smarter Ask gets).
- **Product reference** — BTnet, Broadband, Cloud Security, Mobile/SIM, iPhone… (Campaigns links to
  these; the entity graph uses them).
- **Ask context framework** — a pluggable way to inject context providers (benchmarks, campaigns,
  knowledge, evidence retrieval) so every later feature plugs in without rewrites.

## Phase 1 — Campaigns foundation + first intelligence win
*Immediate, visible value for managers and reps.*
- **Campaigns module + manager CRUD inside SalesIQ** — promotions & incentives with dates, teams,
  products, talking points, rewards/targets. Reads the Sales Tracker for qualifying sales (no double
  entry). (Campaigns plan Phase 1.)
- **Comparative trend charts** — each rep's sales + call‑quality over time vs **team average + league
  rank + "most improved"**, on Today (me vs team) and Command Centre (the squad). Uses the Phase‑0
  benchmarks. (Intelligence quick‑win #1 — the motivational lever.)

## Phase 2 — The analyser becomes intelligent (the key shared seam) ★
*Extend the per‑call Claude analysis once to do double duty.*
- **Campaign detection** — for live, team‑relevant campaigns on the call date: addressed (yes/weak/
  missed), evidence snippet, customer reaction, outcome link → `CampaignMention`. Campaign badges on
  call detail. (Campaigns plan Phase 2.)
- **Behaviour + skill mining** — richer behaviour tags and per‑skill signals stored to the skill
  time‑series, seeding the what‑works miner. (Intelligence flywheel seed.)
- Promo adoption is **woven into the normal coaching** ("always include live promotions").
This single pass is why everything downstream is cheap.

## Phase 3 — Proactive intelligence + manager analytics
*Surfaces trends, weaknesses and campaign performance in one place; preps 1‑to‑1s.*
- **Insight engine** (scheduled analyst) — evidence‑linked insights nobody asked for; campaign
  red‑flags (laggards, low adoption) are one insight category.
- **Per‑campaign dashboard** — adoption funnel, quality, reactions, conversion **uplift vs baseline**,
  leaderboard, listen‑to‑the‑best snippets; **incentive progress vs target + payout forecast**.
- **Command Centre** — insights feed + **auto 1‑to‑1 briefs** per rep (feeds the HR Reviews tab) +
  campaign at‑a‑glance.
- **Weekly intelligence digest** — one insight per rep + per team, including campaign adoption and
  incentive progress.

## Phase 4 — In‑flow enablement + Ask everywhere
*Guide reps in the moment; make the whole app askable.*
- **Today** — unified: "Live now" campaign card with the rep's own progress + nudges, **plus** their
  trend vs team, next skill to focus on, and a prompt to ask.
- **Post‑call coaching card** — campaign‑miss flags + the one skill to work on.
- **Ask RepIQ upgraded** — campaign + benchmark + evidence retrieval context, permission‑scoped
  (rep ⇄ self, manager ⇄ team).
- **Manager alerts** (existing alert engine) — campaign laggards, incentive period ending, anomalies.
- **Weekly AI briefing/video** — includes campaign adoption + skill progress.

## Phase 5 — The oracle + the learning flywheel (compounding, no new code after this)
*Now that embeddings + outcomes have accumulated, switch on the parts that make it learn.*
- **Org‑wide retrieval‑augmented Ask** — strategic questions: hiring scorecard from your top‑performer
  patterns, "experienced vs train‑juniors", product gaps, promotion readiness — all evidence‑cited.
- **What‑works mining matured** — behaviour→outcome patterns coach with **your own wins**; campaigns
  learn "which introduction style converts best".
- **Knowledge store ("company wisdom")** + **exemplar library** + **feedback loops** (thumbs / "this
  worked") across insights, coaching and campaigns — adding knowledge = getting smarter, no code.
- **Campaign close‑out reports + ROI**, uplift/baseline.
From here, every passing week of calls and feedback makes RepIQ sharper **without new features** —
the end goal.

---

## Notes
- **Other tracks:** HR (live) and the future Order Entry module are separate builds; when Order Entry
  lands it simply becomes another source feeding the Phase‑0 facts warehouse — more for the brain.
- **Hard constraint still holds:** existing trackers/feeds stay authoritative until anything that
  replaces them is complete and reconciled.
- **First step when building begins:** Phase 0 (facts warehouse + benchmarks + pgvector + product ref
  + Ask context). It's the smallest amount of code that unlocks the largest amount of intelligence.
