# RepIQ v2 — Project Plan & Technical Design
### HR Module (SafeHR replacement) + Order Entry Module (NetSuite + Excel replacement)

**Prepared for:** Salem Zerti · **Source brief:** *RepIQ — HR & Order Entry Brief v2.0 (Oliver, 17 June 2026)*
**Status:** Plan for review · **Author:** RepIQ build (Claude)

> **Hard constraint (Salem, 19 June 2026): keep everything running until v2 is complete.**
> The existing Excel/SharePoint trackers (sales, lead, activity, pending), the current SalesIQ
> spreadsheet/Graph data feeds, SafeHR, and NetSuite **remain live and authoritative throughout
> the build**. RepIQ v2 is built and populated *alongside* them. Nothing is switched off, replaced,
> or made the source of truth until the **entire** v2 (HR + Order Entry) is built, the data is
> fully migrated, and the commission/Schedule-5 figures reconcile penny-perfect. The new modules
> run in **read-and-write parallel** (the spreadsheets stay the live feed; RepIQ mirrors them) right
> up to a single, deliberate, all-at-once cutover at the very end. This constraint overrides any
> "replace / decommission / switch source" wording elsewhere in this plan — all of those are
> **end-of-project** steps, gated on your sign-off.

---

## 0. How to read this document

This is the engineering plan that sits *under* Oliver's product brief. The brief says **what** to build; this says **how to build it inside the existing RepIQ codebase so it lasts** — i.e. so that HR, Order Entry, and every future module slot in without rewrites.

It is organised as:

1. **Principles & the one big idea** (the architecture that delivers "expand without rewriting")
2. **Foundational decisions** — the platform-level choices that both modules depend on, each with a recommendation and rationale
3. **HR module design**
4. **Order Entry module design**
5. **Cross-module integration** (how HR/Orders connect to the existing CallIQ/SalesIQ/CompanyIQ)
6. **Data migration & cutover**
7. **Security, compliance & non-functional requirements**
8. **Phased delivery roadmap** with sequencing and dependencies
9. **Risks** and **decisions to confirm**
10. **Appendices** — folder structure, full table inventory, Phase 0 concrete tickets

Where the brief and the current code disagree (e.g. UUID vs integer keys, Alembic vs the current ad-hoc migrations), this plan calls it out and recommends a path rather than silently picking one.

---

## 1. Principles & the one big idea

### 1.1 Where we are today

RepIQ today is a **single FastAPI app + React/Vite SPA**, one Dockerfile, one Postgres database on Railway, with an in-process background worker. The backend is already loosely modular:

```
backend/app/
  main.py            # registers routers, runs startup migrations + worker
  db.py              # SQLAlchemy 2.0 DeclarativeBase, engine, SessionLocal
  models.py          # ALL models in one file (User, Call, Team, Setting, PerformanceVideo, …)
  auth.py            # PBKDF2 hashing + JWT (require_admin, require_manager, scopes: none yet)
  config.py          # pydantic-settings
  routers/           # one router file per area (calls, salesiq, companyiq, intelligence, company, teams…)
  services/          # salesiq/*, companyiq/*, intelligence/*  (domain logic)
  pipeline/          # worker, transcriber, analyzer, ringcentral, msteams
  seed/              # bootstrap + demo
```

Migrations are done by a hand-written `_ensure_columns()` in `main.py` that runs idempotent `ALTER TABLE … ADD COLUMN IF NOT EXISTS` on startup. That has been fine for incremental columns but **will not scale** to ~40 new tables across HR + Orders with foreign keys, enums, separate schemas, and evolving shape.

### 1.2 The one big idea: a **modular monolith** with a thin **platform core**

We keep **one deployable app** (no microservices — that would be over-engineering for ~50 users and would slow you down). But we draw **hard module boundaries** and put everything cross-cutting into a **platform core** that every module consumes the same way.

```
backend/app/
  core/                     # the platform — shared, owned by no single feature
    db.py  config.py
    rbac.py                 # roles, scopes, dependencies (require_role/require_scope/team-scope)
    audit.py                # immutable audit log service + model
    projection.py           # field-group permission projection (the "one record, many views" engine)
    crypto.py               # AES-256 field encryption (bank details etc.)
    audit_mixins.py         # UUID PK, timestamps, soft-delete base mixins
    calendar.py             # financial-month calendar (promoted from salesiq/fincal.py)
    notifications.py        # notification_queue + alert-rule engine
    storage.py              # document/file storage abstraction (object storage)
    registry.py             # module registry: each module self-registers routers + startup hooks
  modules/
    hr/        models.py schemas.py permissions.py services/ router.py
    orders/    models.py schemas.py permissions.py services/ router.py
    calliq/    …            # existing call intelligence (migrated here opportunistically)
    salesiq/   …
    companyiq/ …
  main.py                   # builds the app from the registry; nothing feature-specific
```

