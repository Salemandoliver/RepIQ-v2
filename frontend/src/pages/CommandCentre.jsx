import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Avatar, Spinner, EmptyState, Modal, CollapsibleCard } from "../components/ui.jsx";
import WeeklyVideo from "../components/WeeklyVideo.jsx";
import ReviewVideo from "../components/ReviewVideo.jsx";
import TeamLeague from "../components/TeamLeague.jsx";
import CampaignAlerts from "../components/CampaignAlerts.jsx";
import { InsightsFeed } from "../components/Insights.jsx";
import OracleAsk from "../components/Oracle.jsx";
import WeeklyForecastManager from "../components/WeeklyForecastManager.jsx";
import ReflectionsManager from "../components/ReflectionsManager.jsx";
import { useCachedGet } from "../useCachedGet.js";
import { formatDuration } from "../utils";

function WeeklyVideoPicker() {
  const [people, setPeople] = useState([]);
  const [sel, setSel] = useState("");
  const [period, setPeriod] = useState("month");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => { api.get("/api/intelligence/video/people").then((d) => setPeople(d.people || [])).catch(() => {}); }, []);

  const genReview = async () => {
    if (!sel) return;
    setBusy(true); setMsg("Generating review…");
    try {
      const r = await api.post("/api/intelligence/video/review/generate", { userId: Number(sel), period });
      setMsg(r.hasVideo ? "Review ready — video rendered." : r.status === "rendering" ? "Script ready — video rendering…" : "Review written (set HeyGen keys to render Gary's video).");
      setReloadKey((k) => k + 1);
    } catch (e) { setMsg(e.message || "Couldn't generate the review."); }
    finally { setBusy(false); }
  };

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="flex" style={{ gap: 8, marginBottom: 10, flexWrap: "wrap", alignItems: "center" }}>
        <span aria-hidden="true">🎬</span>
        <span style={{ fontWeight: 700, fontSize: 15 }}>Performance videos</span>
        <select className="input" value={sel} onChange={(e) => { setSel(e.target.value); setMsg(""); }} style={{ width: "auto", marginLeft: "auto" }} aria-label="Choose a rep or BC">
          <option value="">Choose a rep / BC…</option>
          {people.map((p) => <option key={p.id} value={p.id}>{p.name}{p.role === "bc" ? " (BC)" : ""}</option>)}
        </select>
        {sel && <>
          <select className="input" value={period} onChange={(e) => setPeriod(e.target.value)} style={{ width: "auto" }} aria-label="Review period">
            <option value="month">Monthly</option>
            <option value="quarter">Quarterly</option>
          </select>
          <button className="btn btn-outline btn-sm" disabled={busy} onClick={genReview} title="Generate this rep's review now (for testing)">{busy ? "Working…" : "↻ Generate review (test)"}</button>
        </>}
      </div>
      {msg && <div className="muted small" style={{ marginBottom: 10 }}>{msg}</div>}
      {sel ? <><ReviewVideo userId={Number(sel)} reloadKey={reloadKey} /><WeeklyVideo userId={Number(sel)} /></> : <div className="muted small">Pick a rep or BC to watch their weekly video and monthly/quarterly review.</div>}
    </div>
  );
}

const DEAL_TAG = {
  "Proposal due": { bg: "rgba(239,68,68,0.1)", color: "var(--red)" },
  "Callback owed": { bg: "rgba(245,158,11,0.12)", color: "var(--amber)" },
  "Warm": { bg: "rgba(34,197,94,0.12)", color: "var(--green)" },
};

function ProgressBar() {
  const [p, setP] = useState(8);
  useEffect(() => {
    const id = setInterval(() => setP((x) => Math.min(92, x + Math.random() * 16)), 170);
    return () => clearInterval(id);
  }, []);
  return (
    <div style={{ height: 4, background: "#e9ebef", borderRadius: 3, overflow: "hidden", margin: "14px 0 22px" }}>
      <div style={{ width: `${p}%`, height: "100%", background: "var(--accent-grad)", transition: "width .2s ease" }} />
    </div>
  );
}

