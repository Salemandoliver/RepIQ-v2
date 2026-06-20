# RepIQ — Promotions & Incentives ("Campaigns") Design Plan

**Goal:** let managers run time‑bound BT promotions and internal sales incentives, and make the
whole app *aware* of them — so calls are analysed against what's live, reps are nudged to act, and
managers can see adoption, behaviour and results in one place. Designed to be smart, seamless, and
to reuse what already exists rather than bolt on another disconnected tool.

---

## 1. The core idea — one backbone, two faces: **Campaigns**

Promotions and Incentives look different to the user but are the *same machine* underneath: a
time‑bound thing a manager creates, tied to products, that should change what reps **say** and
**sell**, and whose adoption we detect in calls and measure against sales.

So we build **one module, `campaigns`,** with a `type` of **Promotion** or **Incentive**. They share
all the plumbing (scheduling, product links, detection, analytics, Ask/coaching hooks); each gets its
own fields and views. This is simpler to build, simpler to use, and means every smart feature
(call analysis, Ask RepIQ, Today nudges) is written once and works for both.

### The crucial distinction (matters for the AI)
- **Promotion = customer‑facing.** The rep should *introduce and position* it to the customer
  (iPhone 19 launch, a discount, a bundle, "more SOV on product X"). We measure **mention rate +
  quality + customer reaction + conversion uplift**.
- **Incentive = rep‑facing.** It's an internal reward ("sell a BTnet → £25"). The rep must **pitch
  the qualifying product** — but must *not* tell the customer about the bonus. So for incentives we
  measure **whether the qualifying products are being pitched/sold**, progress vs target, and bonus
  earned — never "did they disclose the bonus".

The AI is told this difference explicitly, so it coaches correctly for each.

---

## 2. Data model (`backend/app/modules/campaigns/`)

