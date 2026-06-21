import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Avatar, Spinner, EmptyState, Modal } from "../components/ui.jsx";
import AskCopilot from "../components/AskCopilot.jsx";
import WeeklyVideo from "../components/WeeklyVideo.jsx";
import TeamLeague from "../components/TeamLeague.jsx";
import CampaignAlerts from "../components/CampaignAlerts.jsx";
import { InsightsFeed } from "../components/Insights.jsx";
import OracleAsk from "../components/Oracle.jsx";
import { formatDuration } from "../utils";

function WeeklyVideoPicker() {
  const [people, setPeople] = useState([]);
  const [sel, setSel] = useState("");
  useEffect(() => { api.get("/api/intelligence/video/people").then((d) => setPeople(d.people || [])).catch(() => {}); }, []);
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="flex" style={{ gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <span aria-hidden="true">🎬</span>
        <span style={{ fontWeight: 700, fontSize: 15 }}>Weekly performance videos</span>
        <select className="input" value={sel} onChange={(e) => setSel(e.target.value)} style={{ width: "auto", marginLeft: "auto" }} aria-label="Choose a rep or BC">
          <option value="">Choose a rep / BC…</option>
          {people.map((p) => <option key={p.id} value={p.id}>{p.name}{p.role === "bc" ? " (BC)" : ""}</option>)}
        </select>
      </div>
      {sel ? <WeeklyVideo userId={Number(sel)} /> : <div className="muted small">Pick a rep or BC to watch their weekly performance video.</div>}
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

export default function CommandCentre() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState("achievementPct");
  const [drill, setDrill] = useState(null);

  const load = () => {
    setLoading(true);
    api.get("/api/intelligence/team").then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  };
  useEffect(load, []);

  const reps = useMemo(() => {
    if (!data) return [];
    const rows = [...data.reps];
    rows.sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name);
      return (b[sort] ?? -1) - (a[sort] ?? -1);
    });
    return rows;
  }, [data, sort]);

  if (loading) return (
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

      {/* Ask RepIQ */}
      <div style={{ marginBottom: 16 }}>
        <AskCopilot title="Ask RepIQ" subtitle="the company's performance — team, deals and numbers"
          presets={["Which deals should we focus on?", "Who needs help today?", "How is the team performing this month?"]} />
      </div>

      {/* The insight engine's prioritised, evidence-bound action list */}
      <InsightsFeed />

      {/* The Org Oracle — cross-team Q&A + knowledge library */}
      <OracleAsk />

      {/* Campaigns needing a nudge — weak adoption / ending soon */}
      <CampaignAlerts />

      {/* Team league — ranked by call quality, with most-improved */}
      <div style={{ marginBottom: 16 }}><TeamLeague /></div>

      {/* Weekly performance videos — pick any rep/BC */}
      <WeeklyVideoPicker />

      {/* Deals to get over the line */}
      {data.deals?.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="spread" style={{ marginBottom: 12 }}>
            <div className="card-title" style={{ margin: 0 }}>🔥 Deals to get over the line</div>
            <span className="muted small">warm &amp; open · push to signing</span>
          </div>
          {data.deals.map((d, i) => {
            const t = DEAL_TAG[d.tag] || DEAL_TAG["Warm"];
            return (
              <div key={i} className="flex" style={{ gap: 11, alignItems: "flex-start", padding: "11px 0", borderTop: i ? "1px solid var(--border)" : "none" }}>
                <span className="small" style={{ fontWeight: 600, padding: "3px 9px", borderRadius: 8, whiteSpace: "nowrap", background: t.bg, color: t.color }}>{d.tag}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14 }}><strong>{d.company}</strong> — {d.rep}{d.ageDays > 0 ? ` · ${d.ageDays}d ago` : ""}</div>
                  <div className="muted small" style={{ marginTop: 3, lineHeight: 1.5 }}>{d.action}{d.proposal ? `: ${d.proposal}` : ""}</div>
                </div>
                <Link to={`/calls/${d.callId}`} className="btn btn-outline btn-sm" style={{ flexShrink: 0 }}>Open</Link>
              </div>
            );
          })}
        </div>
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
                {others.map((al, i) => {
                  const m = ALERT_META[al.type] || { icon: "•", bg: "#f3f4f6", bar: "var(--text-soft)" };
                  return (
                    <div key={i} className="flex" style={{ gap: 11, alignItems: "center", background: m.bg, borderLeft: `3px solid ${m.bar}`, borderRadius: 9, padding: "11px 13px" }}>
                      <span style={{ fontSize: 19, lineHeight: 1 }}>{m.icon}</span>
                      <span className="small" style={{ lineHeight: 1.4 }}>{al.text}</span>
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