/* Feature 4 — Manager Team Command Centre (Phase 1).
   Team aggregates + Smart Alerts + a sortable rep grid with a drill-down scorecard. */

const ragColor = (r) => ({ green: "var(--green)", amber: "var(--amber)", red: "var(--red)" }[r] || "var(--text-soft)");
const TREND = { improving: { a: "↑", c: "var(--green)" }, declining: { a: "↓", c: "var(--red)" }, flat: { a: "→", c: "var(--text-soft)" } };
const SORTS = [
  { k: "achievementPct", label: "Target", hint: "Sort by how far through this month's sales target each rep is" },
  { k: "yesterdayQuality", label: "Quality", hint: "Sort by yesterday's average call-quality score (out of 100)" },
  { k: "yesterdayCalls", label: "Calls", hint: "Sort by the number of calls made yesterday" },
  { k: "name", label: "Name", hint: "Sort alphabetically by name" },
];
// Smart-alert presentation: an icon, tint and heading per alert type.
const ALERT_META = {
  no_calls: { icon: "📵", bg: "rgba(239,68,68,0.08)", bar: "var(--red)" },
  declining: { icon: "📉", bg: "rgba(239,68,68,0.08)", bar: "var(--red)" },
  improving: { icon: "🚀", bg: "rgba(34,197,94,0.10)", bar: "var(--green)" },
  overdue_callbacks: { icon: "⏰", bg: "rgba(245,158,11,0.10)", bar: "var(--amber)" },
  forecast_missing: { icon: "🎯", bg: "rgba(245,158,11,0.10)", bar: "var(--amber)" },
  forecast_behind: { icon: "🎯", bg: "rgba(239,68,68,0.08)", bar: "var(--red)" },
  reflection_missing: { icon: "💬", bg: "rgba(109,40,217,0.08)", bar: "var(--accent)" },
  reflection_blocker: { icon: "🪻", bg: "rgba(245,158,11,0.10)", bar: "var(--amber)" },
};

