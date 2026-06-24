# Weekly Forecast — Detailed Design & Execution Plan

**Feature:** Each Sales Rep commits a weekly forecast (Data SOV, Cloud SOV, Mobile SOV) on Monday morning. The app tracks daily progress against it from placed orders, scores how *consistently* each rep hits their forecast, and weaves that signal through every performance surface in the app — dashboards, alerts, call/coaching analysis, 1-to-1 briefs, reviews and the AI videos.

**Status:** Plan for approval. No code written yet.

---

## 1. Confirmed decisions (from your answers)

1. **"Data SOV" = the Connectivity column** in the Sales Tracker. The *Other* column is excluded from all three forecast categories. So a rep forecasts three figures: **Data (Connectivity), Cloud, Mobile**, and the headline forecast = Data + Cloud + Mobile.
2. **Achievement counts placed orders only** — orders flagged `Placed = Yes` on the tracker.
3. **Reps submit once; then it locks to them.** After submission a rep cannot change their own forecast — **only a manager can edit or unlock it.** A rep who hasn't submitted yet can still submit (including late, after 11am).
4. **Reminder = in-app popup for the rep + a manager-facing "missing forecast" list.** Reps on annual leave (or other booked leave) are always skipped.

## 2. Scope

- **In scope:** Sales Reps only. **BCs have no forecast** (and are excluded from every forecast surface). Managers/Admins/Operations don't forecast but managers *view and manage* everything.
- Forecast unit is **£ SOV** (share-of-value, i.e. the revenue value the tracker already sums per category).
- Forecast period is the **BT financial week** (Mon–Sun), keyed by `week_year` + `week_number` (existing `fincal.financial_week`). This is the same week Operations reconcile against Schedule 5, so everything lines up.

---

## 3. Key concepts & definitions

### 3.1 The week
We key forecasts on the BT financial week from `fincal.financial_week(today)` → `{number, week_year, start(Mon), end(Sun)}`. "This week" = the week containing today. The forecast covers Monday→Sunday.

### 3.2 Categories & the tracker mapping
The Sales Tracker reader (`services/salesiq/sales.py`) already returns, per order: `mobile`, `cloud`, `connectivity`, `other`, `sov (= sum)`, `gm`, `placed`, `agent`, `week`. The forecast maps:

| Forecast line | Tracker column |
|---|---|
| Data SOV | `connectivity` |
| Cloud SOV | `cloud` |
| Mobile SOV | `mobile` |
| (excluded) | `other` |

### 3.3 Achievement (computed daily, live)
For a rep in the current week:
- Pull the current sales month's tracker orders (`sales.orders_for(year, month)`), keep those **matched to the rep** (`roles.user_agent_match`), **`placed == True`**, and **in this week**.
- Sum `connectivity` → actual Data; `cloud` → actual Cloud; `mobile` → actual Mobile.
- `achievementPct(category) = actual / forecast × 100` (guard divide-by-zero: if forecast = 0 and actual > 0 → show "no forecast set" / 100%+ as appropriate; if both 0 → 0%).
- Overall achievement = `(actualData+actualCloud+actualMobile) / (fData+fCloud+fMobile) × 100`.

**Week-matching note (build-time verification):** the tracker labels orders `Week 1..N` *within a sales-month tab*. We'll map "this week" to the tracker's week label by computing the current Monday's index within the sales month, and **verify the alignment against the real sheet** before relying on it. Fallback if labels prove unreliable: cross-check against the Orders-module DB (which stamps the BT `week_number`/`week_year` by `order_date`) for the set of orders in the week, using the tracker only for the category split. This is the one area I'll validate empirically during Phase 1.

### 3.4 Consistency / Forecast Reliability Score (the headline new signal)
At each **week close** (Monday, for the week just ended) we snapshot the rep's forecast vs actuals into history. From the rolling history we compute a **Forecast Reliability Score (0–100)** per rep, blended from four components:

| Component | What it measures | Default weight |
|---|---|---|
| **Hit rate** | % of recent weeks where overall achievement **≥ 100%** (your decision: strict — only fully meeting/beating the committed number counts) | 40% |
| **Accuracy** | How close actual lands to forecast — **penalises both directions**: wild over-forecasting *and* sandbagging (low-balling then easily beating it). Uses mean absolute % error vs forecast, capped. | 30% |
| **Trend** | Is achievement improving or declining over the window | 15% |
| **Discipline** | Submitted on time (before 11am Monday), not left blank | 15% |

