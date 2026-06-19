import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import { useToast } from "../components/Toast.jsx";
import { Avatar, Skeleton, EmptyState } from "../components/ui.jsx";
import { formatDuration, relativeDate } from "../utils";
import {
  SearchIcon,
  BuildingIcon,
  UsersIcon,
  MailIcon,
  GlobeIcon,
  LinkedinIcon,
  MapPinIcon,
  PhoneIcon,
  ClockIcon,
  CheckCircleIcon,
} from "../components/Icons.jsx";

const SOURCE_LABELS = {
  companies_house: "Companies House",
  apollo: "Apollo.io",
  hunter: "Hunter.io",
  lemlist: "Lemlist",
  google_places: "Google Places",
  mastersheet: "Companies DB",
  sales_tracker: "Sales Tracker",
};

const ORDER_STATUS = {
  confirmed: "ok",
  pending: "warn",
  cancelled: "faint",
};

function fmtMoney(v) {
  if (v == null || v === "") return "—";
  if (typeof v === "number") return "£" + v.toLocaleString("en-GB");
  return String(v);
}

function OrderHistory({ data }) {
  const [expanded, setExpanded] = useState(false);
  const oh = data.orderHistory;
  if (!oh || oh.available === false) {
    return <div className="ciq-faint">Order history unavailable.</div>;
  }
  if (!oh.totalOrders) {
    return <div className="ciq-faint">No previous orders on record.</div>;
  }
  const orders = oh.orders || [];
  const shown = expanded ? orders : orders.slice(0, 3);
  return (
    <div>
      <div className="ciq-orders-summary">
        {oh.totalOrders} previous {oh.totalOrders === 1 ? "order" : "orders"}
        {oh.lastOrderDate ? ` — last order ${oh.lastOrderDate}` : ""}
      </div>
      <div className="ciq-orders">
        {shown.map((o, i) => (
          <div className="ciq-order-row" key={i}>
            <span className="ciq-order-date">{o.date || "—"}</span>
            <div className="ciq-order-mid">
              <div className="ciq-order-product">{o.product || "Order"}</div>
              {o.rep && <div className="ciq-faint">{o.rep}</div>}
            </div>
            <div className="ciq-order-right">
              <span className="ciq-order-value">{fmtMoney(o.value)}</span>
              {o.status && (
                <span className={"ciq-ostatus " + (ORDER_STATUS[String(o.status).toLowerCase()] || "faint")}>
                  {o.status}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
      {orders.length > 3 && (
        <button className="ciq-orders-toggle" onClick={() => setExpanded((e) => !e)}>
          {expanded ? "Show fewer" : `View all ${oh.totalOrders} orders`}
        </button>
      )}
    </div>
  );
}

const SRC_SHORT = { apollo: "Apollo", mastersheet: "Companies DB", companies_house: "Companies House" };

function ConfChip({ meta }) {
  if (!meta) return null;
  const cls = { high: "ok", medium: "warn", low: "faint" }[meta.confidence] || "faint";
  return <span className={"ciq-badge " + cls}>est · {SRC_SHORT[meta.source] || meta.source}</span>;
}

function fmtRevenue(v) {
  if (typeof v === "number") {
    if (v >= 1e6) return `£${(v / 1e6).toFixed(v % 1e6 ? 1 : 0)}m`;
    if (v >= 1e3) return `£${Math.round(v / 1e3)}k`;
    return `£${v}`;
  }
  return v;
}

function statusDot(ok) {
  return <span className="ciq-dot" style={{ background: ok ? "var(--green)" : "var(--text-faint)" }} />;
}

function emailBadge(status) {
  if (status === "verified") return <span className="ciq-badge ok">✓ Verified</span>;
  if (status === "inferred") return <span className="ciq-badge warn">⚠ Inferred</span>;
  return <span className="ciq-badge faint">Estimated</span>;
}

function Section({ label, children }) {
  return (
    <div className="ciq-section">
      <div className="ciq-section-label">{label}</div>
      {children}
    </div>
  );
}

function dispositionLabel(d) {
  return ({ answered: "Answered", no_answer: "No answer", voicemail: "Voicemail" }[d] || d || "—");
}

const PRIORITY = {
  HIGH: { bg: "#fef3c7", fg: "#b45309", label: "HIGH PRIORITY" },
  MEDIUM: { bg: "#e0e7ff", fg: "#4338ca", label: "MEDIUM PRIORITY" },
  LOW: { bg: "#f1f5f9", fg: "#64748b", label: "LOW PRIORITY" },
};

function Bullets({ items, warn }) {
  return (
    <ul className={"ciq-bullets" + (warn ? " warn" : "")}>
      {items.map((s, i) => (
        <li key={i}>{s}</li>
      ))}
    </ul>
  );
}

function ReportView({ data }) {
  const r = data.report;
  if (!r) {
    return (
      <div className="card ciq-report-empty">
        <div className="ciq-faint">{data.reportError || "No report available."}</div>
      </div>
    );
  }
  const pri = PRIORITY[r.priority?.rating] || PRIORITY.MEDIUM;
  return (
    <div className="ciq-report">
      <div className="ciq-report-head">
        <span className="ciq-priority" style={{ background: pri.bg, color: pri.fg }}>★ {pri.label}</span>
        {r.priority?.reason && <span className="muted small">{r.priority.reason}</span>}
        {data.meta?.reportCached && <span className="small faint" style={{ marginLeft: "auto" }}>cached</span>}
      </div>

      {r.tldr && (
        <div className="ciq-tldr">
          <div className="ciq-rep-label">TL;DR</div>
          {r.tldr}
        </div>
      )}

      <div className="ciq-report-grid">
        {r.whatTheyDo && (
          <div className="card">
            <h3 className="card-title">What they do</h3>
            <p style={{ margin: 0 }}>{r.whatTheyDo}</p>
          </div>
        )}
        {r.telecomSetup && (
          <div className="card">
            <h3 className="card-title">Telecom angle</h3>
            <p style={{ margin: 0 }}>{r.telecomSetup}</p>
          </div>
        )}
      </div>

      {(r.growthSignals?.length > 0 || data.timeline?.length > 0) && (
        <div className="card">
          <h3 className="card-title">Growth &amp; recent signals</h3>
          {r.growthSignals?.length > 0 && <Bullets items={r.growthSignals} />}
          {data.timeline?.length > 0 && (
            <div className="ciq-timeline">
              {data.timeline.slice(0, 8).map((t, i) => (
                <div className="ciq-tl-row" key={i}>
                  <span className="ciq-tl-date">{String(t.date).slice(0, 10)}</span>
                  <span className="ciq-tl-desc">{t.description}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {r.decisionMakers?.length > 0 && (
        <div className="card">
          <h3 className="card-title">Decision makers</h3>
          {r.decisionMakers.map((d, i) => (
            <div className={"ciq-dm-row" + (d.startHere ? " start" : "")} key={i}>
              <div>
                <strong>{d.name}</strong>
                {d.role && <span className="ciq-faint"> · {d.role}</span>}
                {d.startHere && <span className="ciq-starthere">START HERE</span>}
              </div>
              {d.guidance && <div className="ciq-faint" style={{ marginTop: 2 }}>{d.guidance}</div>}
            </div>
          ))}
        </div>
      )}

      {r.pitch && (
        <div className="ciq-pitch">
          <div className="ciq-rep-label light">The pitch</div>
          <blockquote>"{r.pitch}"</blockquote>
        </div>
      )}

      <div className="ciq-report-grid">
        {r.keyAngles?.length > 0 && (
          <div className="card">
            <h3 className="card-title">Key angles</h3>
            <Bullets items={r.keyAngles} />
          </div>
        )}
        {r.watchOuts?.length > 0 && (
          <div className="card">
            <h3 className="card-title">Watch-outs</h3>
            <Bullets items={r.watchOuts} warn />
          </div>
        )}
      </div>
    </div>
  );
}

export default function CompanyIQ() {
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [providers, setProviders] = useState(null);
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    api.get("/api/companyiq/status").then((d) => setProviders(d?.providers || {})).catch(() => {});
    inputRef.current?.focus();
  }, []);

  const lookup = async (e) => {
    e?.preventDefault();
    const q = query.trim();
    const p = phone.trim();
    if (!q && !p) return;
    setLoading(true);
    setData(null);
    setReport(null);
    try {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (p) params.set("phone", p);
      const d = await api.get(`/api/companyiq/lookup?${params.toString()}`);
      setData(d);
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setLoading(false);
    }
  };

  const generateReport = async (refresh = false) => {
    const q = query.trim();
    const p = phone.trim();
    if (!q && !p) return;
    setReportLoading(true);
    try {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (p) params.set("phone", p);
      if (refresh) params.set("refresh", "true");
      const d = await api.get(`/api/companyiq/report?${params.toString()}`);
      setReport(d);
      if (d.reportError) toast(d.reportError, "error");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setReportLoading(false);
    }
  };

  const company = data?.company;
  const contacts = data?.contacts || [];
  const primary = contacts.find((c) => c.isPrimary) || contacts[0];
  const others = contacts.filter((c) => c !== primary).slice(0, 4);
  const intel = data?.sectorIntel;
  const hist = data?.callHistory;
  const outreach = data?.outreach;

  return (
    <div className="page">
      <div className="spread" style={{ marginBottom: 8, flexWrap: "wrap" }}>
        <div>
          <h1 className="page-title">
            <span className="flex">
              <BuildingIcon size={22} /> CompanyIQ
            </span>
          </h1>
          <p className="page-sub">In-call intelligence — company profile, decision makers, sector angle and history in one glance.</p>
        </div>
      </div>

      <form className="ciq-search" onSubmit={lookup}>
        <SearchIcon size={18} />
        <input
          ref={inputRef}
          className="ciq-search-input"
          placeholder="Company name or Companies House number…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="ciq-search-div" />
        <PhoneIcon size={16} />
        <input
          className="ciq-search-input ciq-search-phone"
          placeholder="Number being dialled (optional)"
          value={phone}
          inputMode="tel"
          onChange={(e) => setPhone(e.target.value)}
        />
        <button type="submit" className="btn btn-primary" disabled={loading || (!query.trim() && !phone.trim())}>
          {loading ? "Looking up…" : "Look up"}
        </button>
      </form>

      {providers && (
        <div className="ciq-providers">
          {Object.entries(SOURCE_LABELS).map(([k, label]) => (
            <span key={k} className="ciq-provider" title={providers[k] ? "Connected" : "Add an API key in .env to enable"}>
              {statusDot(providers[k])} {label}
            </span>
          ))}
        </div>
      )}

      {loading ? (
        <div className="ciq-layout">
          <Skeleton h={460} style={{ borderRadius: 14 }} />
          <Skeleton h={460} style={{ borderRadius: 14 }} />
        </div>
      ) : !data ? (
        <div className="card" style={{ marginTop: 16 }}>
          <EmptyState
            icon="🔎"
            title="Look up a company"
            sub="Search by name, the number you're about to dial, or a Companies House number to pull its intelligence card."
          />
        </div>
      ) : data.status === "unresolved" ? (
        <div className="card" style={{ marginTop: 16 }}>
          <EmptyState
            icon="🏢"
            title="Company not found"
            sub={`Nothing matched "${data.query}". Try the registered company name or its Companies House number.`}
          />
        </div>
      ) : (
        <>
        <div className="ciq-report-bar">
          <button className="btn btn-primary" onClick={() => generateReport(false)} disabled={reportLoading}>
            {reportLoading ? "Generating intel report…" : report ? "Regenerate report" : "✨ Generate AI intel report"}
          </button>
          {report && !reportLoading && (
            <button className="btn btn-outline" onClick={() => generateReport(true)}>Refresh data</button>
          )}
        </div>
        <div className="ciq-layout">
          {/* ---- Primary intelligence card ---- */}
          <div className="ciq-card">
            <div className="ciq-card-head">
              <span className="ciq-dot live" /> CompanyIQ
            </div>

            <Section label="Company">
              <div className="ciq-company-name">{company?.name || "Unknown company"}</div>
              {data.dialledNumber && (
                <div className="ciq-dialling">
                  <PhoneIcon size={12} /> Dialling {data.dialledNumber}
                </div>
              )}
              <div className="ciq-meta-row">
                {company?.address?.locality && (
                  <span className="flex" style={{ gap: 4 }}>
                    <MapPinIcon size={13} /> {company.address.locality}
                  </span>
                )}
                {company?.employees != null && (
                  <span className="flex" style={{ gap: 5 }}>
                    <UsersIcon size={13} /> {company.employees} employees
                    <ConfChip meta={company.employeesMeta} />
                  </span>
                )}
              </div>
              {company?.revenue && (
                <div className="ciq-faint flex" style={{ gap: 6, flexWrap: "wrap" }}>
                  Turnover: {fmtRevenue(company.revenue)}
                  <ConfChip meta={company.revenueMeta} />
                </div>
              )}
              <div className="ciq-faint">
                {company?.incorporatedDate && <>Inc. {String(company.incorporatedDate).slice(0, 10)} · </>}
                {company?.status ? (
                  <span style={{ textTransform: "capitalize", color: company.status === "active" ? "var(--green)" : "var(--amber)" }}>
                    {company.status}
                  </span>
                ) : null}
                {company?.chNumber && <> · CH {company.chNumber}</>}
              </div>
              <div className="ciq-links">
                {company?.website && (
                  <a href={company.website} target="_blank" rel="noreferrer" className="ciq-link">
                    <GlobeIcon size={13} /> Website
                  </a>
                )}
                {company?.phone && (
                  <a href={`tel:${company.phone}`} className="ciq-link">
                    <PhoneIcon size={13} /> {company.phone}
                  </a>
                )}
              </div>
            </Section>

            <Section label="Decision maker">
              {primary ? (
                <>
                  <div className="ciq-dm-name">{primary.name || "Name unavailable"}</div>
                  <div className="ciq-faint" style={{ marginBottom: 6 }}>
                    {primary.title || "—"}
                    {primary.fromFiling && <span className="ciq-tag">From Companies House filing</span>}
                  </div>
                  <div className="ciq-links">
                    {primary.email && (
                      <a href={`mailto:${primary.email}`} className="ciq-link">
                        <MailIcon size={13} /> {primary.email}
                      </a>
                    )}
                    {primary.email && emailBadge(primary.emailStatus)}
                    {primary.linkedin && (
                      <a href={primary.linkedin} target="_blank" rel="noreferrer" className="ciq-link">
                        <LinkedinIcon size={13} /> LinkedIn
                      </a>
                    )}
                  </div>
                  {others.length > 0 && (
                    <div className="ciq-others">
                      {others.map((c, i) => (
                        <div key={i} className="ciq-other">
                          <strong>{c.name || "—"}</strong>
                          <span className="ciq-faint"> · {c.title || "Contact"}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="ciq-faint">
                  No decision-maker data{providers && !providers.apollo ? " — connect Apollo.io to enable." : "."}
                </div>
              )}
            </Section>

            {intel && (
              <Section label={`Sector · ${intel.tag}`}>
                <div className="ciq-intel" style={{ borderColor: intel.color }}>
                  {intel.brief}
                </div>
              </Section>
            )}
          </div>

          {/* ---- Supporting panel ---- */}
          <div className="ciq-side">
            <div className="card">
              <h3 className="card-title">
                <span className="flex">
                  <ClockIcon size={15} /> Call history{hist?.totalCalls ? ` · ${hist.totalCalls} calls` : ""}
                </span>
              </h3>
              {hist?.coolingOff && (
                <div className="ciq-flag warn">⚠ Attempted 3+ times with no answer — consider a cooling-off period.</div>
              )}
              {hist?.reachedDM && (
                <div className="ciq-flag ok">
                  <CheckCircleIcon size={13} /> A rep has previously spoken to this company.
                </div>
              )}
              {!hist || hist.log.length === 0 ? (
                <div className="ciq-faint">No prior calls to this company in RepIQ.</div>
              ) : (
                <div className="ciq-log">
                  {hist.log.slice(0, 8).map((c) => (
                    <Link key={c.id} to={`/calls/${c.id}`} className="ciq-log-row">
                      <Avatar name={c.repName} size={26} />
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div className="ciq-log-rep">{c.repName}</div>
                        <div className="ciq-faint">
                          {relativeDate(c.date)} · {formatDuration(c.durationSec)} · {dispositionLabel(c.disposition)}
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </div>

            <div className="card">
              <h3 className="card-title">Order history</h3>
              <OrderHistory data={data} />
            </div>

            <div className="card">
              <h3 className="card-title">Outreach</h3>
              {outreach ? (
                <div className="ciq-flag ok">
                  {outreach.replied
                    ? "⚑ Warm — replied to a Lemlist email. Treat as a follow-up, not a cold call."
                    : outreach.opened
                    ? `Opened email · ${outreach.campaignName || "active sequence"}`
                    : `In sequence: ${outreach.campaignName || "active"}`}
                  {outreach.lastEmailDate && (
                    <div className="ciq-faint" style={{ marginTop: 2 }}>
                      Last: {String(outreach.lastEmailDate).slice(0, 10)}
                      {outreach.lastEmailSubject ? ` — "${outreach.lastEmailSubject}"` : ""}
                    </div>
                  )}
                </div>
              ) : (
                <div className="ciq-faint">
                  No active outreach{providers && !providers.lemlist ? " — connect Lemlist to enable." : "."}
                </div>
              )}
            </div>

            {data.meta?.sources?.length > 0 && (
              <div className="small faint" style={{ textAlign: "center" }}>
                Sources: {data.meta.sources.map((s) => SOURCE_LABELS[s] || s).join(" · ")}
                {data.meta.servedFromCache ? " · cached" : ""}
              </div>
            )}
          </div>
        </div>
        {reportLoading && (
          <div className="card ciq-report-empty">
            <Skeleton h={28} style={{ borderRadius: 8, marginBottom: 10 }} />
            <Skeleton h={80} style={{ borderRadius: 8 }} />
            <div className="small muted" style={{ marginTop: 10 }}>Writing the intel briefing…</div>
          </div>
        )}
        {report && !reportLoading && <ReportView data={report} />}
        </>
      )}
    </div>
  );
}