**The contract for a module** (this is what makes growth cheap): a module is a Python package that exposes

```python
# modules/<name>/__init__.py
module = ModuleSpec(
    name="hr",
    routers=[employees_router, leave_router, admin_router],   # FastAPI routers
    startup=[seed_hr_reference_data],                          # optional hooks
    alert_rules=[probation_due_rule, rtw_expiring_rule],       # optional notification rules
    nav=[NavItem("People", "/hr", roles=["manager","admin"])], # optional UI nav (served to frontend)
)
```

`core/registry.py` collects every `ModuleSpec`, and `main.py` just iterates: include routers, run startup hooks, register alert rules, expose nav. **Adding a future module (e.g. "FinanceIQ", "Recruitment") is then a new folder — no edits to `main.py`, no edits to other modules.** This is the concrete mechanism behind "expand and grow without rewriting too much code."

> We do **not** big-bang refactor the existing CallIQ/SalesIQ code into `modules/` on day one. New code (HR, Orders, core) is built the new way; existing routers are moved folder-by-folder opportunistically when they're already being touched. The registry supports both during the transition.

### 1.3 Design rules every module follows

These are lifted from the brief's "Guiding Principles" and made concrete:

| Principle | Concrete rule in RepIQ |
|---|---|
| Privacy by design | Default deny. A field group is invisible unless the caller's role/scope grants it. Financial data is a *separate access tier*, not a flag. |
| Extensibility over cleverness | Normalised relational tables + a `metadata JSONB` extension column on every major entity. New attributes go in JSONB first, graduate to real columns via a migration when they stabilise. |
| Audit everything | Every write to a sensitive entity, and every *read* of financial data, produces an immutable `audit_log` row. No update/delete on the audit table — ever. |
| One record, many views | Build the entity once; the API projects it per the caller's scopes (`core/projection.py`). An employee, their manager, and an admin all hit the same endpoint and get different shapes. |
| GDPR is not optional | Retention windows, data export, erasure (anonymisation), rectification, and consent tracking are foundations in Phase 0 — not Phase 4 features. |

---

## 2. Foundational decisions (Phase 0)

These are the platform-core choices both modules sit on. **Build these first** — the brief is explicit ("Do not defer the audit log or financial isolation — those are foundations"). Each has a recommendation; the few that need your sign-off are collected in §9.2.

### 2.1 Migrations → adopt **Alembic** now

**Decision:** Introduce Alembic and make it the single source of truth for schema going forward. Keep the existing `_ensure_columns()` running for the legacy tables during transition, then retire it.

- **Why:** ~40 new tables, enums, FKs, multiple Postgres schemas, and ongoing evolution. Hand-written `ALTER`s can't express table creation order, downgrades, data backfills, or schema separation safely.
- **How:** `alembic init`, set the target metadata to `core.db.Base.metadata`, **baseline** the current production schema as revision 0001 (autogenerate against a fresh DB, then `stamp` prod), then every change is a reviewed migration. Run `alembic upgrade head` on container start (replacing the `_ensure_columns` call) — same trigger point, robust mechanism.
- **Dev/prod parity:** Alembic runs identically on SQLite (local) and Postgres (Railway). Postgres-only features (schemas, JSONB) are guarded with `if dialect == 'postgresql'`.

### 2.2 Primary keys → **UUID** for all new domain tables

**Decision:** New HR and Orders tables use `UUID` primary keys (brief-specified). Existing tables keep their integer keys; cross-links to `users.id` remain integer FKs.

- **Why:** UUIDs don't leak counts or allow enumeration of employee/order records, they're safe in URLs and exports (GDPR data export, Schedule-5 files), and they make future data import/merge painless. The brief asks for this explicitly.
- **Mixed keys are fine:** `employees.user_id -> users.id` is an integer FK; `employee_personal.employee_id -> employees.id` is a UUID FK. SQLAlchemy handles both. We provide a `UUIDPkMixin` so it's one line per model.

### 2.3 Postgres **schemas** for separation

**Decision:** Four schemas — `public` (existing), `hr`, `hr_financial`, `orders`.

- `hr_financial` physically separates pay/bank/benefit-cost tables (brief §4.3). Models set `__table_args__ = {"schema": "hr_financial"}`.
- **Railway caveat (important):** Railway gives you a single database role, so the brief's "restrict access by DB user/role" can't be fully realised with a second locked-down DB user out of the box. We therefore enforce financial isolation in **depth** (see §2.8): schema separation **+** mandatory `financial` API scope **+** field-level encryption **+** audited reads **+** UI omission. If/when you want true DB-role isolation, we provision a second restricted Postgres role or a separate database and point only the financial-data connection at it — the schema split makes that a config change, not a rewrite.
- **Dev nuance:** SQLite has no schemas; locally we use SQLAlchemy's `schema_translate_map` to collapse them to one DB. Prod uses real schemas.