- Window: rolling **8 weeks** (configurable), with a "not enough history yet" state for new reps.
- Output per rep: `reliabilityScore` (0–100), a RAG band, plus the component breakdown so coaching can be specific ("you hit your number 3 of the last 8 weeks, but you consistently under-forecast Cloud by ~40%").
- This score is what feeds the wider intelligence (section 9).

*(Weights/threshold/window are constants I'll expose so you can tune them later. If you'd prefer different emphasis — e.g. pure hit-rate — say so and I'll change the defaults.)*

---

## 4. Data model (new tables)

A new `forecast` module: `backend/app/modules/forecast/` (models, services, router), consistent with the `orders`/`hr` modular-monolith pattern.

**`weekly_forecasts`** — one row per (rep, week):
| Column | Notes |
|---|---|
| id | PK |
| user_id | FK users |
| week_year, week_number | BT financial week key (indexed, unique with user_id) |
| data_sov, cloud_sov, mobile_sov | the rep's committed £ figures |
| submitted_at, submitted_by_id | when/who first submitted (rep) |
| locked | true once submitted (rep can't edit; manager can) |
| edited_by_id, edited_at, edit_note | manager corrections (audit) |
| created_at, updated_at | |

**`weekly_forecast_results`** — immutable weekly snapshot written at week close (drives consistency history, stable even as the live sheet changes):
| Column | Notes |
|---|---|
| id | PK |
| user_id, week_year, week_number | |
| forecast_data/cloud/mobile | what was forecast |
| actual_data/cloud/mobile | placed-order SOV that week |
| achievement_pct | overall |
| hit | bool (≥ threshold) |
| on_time | submitted before Monday 11am |
| captured_at | |

**`weekly_forecast_reliability`** (or computed-and-cached) — per rep current score + components, recomputed at week close. Could be derived on the fly from results, but storing it makes every read cheap and keeps the heavy compute out of the hot path.

Additive migration via the existing `main._ensure_columns` pattern + `Base.metadata.create_all`.

---

## 5. Backend services

`modules/forecast/services.py`:
- `current_week()` / `week_key(d)` — wrap fincal.
- `get_forecast(db, user, week)` / `upsert_forecast(...)` with the **lock rules**: rep may create when none exists; rep may **not** update a locked row; manager may update/unlock any row (stamps `edited_by`).
- `eligible_reps(db)` — active users with `role_for_user == "rep"` (excludes BC/manager/ops/admin).
- `compute_achievement(db, user, week)` — live, from the cached tracker (section 3.3). Returns per-category forecast/actual/pct + overall + pacing (expected % by day-of-week for an "on track?" read).
- `team_forecast(db, week, team=None)` — aggregate totals (Data/Cloud/Mobile forecast + actual + pct) and per-rep rows. Excludes BCs.
- `missing_forecasts(db, week, asof)` — reps with no submitted forecast, **minus** anyone on leave that day (`hr.leave.leave_rows` + the SharePoint Holiday Tracker fallback, exactly like the leave-aware Smart Alerts already do).
- `close_week(db, week)` — snapshot results + recompute reliability (idempotent; run by the Monday worker).
- `reliability(db, user)` / `team_reliability(db)` — the consistency score + components.

All heavy reads go through the existing `useCachedGet` on the frontend and the tracker's TTL cache on the backend; `team_forecast`/reliability are cheap (DB + cached tracker).

## 6. API endpoints

`routers/forecast_router.py` (prefix `/api/forecast`):

| Method & path | Who | Purpose |
|---|---|---|
| `GET /me?week=` | rep | my forecast + live achievement + pacing for the week (defaults to current) |
| `POST /me` | rep | submit my forecast (blocked if already locked) |
| `GET /status` | rep | "do I still need to submit this week?" (drives the reminder modal) |
| `GET /team?week=&team=` | manager | team totals + per-rep forecast vs actual + reliability |
| `GET /rep/{userId}?week=` | manager | one rep's forecast, achievement, history, reliability |
| `PUT /rep/{userId}?week=` | manager | edit/unlock a rep's forecast (audited) |
| `GET /missing?week=` | manager | reps who haven't forecast (leave-excluded) |
| `GET /reliability/{userId}` | manager/self | reliability score + component breakdown + weekly history |

Permission: reuse `_is_manager` / `role_for_user`. Reps only see their own; managers see the team.

## 7. Reminder & scheduling (worker jobs)

Extend the existing pipeline worker (`pipeline/worker.py`, where `maybe_weekly_videos` already lives):
- **Monday week-roll (early AM):** `close_week(previous week)` → snapshot results + recompute reliability. Guarded by a `Setting` key so it runs once per week.
- **Reminder gating (weekday ≥ 11:00 local):** nothing to "send" server-side for the in-app modal; the modal is driven by `GET /forecast/status`. The worker's job here is to compute and cache the **manager missing-forecast list** and raise a Smart Alert. (If you later enable email, this is where the nudge email would fire.)

**Rep reminder modal (frontend):** a small app-level check — on load, if today is a weekday, it's ≥ 11:00, the user is a rep, not on leave, and `status` says "not submitted", show a **blocking-but-dismissible modal** prompting them to enter the forecast (with the three inputs inline so they can do it right there). Dismiss = "remind me later" (re-prompts next load); submitting clears it for the week. Before 11:00 we show a gentler inline card (section 8) rather than the modal.

## 8. Frontend — Rep experience

1. **Weekly Forecast card on Today / Morning Dashboard** (top of the page Monday→all week):
   - If not submitted: the entry form — three labelled £ inputs (Data, Cloud, Mobile) with a running total, a "Submit forecast" button, and a note that it locks after submitting.
   - If submitted: a **progress dashboard** in the screenshot style — three gauges (Data / Cloud / Mobile achievement %) + a big "overall %" number + a "pacing" indicator (on track / behind for the day of week) + actual-vs-forecast £ per category. Read-only ("locked — ask your manager to change").
2. **Reminder modal** after 11:00 if still missing (section 7).
3. **SalesIQ Rep view** gains a "Weekly Forecast" section: this week's progress + a **consistency strip** (last 8 weeks achievement as small bars, hit/miss, the reliability score and its breakdown).

## 9. Frontend — Manager experience

1. **Command Centre — "Weekly Forecast" dashboard card** (screenshot style, collapsible like the others):
   - **Team totals:** big-number tiles for Data / Cloud / Mobile **forecast £**, **actual placed £**, and **achievement %** gauges; an overall team gauge.
   - **Per-rep table/bars:** each rep's forecast, actual, % (RAG-coloured), pacing, and reliability score — ranked, with drill-through to the rep.
   - **Missing forecasts:** a clear list of reps who haven't submitted (leave-excluded), with a one-click "remind"/"enter on their behalf" (manager edit).
2. **Smart Alerts** gains: "N reps haven't set this week's forecast" and per-rep "X is behind forecast (45% with 1 day left)" / "X has missed forecast 3 weeks running".
3. **SalesIQ Manager view** gains a Weekly Forecast section mirroring the Command Centre card with the team filter.
4. **Manager edit/unlock** modal from the per-rep view.

## 10. Dashboard visual kit (consistent with our colours)

I'll add a small reusable component set so we can use the screenshot's dashboard language **everywhere**, but in **our existing light-card theme and accent palette** (magenta/purple accent, green/amber/red RAG, teal) — not the screenshot's dark navy:
- `Gauge` — an SVG arc gauge (value, RAG band, label) for achievement %, CSAT-style.
- `KpiTile` — big-number tile (already partly exists as `Stat`/`siq-tile`; I'll consolidate).
- `RankedBars` / `MiniBars` — ranked list with inline bars (for per-rep and the 8-week consistency strip).
These get reused by Weekly Forecast first, then are available to refresh other dashboards over time.

## 11. Deep integration — making the forecast matter everywhere

This is the core of your ask: forecast consistency becomes a first-class performance signal.

- **Insight engine / detectors** (`services/intelligence/detectors.py`): new evidence-linked signals — *chronic forecast misser*, *strong/consistent forecaster (recognition)*, *sandbagger* (habitually under-forecasts then beats easily), *behind-pace mid-week (needs help today)*, *didn't submit*. These flow into the Command Centre insights feed and the weekly digest with the same dedupe/feedback flywheel.
- **Rep Morning Dashboard / Today:** forecast progress is a headline focus; the daily plan and "Ask RepIQ" become forecast-aware ("you're at 40% of your Data forecast with 2 days left — these 3 warm Connectivity deals would close the gap").
- **Call & coaching analysis:** the post-call coaching card and call-quality reads gain forecast context — e.g. tie a strong Cloud-pitch call to the rep's Cloud forecast pacing; flag when activity isn't aligned to where they're behind.
- **1-to-1 briefs** (auto brief → HR Reviews): include forecast reliability, this week's pacing, the 8-week record, and concrete talking points ("Cloud forecast missed 4/8 weeks — coach on Cloud discovery").
- **Performance & Reviews (HR):** reliability score tracked over time as a reviewable metric on the Performance tab.
- **Weekly (Oliver) & monthly/quarterly (Gary) AI videos:** scripts incorporate forecast achievement and consistency ("you committed to £X Data, delivered £Y — and you've now hit your number 5 weeks running").
- **Team League / benchmarks:** optional "forecast reliability" as an additional league lens alongside call quality.
- **Org Oracle:** forecast data added to its context so managers can ask "who's most reliable against forecast?", "who consistently sandbags Cloud?".
- **Campaigns:** where a campaign targets a category (e.g. a Cloud push), forecast-vs-actual for that category enriches the campaign ROI read.

## 12. Edge cases & rules

- **On leave:** never reminded, never flagged "missing"; excluded from the team "missing" count. If a rep is on leave the whole week, their forecast is optional and not counted against reliability (mark the week "excused").
- **Part-week leave / mid-week join:** forecast stands; pacing accounts for working days remaining.
- **Late submission:** allowed; `on_time=false` (hurts the Discipline component only).
- **Manager edits:** always allowed, audited (`edited_by`, note); can unlock to let a rep re-enter.
- **No tracker data yet / tracker down:** show forecast with "actuals pending" rather than 0%/errors.
- **New rep with no history:** reliability shows "building history (n/8 weeks)" instead of a misleadingly low score.
- **Forecast = 0 in a category:** allowed (rep expects nothing there); achievement for that category shows "—" not a divide-by-zero.
- **Bank holiday Monday:** week-roll/reminder respects the working-day logic already used by Smart Alerts.

## 13. Permissions

- Enter/submit own forecast: **reps** only.
- View own: reps. Edit own after lock: **no** (managers only).
- View team, edit/unlock any, see missing list: **managers/admin**.
- BCs/Operations: no forecast surfaces at all.

## 14. Phased delivery (each phase verified before the next)

- **Phase 1 — Foundations & truth:** forecast module (models + migration), services (forecast CRUD with lock rules, eligible reps), and the **achievement calculator with the tracker week-matching verified against the real sheet** (SO-level spot checks like we did for the GM splits). Unit-test the maths in isolation. *No UI yet.*
- **Phase 2 — Rep entry + progress:** API + Today/Morning "Weekly Forecast" card (entry → locked progress dashboard with gauges) + the dashboard visual kit (Gauge/KpiTile).
- **Phase 3 — Reminder + manager view:** the 11am reminder modal, the missing-forecast list, the Command Centre Weekly Forecast dashboard card, Smart Alert, and manager edit/unlock.
- **Phase 4 — Week-roll + consistency:** the Monday close-week snapshot, reliability scoring, the rep/SalesIQ consistency strip, and the manager reliability column.
- **Phase 5 — Deep intelligence integration:** detectors/insights, 1-to-1 briefs, reviews, Oliver/Gary video scripts, Ask RepIQ/Oracle context, coaching-card context, league lens.
- **Phase 6 — Polish & verification:** end-to-end check against real reps (one who's on leave, one new, one strong, one weak), tune weights, final build/deploy.

Each phase ends with a build/compile verification and, where it touches real numbers, a spot-check against the live Sales Tracker.

## 15. Open assumptions to confirm (or I'll proceed with these defaults)

1. **Reliability weights/window** — confirmed: a hit = **achievement ≥ 100%** (strict); accuracy penalises **both** over- and under-forecasting (anti-sandbagging). Remaining defaults: 8-week rolling window, weights 40/30/15/15 (hit/accuracy/trend/discipline). Tunable later.
2. **"On time" cutoff** = Monday 11:00 (same as the reminder). 
3. **Reminder cadence** — re-prompt on each app load while still missing on a working day after 11am; no nagging before 11am (gentle inline card instead).
4. **Forecast vs monthly target** — I'll *also* show the week's forecast next to the pro-rata monthly SOV target as context, but the forecast is the rep's own commitment (not auto-derived from target).
5. **Leave = whole week** → that week is "excused" and doesn't count toward reliability.

If any of these defaults are wrong, tell me and I'll adjust before Phase 1. Otherwise I'll start building Phase 1.