function RepScorecard({ userId, onClose }) {
  const [d, setD] = useState(null);
  useEffect(() => { api.get(`/api/intelligence/scorecard/${userId}`).then(setD).catch(() => setD(null)); }, [userId]);
  const y = d?.yesterday, mtd = d?.monthToDate;
  return (
    <Modal title={d ? d.meta.name : "Loading…"} onClose={onClose} wide>
      {!d ? <div className="flex" style={{ justifyContent: "center", padding: 40 }}><Spinner /></div> : (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
            <Stat label="Quality (yest.)" value={y.quality != null ? Math.round(y.quality) : "—"} />
            <Stat label="Calls (yest.)" value={y.calls} sub={`avg ${y.dailyAvgCalls}/day`} />
            <Stat label="Talk time" value={formatDuration(y.talkTimeSec)} />
            <Stat label="Orders" value={y.ordersYesterday} />
          </div>
          {mtd && !mtd.unavailable && mtd.type !== "bc" && (
            <div style={{ padding: "10px 12px", background: "#f7f8fa", borderRadius: 10 }}>
              <div className="small"><b>This month:</b> {mtd.sovPct != null ? `${mtd.sovPct}% of SOV target` : "—"}
                {mtd.predictor?.projectedFinishPct != null && <> · projected finish <b style={{ color: ragColor(mtd.predictor.rag) }}>{mtd.predictor.projectedFinishPct}%</b></>}
                {mtd.daysRemaining != null && <> · {mtd.daysRemaining} days left</>}
              </div>
            </div>
          )}
          <div>
            <div className="card-title">Skill snapshot</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 10 }}>
              {(d.skills?.skills || []).map((s) => {
                const latest = [...(d.skills.series || [])].reverse().find((p) => p[s.key] != null);
                const v = latest ? latest[s.key] : null;
                return (
                  <div key={s.key} style={{ border: "1px solid var(--border)", borderRadius: 10, padding: "8px 10px" }}>
                    <div className="muted small">{s.label}</div>
                    <div style={{ fontWeight: 700 }}>{v != null ? v : "—"}
                      {s.teamAvg != null && <span className="muted small" style={{ fontWeight: 400 }}> · team {s.teamAvg}</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}

function Stat({ label, value, sub }) {
  return (
    <div style={{ flex: "1 1 120px", background: "#fff", border: "1px solid var(--border)", borderRadius: 10, padding: "10px 12px" }}>
      <div className="muted small">{label}</div>
      <div style={{ fontSize: 20, fontWeight: 800 }}>{value}</div>
      {sub && <div className="muted small">{sub}</div>}
    </div>
  );
}

// Deal highlight cycles through three stages on each click.
const NEXT_STATUS = { null: "actioning", actioning: "actioned", actioned: null };

export default function CommandCentre() {
  // Keep the team data cached for 30 min so returning to this page (e.g. after listening to a
  // call) serves instantly from cache while any refresh happens silently in the background.
  const { data, loading, refresh } = useCachedGet("/api/intelligence/team", { ttl: 30 * 60 * 1000 });
  const [sort, setSort] = useState("achievementPct");
  const [drill, setDrill] = useState(null);
  const [hl, setHl] = useState({});         // local override of deal highlight state, by dealKey
  const load = refresh;

  // Cycle a deal: (none) → Highlight/Actioning → Actioned → (none). Shared across all managers.
  const cycleDeal = async (d) => {
    const cur = hl[d.dealKey]?.status ?? d.status ?? null;
    const next = NEXT_STATUS[cur] ?? "actioning";
    setHl((m) => ({ ...m, [d.dealKey]: { status: next, actionedBy: next ? "You" : null } }));
    try {
      const r = await api.post("/api/intelligence/deals/highlight", { dealKey: d.dealKey, company: d.company, rep: d.rep, status: next });
      setHl((m) => ({ ...m, [d.dealKey]: { status: r.status ?? null, actionedBy: r.actionedBy } }));
    } catch (e) {
      setHl((m) => ({ ...m, [d.dealKey]: { status: cur, actionedBy: d.actionedBy } }));   // revert
    }
  };

  const reps = useMemo(() => {
    if (!data) return [];
    const rows = [...data.reps];
    rows.sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name);
      return (b[sort] ?? -1) - (a[sort] ?? -1);
    });
    return rows;
  }, [data, sort]);

  // Only block the whole page on the very first load (no cached data yet). On return visits we
  // already have data, so we render it immediately and let any refresh run silently in the
  // background (the Refresh button shows "Refreshing…") — no more multi-minute blank wait.
  if (loading && !data) return (
    <div className="page" style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 22px" }}>
      <h1 style={{ margin: 0, fontSize: 26 }}>Team Command Centre</h1>
      <div className="muted small">Pulling the team together…</div>
      <ProgressBar />
    </div>
  );
  if (!data) return <EmptyState icon="📭" title="Couldn't load the command centre" />;

  const ag = data.aggregates;
  return (
    <div className="page" style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 22px 60px" }}>
      <div className="spread" style={{ alignItems: "flex-start" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26 }}>Team Command Centre</h1>
          <div className="muted" style={{ marginBottom: 16 }}>{data.meta.date}</div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>{loading ? "Refreshing…" : "↻ Refresh"}</button>
      </div>

      {/* Aggregates */}
      <div className="flex" style={{ gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <Stat label="Team achievement" value={ag.teamAchievementPct != null ? `${ag.teamAchievementPct}%` : "—"} />
        <Stat label="Orders this month" value={ag.ordersMTD} />
        <Stat label="Calls yesterday" value={ag.totalCallsYesterday} />
        <Stat label="Avg quality (yest.)" value={ag.avgQualityYesterday != null ? Math.round(ag.avgQualityYesterday) : "—"} />
        <Stat label="Reps" value={ag.reps} />
      </div>

      {/* Ask the Oracle — one Ask: operational (this week/month) + cross-team patterns + knowledge library */}
      <OracleAsk />

      {/* Weekly Forecast — team Data/Cloud/Mobile vs placed orders, per-rep + reliability + edit */}
      <WeeklyForecastManager />

      {/* Review Reflections — who's reflected, blockers needing help, themes, per-rep + transcripts */}
      <ReflectionsManager />

      {/* The insight engine's prioritised, evidence-bound action list */}
      <InsightsFeed />

      {/* Campaigns needing a nudge — weak adoption / ending soon */}
      <CampaignAlerts />

      {/* Team league — ranked by call quality, with most-improved */}
      <div style={{ marginBottom: 16 }}><TeamLeague /></div>

      {/* Weekly performance videos — pick any rep/BC */}
      <WeeklyVideoPicker />

      {/* Deals to get over the line — collapsible to keep the view clean */}
      {data.deals?.length > 0 && (
        <CollapsibleCard title="🔥 Deals to get over the line" style={{ marginBottom: 16 }}
          actions={<span className="muted small">{data.deals.length} warm &amp; open · push to signing</span>}>
          {data.deals.map((d, i) => {
            const t = DEAL_TAG[d.tag] || DEAL_TAG["Warm"];
            const arrow = d.momentum === "up" ? { c: "var(--green)", g: "↑", t: "heating up" }
              : d.momentum === "down" ? { c: "var(--red)", g: "↓", t: "going cold" }
              : { c: "var(--text-faint)", g: "→", t: "steady" };
            const status = hl[d.dealKey]?.status ?? d.status ?? null;   // null | "actioning" | "actioned"
            const actionedBy = hl[d.dealKey]?.actionedBy ?? d.actionedBy;
            const isActioning = status === "actioning";
            const isActioned = status === "actioned";
            const rowBg = isActioned ? "color-mix(in srgb, var(--green) 8%, transparent)"
              : isActioning ? "color-mix(in srgb, var(--accent) 6%, transparent)" : undefined;
            return (
              <div key={i} className="flex" style={{ gap: 11, alignItems: "flex-start", padding: "11px 0", borderTop: i ? "1px solid var(--border)" : "none", background: rowBg }}>
                <span className="small" style={{ fontWeight: 600, padding: "3px 9px", borderRadius: 8, whiteSpace: "nowrap", background: t.bg, color: t.color }}>{d.tag}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14 }}>
                    <span title={`Momentum: ${arrow.t}`} style={{ color: arrow.c, fontWeight: 700, marginRight: 5 }}>{arrow.g}</span>
                    <strong>{d.company}</strong> — {d.rep}{d.ageDays > 0 ? ` · ${d.ageDays}d ago` : ""}
                  </div>
                  <div className="muted small" style={{ marginTop: 3, lineHeight: 1.5 }}>{d.action}{d.proposal ? `: ${d.proposal}` : ""}</div>
                  {d.products?.length > 0 && (
                    <div className="flex" style={{ flexWrap: "wrap", gap: 4, marginTop: 5 }}>
                      {d.products.map((p, pi) => (
                        <span key={pi} className="chip" style={{ fontSize: 11 }}>
                          <span className="dot" style={{ background: p.color, width: 7, height: 7 }} />{p.name}
                        </span>
                      ))}
                    </div>
                  )}
                  {isActioning && <div className="small" style={{ marginTop: 4, color: "var(--accent)", fontWeight: 600 }}>● Being actioned{actionedBy ? ` — ${actionedBy}` : ""}</div>}
                  {isActioned && <div className="small" style={{ marginTop: 4, color: "var(--green)", fontWeight: 600 }}>✓ Actioned{actionedBy ? ` — ${actionedBy}` : ""}</div>}
                </div>
                <div className="flex" style={{ gap: 6, flexShrink: 0, flexWrap: "wrap", justifyContent: "flex-end" }}>
                  <button className={`btn btn-sm ${isActioning ? "btn-primary" : "btn-outline"}`} onClick={() => cycleDeal(d)}
                    style={isActioned ? { background: "var(--green)", borderColor: "var(--green)", color: "#fff" } : undefined}
                    title={isActioned ? "Done — click to clear the highlight" : isActioning ? "Mark as actioned (done)" : "Mark as being actioned (shared with all managers)"}>
                    {isActioned ? "✓ Actioned" : isActioning ? "✓ Actioning" : "Highlight"}
                  </button>
                  <Link to={`/calls/${d.callId}`} className="btn btn-outline btn-sm">Open</Link>
                </div>
              </div>
            );
          })}
        </CollapsibleCard>
      )}

      {/* Smart alerts */}
      {data.alerts.length > 0 && (() => {
        const behind = data.alerts.filter((a) => a.type === "behind_target");
        const others = data.alerts.filter((a) => a.type !== "behind_target");
        return (
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="spread" style={{ marginBottom: 12 }}>
              <div className="card-title" style={{ margin: 0 }}>Smart alerts</div>
              <span className="muted small">{data.alerts.length} flagged</span>
            </div>

            {others.length > 0 && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 10, marginBottom: behind.length ? 16 : 0 }}>
                <style>{`
                  .cc-alert { position: relative; }
                  .cc-alert.has-tip { cursor: help; }
                  .cc-tip { position: absolute; left: 12px; right: 12px; top: calc(100% + 6px); z-index: 50;
                    background: #1f2430; color: #fff; border-radius: 8px; padding: 9px 11px; font-size: 12px;
                    font-weight: 400; line-height: 1.5; box-shadow: 0 8px 24px rgba(0,0,0,.22);
                    opacity: 0; visibility: hidden; transition: .12s ease; transform: translateY(-3px); }
                  .cc-alert:hover .cc-tip, .cc-alert:focus .cc-tip { opacity: 1; visibility: visible; transform: translateY(0); }
                `}</style>
                {others.map((al, i) => {
                  const m = ALERT_META[al.type] || { icon: "•", bg: "#f3f4f6", bar: "var(--text-soft)" };
                  return (
                    <div key={i} tabIndex={al.detail ? 0 : undefined}
                      className={"cc-alert flex" + (al.detail ? " has-tip" : "")}
                      style={{ gap: 11, alignItems: "center", background: m.bg, borderLeft: `3px solid ${m.bar}`, borderRadius: 9, padding: "11px 13px" }}>
                      <span style={{ fontSize: 19, lineHeight: 1 }}>{m.icon}</span>
                      <span className="small" style={{ lineHeight: 1.4 }}>{al.text}{al.detail ? <span style={{ color: "var(--text-faint)" }}> ⓘ</span> : null}</span>
                      {al.detail && <span className="cc-tip">{al.detail}</span>}
                    </div>
                  );
                })}
              </div>
            )}

            {behind.length > 0 && (
              <div>
                <div className="small" style={{ fontWeight: 700, marginBottom: 9, display: "flex", alignItems: "center", gap: 7 }}>
                  <span style={{ fontSize: 17 }}>🎯</span> Behind target this month
                  <span className="muted" style={{ fontWeight: 500 }}>· {behind.length} rep{behind.length === 1 ? "" : "s"}</span>
                </div>
                <div className="flex" style={{ flexWrap: "wrap", gap: 8 }}>
                  {[...behind].sort((a, b) => (a.pct ?? 0) - (b.pct ?? 0)).map((al, i) => (
                    <button key={i} onClick={() => setDrill(al.userId)} title={`Open ${al.rep}'s scorecard`}
                      style={{ display: "inline-flex", gap: 7, alignItems: "center", background: "#fff", border: "1px solid var(--border)", borderLeft: "3px solid var(--red)", borderRadius: 8, padding: "5px 11px", cursor: "pointer" }}>
                      <span className="small" style={{ fontWeight: 600 }}>{al.rep}</span>
                      <span className="small" style={{ fontWeight: 800, color: "var(--red)" }}>{al.pct}%</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })()}

      {/* Coaching priority — whole team */}
      {data.coachingPriority && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="flex" style={{ gap: 8, marginBottom: 6 }}>
            <span aria-hidden="true">💡</span>
            <span style={{ fontWeight: 700, fontSize: 15 }}>Coaching priority — whole team</span>
          </div>
          <div style={{ background: "var(--surface-2, #f3f4f6)", borderRadius: 10, padding: "11px 13px", fontSize: 14, lineHeight: 1.5 }}>
            {data.coachingPriority.action}
          </div>
        </div>
      )}

      {/* Rep grid */}
      <div className="spread" style={{ marginBottom: 6, flexWrap: "wrap", gap: 10 }}>
        <div className="card-title" style={{ margin: 0 }}>Reps</div>
        <div className="flex" style={{ gap: 8, alignItems: "center" }}>
          <span className="muted small">Sort by</span>
          <div className="pill-tabs">
            {SORTS.map((s) => (
              <button key={s.k} className={sort === s.k ? "active" : ""} onClick={() => setSort(s.k)} title={s.hint}>{s.label}</button>
            ))}
          </div>
        </div>
      </div>
      <div className="muted small" style={{ marginBottom: 12, lineHeight: 1.55, maxWidth: 760 }}>
        Each card shows <b>Quality</b> (yesterday's average call score out of 100), <b>Calls</b> (calls made
        yesterday vs the rep's usual daily average), and <b>Target</b> (how far through this month's sales
        target they are — i.e. their achievement). The arrow is their 7-day quality trend. Click a card for the rep's scorecard.
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
        {reps.map((r) => {
          const tr = TREND[r.trend] || TREND.flat;
          return (
            <div key={r.userId} className="card" style={{ cursor: "pointer", padding: 14 }} onClick={() => setDrill(r.userId)}>
              <div className="flex" style={{ gap: 10, marginBottom: 10 }}>
                <Avatar name={r.name} color={r.avatarColor} size={38} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="spread">
                    <span style={{ fontWeight: 700 }}>{r.name}</span>
                    <span style={{ color: tr.c, fontWeight: 800 }}>{tr.a}</span>
                  </div>
                  <div className="muted small" style={{ textTransform: "capitalize" }}>{r.role}</div>
                </div>
              </div>
              <div className="flex" style={{ gap: 8 }}>
                <div style={{ flex: 1 }}>
                  <div className="muted small">Quality</div>
                  <div style={{ fontWeight: 800, fontSize: 18, color: r.yesterdayQuality == null ? "var(--text-faint)" : r.yesterdayQuality >= 70 ? "var(--green)" : r.yesterdayQuality >= 50 ? "var(--amber)" : "var(--red)" }}>
                    {r.yesterdayQuality != null ? Math.round(r.yesterdayQuality) : "—"}
                  </div>
                </div>
                <div style={{ flex: 1 }}>
                  <div className="muted small">Calls</div>
                  <div style={{ fontWeight: 800, fontSize: 18 }}>{r.yesterdayCalls}<span className="muted small" style={{ fontWeight: 400 }}> /{r.dailyAvgCalls}</span></div>
                </div>
                <div style={{ flex: 1 }}>
                  <div className="muted small">Target</div>
                  <div style={{ fontWeight: 800, fontSize: 18, color: ragColor(r.rag) }}>{r.achievementPct != null ? `${r.achievementPct}%` : "—"}</div>
                </div>
              </div>
              {r.achievementPct != null && (
                <div style={{ height: 6, borderRadius: 4, background: "#e9ebef", overflow: "hidden", marginTop: 10 }}>
                  <div style={{ width: `${Math.min(100, r.achievementPct)}%`, height: "100%", background: ragColor(r.rag) }} />
                </div>
              )}
              {r.alerts.length > 0 && (
                <div className="flex" style={{ gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                  {r.alerts.map((a, i) => (
                    <span key={i} className="small" style={{ background: a === "improving" ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.1)", color: a === "improving" ? "var(--green)" : "var(--red)", borderRadius: 6, padding: "1px 7px", fontWeight: 600 }}>
                      {a.replace("_", " ")}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {drill && <RepScorecard userId={drill} onClose={() => setDrill(null)} />}
    </div>
  );
}