### 2.4 Base mixins (every major entity)

```python
class UUIDPkMixin:      id: Mapped[uuid] = mapped_column(primary_key=True, default=uuid4)
class TimestampMixin:   created_at, updated_at (server defaults, onupdate)
class SoftDeleteMixin:  deleted_at (nullable);  default queries filter deleted_at IS NULL
class MetadataMixin:    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)  # extension column
```

Soft-delete everywhere (records are immutable per the brief — "delete" means archive/anonymise, never a hard `DELETE` on HR/Orders rows, except GDPR erasure which anonymises).

### 2.5 Identity model — **User (auth) vs Employee (HR)**

This is the most important integration decision, because RepIQ already has a `User` table and a sales-role concept.

**Decision:**

- **`User` stays the authentication/identity account** — login email, password, JWT, MFA. One per person.
- **New `Employee` (HR) record, 1:1 with User** via `employee.user_id`. The Employee is the HR "core identity record" (brief §3.3). All the HR domain tables (`employee_personal`, `employee_contact`, `employee_role`, …) hang off `employees.id`.
- Existing `User` fields we already have (`name`, `email`, `team_id`, `short_name`, `avatar_color`, `left_on`, `left_by_id`, `must_set_password`, …) are the *account* facts; HR-rich facts live on the Employee + its domain tables. The HR profile **Summary** view composes both.
- The **People page** we already built becomes the admin/manager entry point into HR (it already lists users, invites, leavers); it grows into the HR team directory.
- Offboarding (brief §9) reuses and extends the leaver flow we already built (`User.left_on`, `left_by_id`, session invalidation).

**Roles — unify into one platform role + scopes.** Today `User.role` is `admin|analyst|recorder` (mostly legacy) and a *derived* `sales_role` (`rep|bc|manager`) comes from job title via `salesiq_role()`. The brief defines a flat HR/platform role set: `employee | manager | operations | admin`.

We introduce, on `User`:

- `platform_role`: `employee | manager | operations | admin` — **the authoritative role** for HR, Orders, and admin. (Migration maps existing users: current admins → `admin`; users whose `sales_role == manager` → `manager`; Operations team → `operations`; everyone else → `employee`.)
- `scopes`: a JSON array of capability grants layered on top, e.g. `financial`, `ops.orders`, `ops.schedule5`, `calliq.dispute`. **Scopes are how we avoid role explosion** — Operations is a role, but "can read employee financials" is a scope held only by `admin@btlocalbusiness.co.uk`.
- `sales_role` (rep/bc/manager) **remains** as a *sales-domain attribute* derived from job title — it governs SalesIQ dashboards only, orthogonal to `platform_role`. (A `manager` platform-role person and a `rep` sales-role can be the same human; the two answer different questions.)

New auth dependencies in `core/rbac.py`: `require_role("admin")`, `require_any_role("manager","admin")`, `require_scope("financial")`, and `team_scoped(query, user)` (limits a manager to their own team(s)). These replace the ad-hoc `require_admin`/`require_manager` we have, which become thin wrappers during transition.

> **Brief alignment:** "all managers are equal" → there is exactly one `manager` platform role with one permission set, always team-scoped. "Operations is distinct" → `operations` role + `ops.*` scopes, **no** manager-level HR access. "Admin is the only elevated role" → `admin` + the `financial` scope, restricted to `admin@btlocalbusiness.co.uk` (and Salem).

### 2.6 Field-level permission **projection** framework (`core/projection.py`)

This is the engine behind the brief's field-group permission table (§4.2) and "one record, many views."

- Define **field groups** declaratively per entity, each tagged with a **read scope** and a **write scope**:

  ```python
  FIELD_GROUPS = {
    "self.personal":  Scope(read={"self","admin"},               write={"self","admin"}),
    "self.medical":   Scope(read={"self","admin"},               write={"self","admin"}),  # never manager
    "self.documents": Scope(read={"self","manager.team","admin"},write={"admin","manager.docs"}),
    "financial":      Scope(read={"admin.financial"},            write={"admin.financial"}),
    …
  }
  ```
- **Sub-resource endpoints** (e.g. `GET /hr/employees/:id/medical`) return **403** if the caller lacks the group's read scope — exactly as the brief mandates ("the field must not exist in the response payload").
- The **composite** endpoint (`GET /hr/employees/:id`) returns only the field groups the caller can read — a manager's payload simply has no `financial` or `medical` keys.
- Writes go through the same gate; a write to a field outside the caller's write scope is a 403, and every sensitive write is audited.

This framework is written **once** and reused by Orders (e.g. commission-rate fields are admin-only; cost fields hidden from reps) and any future module.

### 2.7 Audit framework (`core/audit.py`)