**Campaign** (UUID, audited)
- `type`: promotion | incentive
- `name`, `description` (the manager's pitch/notes), `template` (launch | discount | bundle | sov_boost | attach_bonus | threshold_bonus | custom)
- `status`: draft | scheduled | live | expired | archived (derived from dates, overridable)
- `start_date`, `end_date`
- `teams`: all, or specific teams (reuses existing Teams)
- `products`: linked products / pillars (see §7 product reference)
- `talking_points`: the key messages reps should land (powers both coaching and detection)
- `created_by`

**Promotion fields**
- `offer` (discount %, price, bundle composition, free‑text terms)
- `sov_multiplier` (for "more SOV toward the rep on product X" — applied by SalesIQ during the window)
- `customer_segments` (optional targeting)

**Incentive fields**
- `reward` (£ per qualifying sale, or tiered/threshold)
- `qualifying_rule` (e.g. "BTnet sold", or "cloud security attached to a broadband") — structured against products
- `basis`: per_sale | threshold | tiered
- `target_per_rep`, `team_target`, `period` (aligns to the existing financial‑month calendar `fincal`)

**CampaignMention** (one row per call × live campaign, produced by the analyser)
- `campaign_id`, `call_id`, `host_id`, `call_date`
- `addressed`: yes | weak | missed  (for promos = introduced to customer; for incentives = qualifying product pitched)
- `evidence`: a short transcript snippet of how they did it
- `customer_reaction`: positive | neutral | objection | n/a
- `led_to_outcome`: linked to the call's outcome/sale

**CampaignResult** (rollups, refreshed by the worker)
- per campaign × rep × period: relevant calls, mention/pitch rate, quality mix, reaction mix, qualifying sales, bonus earned, conversion/attach, uplift vs baseline.

We **do not** re‑enter sales. Incentive progress and promo conversion **read the existing Sales
Tracker / SalesIQ data** — one source of truth for sales. Campaigns add the *layer of meaning* on
top of calls + sales we already ingest.

---

## 3. Where it gets smart — deep integration (not a bolt‑on)

### 3a. Campaign‑aware call analysis (the heart of it)
Every call already runs through the Claude analyser (summary, strengths, one‑thing, etc.). We extend
it: at analysis time we fetch the **campaigns live for that rep's team on the call date** and pass
their talking points + linked products into the prompt. The analyser then:
1. returns a structured **CampaignMention** per live campaign (addressed? how? reaction? outcome?), and
2. **weaves campaign adoption into the normal coaching** — exactly as requested: *"always include
   these promotions when they are live."* e.g. the post‑call *one‑thing* becomes
   *"This was an acquisition call during the iPhone 19 launch — you never mentioned the offer. Next
   time, lead with it after qualifying."*

Only live, team‑relevant campaigns are injected, so prompts stay tight and cheap. Detection is
**semantic (AI), not brittle keyword‑matching** — the right call for "make the app very smart" —
with the product names/keywords as hints.

### 3b. Ask RepIQ
Inject a `campaign_context` summary (what's live + adoption stats) into the Ask context for both
audiences, so it answers naturally:
- **Rep:** *"What's live today?"*, *"How am I doing on the iPhone 19 offer?"*, *"Which incentive am I closest to?"*
- **Manager:** *"Analyse how the team is introducing the iPhone 19 promotion."*, *"Who isn't pushing
  the cloud‑security incentive and why?"*, *"Is the BTnet bonus changing behaviour?"*

### 3c. Rep enablement (encourage the behaviour)
- **Today page — "Live now" card:** today's promotions to mention + incentives to chase, each with
  *the rep's own progress*: *"Sell 1 more BTnet for your £25 bonus — you're at 3/4 this month."*
- **Post‑call coaching card:** flags a missed live promo on a relevant call, with a one‑line fix.
- **Weekly AI briefing/video:** includes "how you did on this month's promos/incentives".
- **Call detail:** small badges showing which live campaigns applied and whether addressed — instant self‑review.

### 3d. Manager monitoring & analysis
- **Campaigns workspace** (managers/admin): create/schedule/expire, and a **per‑campaign dashboard**:
  adoption funnel (mention/pitch rate by rep), quality mix, customer‑reaction breakdown, conversion/
  attach + **uplift vs the pre‑campaign baseline**, a **leaderboard** (top promoters / laggards),
  and **listen‑to‑the‑best snippets** that deep‑link to the source calls.
- **Incentive tracker view:** progress vs target per rep and for the business, **projected vs actual
  bonus payout**, pace vs end of the financial month.
- **Command Centre section:** "Campaigns" at‑a‑glance with red flags ("3 reps haven't mentioned the
  launch in 20+ calls", "incentive ends in 3 days, team at 60%").
- **Auto close‑out report** when a campaign expires: an AI summary of adoption, results, payout and
  ROI — a ready record of what worked, to inform the next one.

---

## 4. Metrics that matter

**Promotions:** mention rate (per rep/team/all), introduction quality, customer‑reaction mix,
conversion when mentioned, **uplift vs baseline**, time‑to‑adopt after launch, leaderboard.

**Incentives:** qualifying sales vs target, **bonus forecast + actual**, attach‑rate change (e.g.
cloud‑on‑broadband before vs during), pace to period end, behaviour shift (is the qualifying product
pitched more?), and **ROI** (incremental margin vs bonus cost).

---

## 5. Encouragement / making it stick (the "anything important")
- **Leaderboards & streaks** — promo champions, incentive earners, "mentioned the launch 10 calls running".
- **Smart nudges** — a rep who keeps missing a live promo gets a targeted Today nudge; a rep 1 sale
  from a bonus gets a "you're nearly there" push.
- **Manager alerts** (reuses the existing alert engine): launches tomorrow, laggards, period ending,
  unusually strong/weak adoption.
- **Templates** for managers — "New product launch", "Attach bonus", "Discount push" — pre‑fill
  talking points + detection + sensible defaults, so creating a campaign takes a minute.
- **Preview as a rep** before publishing, so managers see exactly what the team will get.

---

## 6. Flows

**Manager:** Campaigns → *New* → pick a template → details, products, dates, teams, talking points →
preview → publish. Then live dashboard + alerts; auto close‑out at expiry.

**Rep:** sees "Live now" on Today → pitches on calls → post‑call card confirms/coaches → Ask RepIQ
and the weekly briefing keep them oriented → progress and bonus visible the whole time.

---

## 7. Simplification & data‑source decisions
- **Native, not an external tracker.** Promotions/incentives must drive the analyser and Ask in real
  time — a spreadsheet would lag and break that. So they live in the app. (One *fewer* moving part,
  not one more.)
- **Reuse SalesIQ for sales.** Incentive progress / promo conversion read the existing Sales Tracker
  — no duplicate sales entry, one source of truth.
- **A light product reference.** Introduce a small product/pillar catalogue (BTnet, Broadband, Cloud
  Security, Mobile/SIM, iPhone, etc.) so campaigns link to *real* products; this powers detection,
  attach‑rate and the `sov_multiplier`. It builds on the product pillars the dashboards already use.
- **`sov_multiplier`** plugs into the existing SOV/commission calc so "more SOV on product X during
  the window" is automatic, not manual.

---

## 8. Phased roadmap (each phase ships something useful)
1. **Foundation** — campaigns module + manager CRUD + nav, product reference, "live campaigns"
   service. Managers can create promotions & incentives.
2. **Detection** — campaign‑aware analyser; store CampaignMention; campaign badges on call detail;
   optional backfill of recent calls.
3. **Manager analytics** — per‑campaign dashboard, leaderboard, snippets; incentive progress vs
   target (reads SalesIQ); Command Centre section.
4. **Rep enablement + Ask + nudges** — Today "Live now" card, coaching‑card flags, Ask context,
   weekly‑briefing inclusion, manager alerts.
5. **ROI & gamification** — uplift/baseline, payout forecasting, leaderboards/streaks, auto close‑out report.

---

## 9. Decisions (LOCKED — 2026-06-20)
1. **Unified "Campaigns" backbone** — one system, `type` = promotion | incentive. ✅
2. **Incentive sales source** — read the existing **Sales Tracker / SalesIQ**; no double entry. ✅
3. **Home for campaigns** — **inside SalesIQ** (the sales hub). Managers create & monitor there; reps
   see live campaigns + progress there too, alongside their numbers. (Not a separate nav item.) ✅
4. **Detection** — **AI‑semantic via the per‑call analyser**. ✅