- One `audit_log` table (in `public`, immutable): `id, ts, actor_user_id, actor_role, action (CREATE/UPDATE/DELETE/READ), entity_type, entity_id, field, old_value, new_value, ip, session_id`.
- `record_audit(...)` service called from the service layer on sensitive writes; **financial reads** also call it (brief §4.3). For convenience, models flagged `__audited__ = True` get automatic field-diff via SQLAlchemy `before_flush` event listeners, so developers can't forget.
- Read endpoints: employee sees own history; admin sees all; the financial audit is a separate admin-only view.
- The table is **append-only** — no API or ORM path updates or deletes it; GDPR erasure anonymises *referenced* PII but preserves the audit chain.

### 2.8 Financial isolation (defence in depth)

| Layer | Mechanism |
|---|---|
| Schema | `hr_financial` schema for `employee_pay`, `employee_benefits_cost`, `commissions`, `commission_statements`. |
| API | Every financial endpoint depends on `require_scope("financial")`; missing scope → hard 403. The scope is held only by the admin account. |
| Field encryption | Bank details, NI number encrypted at rest with **AES-256-GCM** (`core/crypto.py`), key in `FINANCIAL_ENC_KEY` env — **separate** from `JWT_SECRET`. |
| UI | The Pay/Financial tab is not rendered for non-admins — it does not exist in their app, no "denied" message. |
| Audit | Every read and write of financial data writes an `audit_log` row with user, role, IP, timestamp. |

### 2.9 Auth hardening — refresh tokens + MFA for admin

Builds directly on what we already shipped (PBKDF2, JWT with a `pv` password-version claim, change-password, invite/reset links, leaver session-invalidation).

- **Access + refresh tokens:** short-lived access JWT (e.g. 30–60 min) + a rotating refresh token stored server-side (`auth_sessions` table) so we can revoke sessions (leaver, password reset, "log out everywhere"). The frontend already centralises token handling in `api.js`, so this is contained.
- **MFA (TOTP) enforced for `admin`:** standard authenticator-app TOTP; secret stored encrypted; required at login for admin, optional for others. (SMS/email OTP explicitly *not* needed.)
- These are Phase 0 because financial/HR data raises the bar; they're additive and don't disturb existing sessions beyond a re-login.

### 2.10 Notifications & alert-rule engine (`core/notifications.py`)

- `notification_queue` table + a small rule engine. Each module registers **alert rules** (brief §7 for HR; CRQ/Schedule-5/commission alerts for Orders).
- Rules run on the **existing in-process worker's hourly housekeeping** (we already run `maybe_weekly_videos`/`maybe_weekly_reports` there) — no new infrastructure.
- Surfaced in-app via a `GET /api/notifications` endpoint + a bell in the sidebar, and folded into the existing rep/manager "Today"/Command-Centre dashboards.

### 2.11 Document & file storage (`core/storage.py`) — **needs a decision**

HR documents and order attachments (contracts, fit notes, signed forms) can be up to 25 MB and must be **durable** and access-controlled. The current app stores call audio on the container's **ephemeral** disk (fine — it re-downloads). **HR/Order documents cannot be ephemeral.**

**Recommendation:** introduce an object-storage abstraction with an **S3-compatible** backend (Cloudflare R2 or AWS S3; both cheap, UK/EU regions available for data residency). Files are stored by key, served via short-lived signed URLs, never public. `core/storage.py` hides the backend so we can start on a Railway volume for the pilot and switch to R2/S3 without touching module code. (Confirm choice in §9.2 — this also has a GDPR data-residency angle.)

### 2.12 Reuse of what already exists (don't rebuild)

| Existing asset | Reused for |
|---|---|
| `salesiq/fincal.py` (financial-month calendar) | Promote to `core/calendar.py`; commission month-close, MTD/QTD/YTD everywhere. The brief calls this out explicitly. |
| `salesiq/roles.py` `agent_matches()` (tolerant name matching) | Schedule-5 reconciliation and order-agent matching. |
| `salesiq/roles.py` `JOB_TITLE_TARGETS` + Settings targets | Seed the Orders `pay_plans` and `targets` tables. |
| Holiday Tracker (current SalesIQ) | Folds into HR `leave_requests` / `employee_leave_entitlements`; the spreadsheet becomes a data source for the initial import, then HR is the source of truth. |
| People page + leaver flow (just built) | HR team directory + offboarding. |
| `companyiq/salestracker.py`, `salesiq/trackers.py` (openpyxl/Graph readers) | Schedule-5 XLSX import + NetSuite/Excel order import. |
| `pipeline/analyzer.py` `_claude` | Order "Generate Insight" AI summaries. |
| Worker housekeeping loop | Alert-rule engine + commission-run scheduling. |

---

## 3. HR Module design

### 3.1 Entity model (grouped)

All tables live in schema `hr` except the financial ones (`hr_financial`). Every table has UUID PK + timestamps + soft-delete + `metadata JSONB`.

**Core & identity**
- `employees` (1:1 `user_id` → `users.id`; employee_id human code; start date; status; department_id; team_id; reports_to → employees.id)
- `departments`, (teams already exist; HR references them)
- `employee_personal` · `employee_contact` (+ address history) · `employee_emergency_contacts` (multiple, priority-ordered)
- `employee_medical` *(GDPR Art. 9 — self+admin only, never manager)*

**Employment**
- `employee_roles` (current title/department/team/reports-to/type) · `employee_role_history` (immutable) · `role_changes` (first-class promotion/transfer workflow, brief §5.19)
- `employee_contract` (type, hours, notice, probation end = start + 6 months fixed)
- `employee_hours` (working pattern, flex/hybrid, TOIL)
- `employee_location`

**Financial (schema `hr_financial`)**
- `employee_pay` (salary, frequency, bank — encrypted, tax/NI, pay history) · `employee_benefits` (+ admin-only `benefits_cost`)

**Leave & absence**
- `employee_leave_entitlements` · `leave_requests` (workflow: submit → manager approve/reject with reason → calendar update → >5-day overdue alert) · `employee_absences` (sick/unauthorised/compassionate; Bradford Factor auto-calc; fit notes; return-to-work)

**Records, performance, growth**
- `employee_records` (1-to-1s, reviews, disciplinaries, commendations — typed, immutable, acknowledgement) · `probation_reviews` (auto-scheduled months 2/4/6) · `employee_goals` · `employee_feedback` · `employee_training` · `employee_qualifications`

**Assets & documents**
- `employee_assets` · `employee_documents` (file ref + metadata: type, version, visibility scope, expiry, acknowledgement)

**Platform**
- `audit_log` (shared core) · `notification_queue` (shared core)

### 3.2 API surface

Versioned REST under `/api/v1/hr/…`, exactly per brief §11 (employees + per-domain sub-resources, leave-requests, admin audit/export). Every endpoint: validate JWT → resolve role+scopes → project field groups → audit if sensitive. Sub-resources return 403 when the scope is absent.

### 3.3 Key workflows

- **Leave approval** — folds in the Holiday Tracker; entitlement balances auto-maintained; manager approval; calendar fed to the existing dashboards.
- **Probation** — `probation_end = start + 6 months` (fixed); reviews auto-scheduled at months 2/4/6 on hire; reminder alerts 7 days prior; month-6 = pass→permanent / fail→extend/terminate; employee acknowledgement required.
- **Role change / promotion** (brief §5.19) — a *first-class workflow*: creates an immutable `role_changes` + `employee_role_history` entry, auto-generates an amendment letter document, employee acknowledges, admin notified if pay is adjusted (pay change goes through `employee_pay` under the `financial` scope). Never an in-place field edit.
- **Offboarding** — end date triggers asset-recovery checklist, access revocation (reuse leaver flow), P45 slot, retention-clock start.

### 3.4 UI

- **Employee profile** — the 18 tabs from brief §12 (Summary, Personal, Role, Location, Contract, Pay [admin-only, omitted entirely otherwise], Benefits, Hours, Holiday, Performance & Reviews, Assets, Documents, Records, Sick & Absence, Training, Qualifications, Goals, Feedback). Tabs render only if the caller has the field-group scope.
- **Manager view** — team directory, employee cards with status alerts, quick actions (add record, approve leave, initiate role change, add probation review).
- **Admin view** — company-wide list, org dashboard, bulk actions, audit, GDPR export/erasure.
- Built as a new top-level **People/HR** area in the SPA, reusing the sidebar/nav, the existing People page as the directory, and our component library.

### 3.5 GDPR

Retention windows (brief §10) implemented as a retention service the worker enforces; **right of access** (full export as PDF/JSON via `/hr/admin/export/:id`), **erasure** (anonymise PII in place, preserve audit chain + financial-record legal retention), **rectification** (employee edits own personal/contact under `self.*` write scopes), **consent tracking** for optional fields.

---

## 4. Order Entry Module design

Replaces the **NetSuite Sales Order module** *and* the **SharePoint Excel trackers** (sales/lead/activity/pending) and **manual commission Excel** — one owned system. Schema `orders` (+ commission tables in `hr_financial` for isolation).

### 4.1 Entities (per brief §14.10)

`customers` (LE code + name; `external_ids JSONB` for Apollo/Lemlist/Jiminny from day one) · `products` (4-level hierarchy: Class › Product Group 1 › Product Group 2 › Schedule 5 Area) · `orders` (full field set, brief §14.2) · `order_lines` (commission unit; GM, splits, Schedule-5 check) · `order_agents` (multi-agent splits, contribution %) · `order_status_log` (immutable transitions) · `order_disputes` (type/status/resolution/**call reference** → CallIQ) · `crq_references` (commission + reporting CRQ) · `targets` (per-rep monthly revenue/volume) · `pay_plans` (versioned, effective-dated commission configs) · `commissions` (per agent per line) · `commission_runs` (monthly, lockable, signed-off) · `commission_statements` (per-rep) · `schedule5_imports` / `schedule5_rows` / `schedule5_reconciliation` / `schedule5_resolutions`.

### 4.2 Order form, state machine, badges

- The order form replicates every NetSuite field (brief §14.2) with equivalent logic; line-item grid with the documented actions (Add/Remove/Copy Previous/Insert/Alternative/Clear/Close Remaining).
- **State machine:** statuses I/J/K/L/M/N/O + "Issues with Payment", with **every transition logged** (timestamp + user) to `order_status_log`; the prominent **badge** maps status → label (PENDING BILLING, FULLY BILLED, PAID, …).
- Cancellation workflow (reason + date required) and rejection flag.

### 4.3 Product catalogue

Seeded from live BT data (the product examples + Schedule-5 categories in brief §14.5). Catalogue is admin-managed; line items reference catalogue products; GM and classification (PG1/PG2/Schedule-5 area) flow from the product + contract value.

### 4.4 Commission engine (the money — built with care)

- **Pay plans are versioned and effective-dated** (brief §14.9c): a historical commission run always uses the plan that was active then. Seeded from the existing `JOB_TITLE_TARGETS` + the uploaded pay-plan docs.
- Per-line calculation: pay-plan rate for the product type → accelerator/threshold bonuses → split % from `order_agents` → exclude cancelled / non-commissionable / `BT Commission Paid = false`.
- **Commission run:** month-close (uses `core/calendar.py`) → lock orders for the month → calculate → generate per-rep statements → manager review/flag → admin approve+lock → export Excel/PDF for payroll.
- **Correctness discipline:** the commission engine ships with a dedicated unit-test suite and a *reconciliation report* against a known month from the current Excel, run in parallel before cutover (see §6). Money code gets tests first.

### 4.5 Schedule 5 reconciliation (first-class, brief §14.9b)

Upload BT's Schedule-5 XLSX/CSV (reuse our openpyxl readers) → auto-match each row to RepIQ orders on Main Order Number / OPP ID / Company Name / Contract Value (reuse `agent_matches` + fuzzy company match) → discrepancy report (matched / value-mismatch / BT-only / RepIQ-only) → per-discrepancy resolution action → sign-off with timestamp+user. Operations: full; Management: read-only; Admin: full + history.

### 4.6 CRQ tracking, disputes, Generate Insight

- **CRQ** workflow (commission + reporting CRQ references, dates, closed flags) on the order.
- **Disputes** link to **CallIQ** call recordings: Operations get a scoped `calliq.dispute` capability (search/listen/transcript/download/add dispute note) **without** coaching cards or performance scores — implemented as scope checks on the existing calls endpoints, a *distinct* access path from the manager coaching view.
- **Generate Insight** button → passes order data to `pipeline/analyzer._claude` → AI summary (customer profile, product fit, commission projection, next best action). This is the bridge that makes Order Entry *intelligent*, reusing the existing Claude wiring.

### 4.7 Reporting

- **Sales Order Status search** (filters + columns + CSV/Excel/PDF export per brief §14.8).
- **ERP Dump** (full order-line tabular export, all documented columns).
- Both reuse our xlsx/export patterns.

---

## 5. Cross-module integration

| Connection | How |
|---|---|
| **Orders → SalesIQ** (source-of-truth switch) | SalesIQ today reads orders from the **Sales Tracker spreadsheet**, and **keeps doing so for the whole build** (per the hard constraint). We add a **source adapter** so SalesIQ can read from spreadsheet **or** DB, but the spreadsheet stays the **default/live** source; the DB path is exercised in parallel for verification only. The actual switch is the **final cutover step**, gated on penny-perfect reconciliation and your sign-off — never mid-build. |
| **Orders ↔ HR/People** | `order_agents` and `commissions` reference the person via `user_id`/`employee_id`. HR owns the person; Orders own their sales output; commissions feed payroll under the `financial` scope. |
| **Orders → CallIQ** (disputes & insight) | Dispute → call recording access (scoped); Generate Insight → analyzer. |
| **HR ↔ existing leaver / People** | Offboarding extends the leaver flow; People page becomes the HR directory. |
| **Everything → core/calendar** | One financial-month definition across SalesIQ, commissions, and HR reporting. |

---

## 6. Data migration & cutover

1. **HR import** — from SafeHR export (and the Holiday Tracker for balances). Map → `employees` + domain tables. Validate, dry-run, reconcile counts.
2. **Orders import** — from the **NetSuite ERP Dump** + Excel trackers → `customers`, `products`, `orders`, `order_lines`, `order_agents`. Preserve historical statuses and splits. Reuse our spreadsheet readers.
3. **Parallel run (the whole build, per the hard constraint)** — the Excel trackers, current SalesIQ feeds, SafeHR and NetSuite stay **live and authoritative** the entire time. RepIQ v2 is built and kept in sync alongside them; the commission and Schedule-5 reconciliation reports are run repeatedly and must reach **penny-perfect** agreement with the live spreadsheets across multiple sales months. No source is switched mid-build.
4. **Cutover (end of project only, on your sign-off)** — once *all* of v2 is complete, data fully migrated, and reconciliation is clean and stable, we flip SalesIQ's source adapter to the DB and make RepIQ the source of truth — a single deliberate switch, not a drift.
5. **Decommission (after cutover)** — keep NetSuite/SafeHR/the spreadsheets read-only for the legal retention window, then retire.

> Data-availability is a dependency: we need a SafeHR export and a NetSuite ERP-Dump + the Excel trackers to build the importers. Listed in §9.2.

---

## 7. Security, compliance & NFRs

- **Financial isolation** — the five-layer approach in §2.8.
- **Encryption** — AES-256-GCM at rest for bank details/NI; separate key; HTTPS only (already); short-lived JWT + refresh rotation; MFA for admin.
- **Audit** — immutable, append-only, covering sensitive writes and financial reads.
- **GDPR** — retention windows, export, erasure, rectification, consent; **UK/EU data residency** for employee PII and documents is a hosting consideration (Railway region + object-storage region) — flagged for confirmation.
- **NFRs (brief §15):** P99 < 500 ms (achieved via indexing, pagination, and the projection layer doing minimal work), 25 MB uploads, ≤50 concurrent users, daily backups + 30-day retention (Railway Postgres backups; verify schedule), 99.5% uptime, modern-browser responsive web, native app later.
- **Tests** — money paths (commission engine) and permission projection get first-class test suites; a verification subagent reviews each phase before merge.

---

## 8. Phased delivery roadmap

Sequencing reflects the brief's phases, the dependency that **both modules sit on the platform core**, and your steer to land HR first.

### Phase 0 — Platform foundations *(do first; unblocks everything)*
Module registry + `modules/` skeleton · Alembic (baseline current schema) · `core/rbac.py` (platform_role + scopes + role migration) · `core/projection.py` · `core/audit.py` · `core/crypto.py` + base mixins · `core/calendar.py` (promote fincal) · `core/notifications.py` (+ worker hook) · `core/storage.py` (+ object-storage backend) · auth hardening (refresh tokens + admin MFA) · Postgres schemas.

### HR — Phase 1 (Foundation/MVP, brief §13)
Employee CRUD (personal/contact/role/contract) · emergency contacts · documents library · flat RBAC enforced via core · **financial isolation** · leave requests + approval (folds in Holiday Tracker) · basic audit live · probation auto-set to 6 months.

### HR — Phase 2 (Manager tools)
1-to-1 records + action points · probation review scheduling (2/4/6) + alerts · performance reviews · **role-change/promotion workflow + immutable history** · assets · absence recording (Bradford Factor) · status-alert engine · team directory + manager view.

### HR — Phase 3 (Self-service)
Medical (self-managed) · training + qualifications · goals · GDPR data export · document acknowledgement.

### HR — Phase 4 (Intelligence & automation)
Bradford-Factor/absence-pattern alerts · minimum-wage auto-check · expiring document/cert alerts · org chart · bulk admin.

### Orders — Phase 1
Full order entry form (all §14.2 fields) · status tracking + state machine + badges · status search view · customer LE lookup.

### Orders — Phase 2
Line items + full product catalogue · sales-team tab · multi-agent commission splits.

### Orders — Phase 3
ERP Dump · monthly targets · achievement-% dashboard · rep & manager views · build the **SalesIQ DB source-adapter and run it in parallel for verification only** (the spreadsheet stays the live source — the actual switch is the end-of-project cutover).

### Orders — Phase 4
Commission engine (auto-calc, runs, statements, lock/sign-off) · CRQ workflow · BT-Commission-Paid reconciliation · **Schedule-5 reconciliation**.

### Orders — Phase 5
Generate Insight (CallIQ bridge) · attribution engine · deep intelligence integration.

### Recommended overall sequence
**Phase 0 → HR P1 → Orders P1 → HR P2 → Orders P2 → … interleaving**, so foundations are proven by the simplest slice of each module before the heavy workflows (commission engine, Schedule-5, role-change) land. Phase 0 + HR P1 + Orders P1 is the first deliverable milestone.

*(Effort: deliberately not quoting calendar dates without your velocity. Relative size: Phase 0 = L, HR P1 = L, Orders P1 = M, commission engine = L and risk-heavy, Schedule-5 = M. Happy to convert to a dated plan once you confirm how many hours/week go into this.)*

---

## 9. Risks & decisions

### 9.1 Risks & mitigations
| Risk | Mitigation |
|---|---|
| Scope is very large | Strict phasing; Phase 0 + thin slice of each module first; ship continuously. |
| Commission maths errors (money) | Tests-first engine; parallel run + penny-perfect reconciliation before cutover; versioned pay plans for auditability. |
| Financial-data leak | Five-layer isolation (§2.8); admin-only `financial` scope; encryption; audited reads. |
| True DB-role isolation limited on Railway | Schema split makes a later move to a restricted DB role/separate DB a config change; meanwhile depth-in-defence. |
| Sensitive PII + GDPR | Foundations in Phase 0; retention/erasure/export; UK/EU residency check. |
| Git/OneDrive workflow fragility (recurring) | Move the working repo out of OneDrive to `C:\dev\RepIQ`; this matters more now the codebase is growing. |
| Migration discipline | Alembic + reviewed migrations; no more ad-hoc ALTERs. |
| Document durability | Object storage from the start (not ephemeral disk). |

### 9.2 Decisions — CONFIRMED (Salem, 19 June 2026)
1. **Object/document storage** — ✅ **Cloudflare R2** (S3-compatible; cheapest). `core/storage.py` keeps the backend swappable.
2. **Data-residency** — ✅ **No restriction.** Simplifies hosting/storage region choice.
3. **Alembic adoption now** — ✅ **Yes.** Replace the ad-hoc `_ensure_columns` migrations.
4. **MFA** — ✅ **Yes**, TOTP authenticator app for admin.
5. **Move repo out of OneDrive** — ✅ **Yes** (to `C:\dev\RepIQ`). GitHub (RepIQ-v2) is the sync point: Claude edits in the mounted workspace and pushes; Salem works from a clone in `C:\dev\RepIQ`. This ends the recurring `.git` corruption/lock issues as the codebase grows.
6. **Data exports** — ✅ **Available.** Salem can provide a SafeHR export + NetSuite ERP-Dump + the Excel trackers when the import phase begins.
7. **Operations role** — ✅ **Yes**, initial holders **Zahida, James, Lee, Michelle, Elli**. The `operations` role is **admin-assignable** (granted/revoked per user from the People page) — *not* a hardcoded list — so the team can change over time without a code change.

---

## 10. Appendices

### 10.1 Proposed table inventory (by schema)
- **`hr`:** employees, departments, employee_personal, employee_contact, employee_emergency_contacts, employee_medical, employee_roles, employee_role_history, role_changes, employee_contract, employee_hours, employee_location, employee_leave_entitlements, leave_requests, employee_absences, employee_records, probation_reviews, employee_goals, employee_feedback, employee_training, employee_qualifications, employee_assets, employee_documents.
- **`hr_financial`:** employee_pay, employee_benefits, employee_benefits_cost, commissions, commission_statements.
- **`orders`:** customers, products, orders, order_lines, order_agents, order_status_log, order_disputes, crq_references, targets, pay_plans, commission_runs, schedule5_imports, schedule5_rows, schedule5_reconciliation, schedule5_resolutions.
- **`public` (shared core):** audit_log, notification_queue, auth_sessions, (existing: users, teams, calls, settings, performance_videos, …).

### 10.2 Naming & conventions
UUID PKs on new tables · `snake_case` tables/columns · timestamps + soft-delete + `metadata JSONB` on majors · enums as Python `Enum` + DB check/enum types · all money as integer pence or `Numeric(12,2)` (never float) · all sensitive writes audited · API versioned `/api/v1/<module>/…`.

### 10.3 Phase 0 — concrete first tickets
1. Add `core/` package + `ModuleSpec`/registry; wire `main.py` to build from the registry (no behaviour change).
2. Introduce Alembic; baseline current schema as revision 0001; switch container start to `alembic upgrade head`.
3. `core/rbac.py`: add `User.platform_role` + `User.scopes`; data migration mapping existing users; `require_role`/`require_scope`/`team_scoped`; wrap the old `require_admin`/`require_manager`.
4. `core/audit.py` + `audit_log` table + `before_flush` diffing + read endpoints.
5. `core/projection.py` with field-group scopes + tests.
6. `core/crypto.py` (AES-256-GCM) + `FINANCIAL_ENC_KEY`; base mixins.
7. Promote `salesiq/fincal.py` → `core/calendar.py` (keep a shim import).
8. `core/storage.py` + object-storage backend; `core/notifications.py` + worker hook.
9. Auth: `auth_sessions` + refresh-token rotation; TOTP MFA for admin.
10. Create empty `modules/hr` and `modules/orders` packages registered via the registry — ready for Phase 1.

---

*End of plan. This is a living document — once you confirm the §9.2 decisions I'll lock Phase 0 into concrete tickets and we build foundations first, exactly as the brief instructs.*
