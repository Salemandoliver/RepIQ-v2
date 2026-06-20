import React, { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, Cell, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import api from "../api";
import { useToast } from "../components/Toast.jsx";
import { Skeleton, EmptyState, Modal } from "../components/ui.jsx";
import { formatDuration } from "../utils";
import { TrendingUpIcon } from "../components/Icons.jsx";
import CampaignsPanel from "../components/CampaignsPanel.jsx";

const RAG_COLOR = { green: "var(--green)", amber: "var(--amber)", red: "var(--red)", none: "var(--text-faint)" };
const ragOf = (pct) => (pct == null ? "none" : pct >= 80 ? "green" : pct >= 50 ? "amber" : "red");
const TONE_COLOR = { green: "var(--green)", amber: "var(--amber)", red: "var(--red)", zero: "var(--red)", none: "var(--text-faint)" };
const toneColor = (t) => TONE_COLOR[t] || "var(--text-faint)";

// Bold any known rep/BC name occurring in AI insight text so people stand out.
function highlightNames(text, names) {
  if (!text || !names?.length) return text;
  const esc = [...new Set(names.filter((n) => n && n.length >= 2))]
    .map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .sort((a, b) => b.length - a.length);
  if (!esc.length) return text;
  const re = new RegExp(`\\b(${esc.join("|")})\\b`, "g");
  const parts = [];
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(<strong key={m.index} className="siq-name">{m[0]}</strong>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function RefreshButton({ onDone }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return (
    <button className="btn btn-outline" disabled={busy} title="Reload the latest tracker data"
      onClick={async () => {
        setBusy(true);
        try { await api.post("/api/salesiq/refresh", {}); onDone(); toast("Data refreshed", "success"); }
        catch (e) { toast(e.message, "error"); } finally { setBusy(false); }
      }}>{busy ? "Refreshing…" : "↻ Refresh"}</button>
  );
}

function gbp(v) {
  if (v == null) return "—";
  const n = Math.round(v);
  if (Math.abs(n) >= 1000) return "£" + (n / 1000).toFixed(n % 1000 ? 1 : 0) + "k";
  return "£" + n.toLocaleString("en-GB");
}
const pctStr = (x) => (x == null ? "—" : `${Math.round(x)}%`);

function ProgressBar({ pct, color }) {
  return <div className="siq-bar"><div style={{ width: `${Math.min(100, pct || 0)}%`, background: color || "var(--accent)" }} /></div>;
}

function Tile({ label, value, sub, color }) {
  return (
    <div className="card siq-tile">
      <div className="siq-tile-label">{label}</div>
      <div className="siq-tile-value" style={color ? { color } : undefined}>{value}</div>
      {sub && <div className="siq-tile-sub">{sub}</div>}
    </div>
  );
}

function MetricTile({ label, mtd, target }) {
  const pct = target ? Math.round((mtd / target) * 100) : null;
  const color = RAG_COLOR[ragOf(pct)];
  return (
    <div className="card siq-tile">
      <div className="siq-tile-label">{label}</div>
      <div className="siq-tile-value" style={{ color }}>{gbp(mtd)}</div>
      <ProgressBar pct={pct} color={color} />
      <div className="siq-tile-sub">{target ? `of ${gbp(target)} · ${pctStr(pct)}` : "no target"}</div>
    </div>
  );
}

function RepPerformance({ p }) {
  const rag = RAG_COLOR[p.rag] || "var(--text)";
  return (
    <>
      <div className="siq-tiles">
        <div className="card siq-tile">
          <div className="siq-tile-label">Sales MTD (SOV)</div>
          <div className="siq-tile-value" style={{ color: rag }}>{gbp(p.sovMTD)}</div>
          <ProgressBar pct={p.sovPct} color={rag} />
          <div className="siq-tile-sub">{p.sovTarget ? `of ${gbp(p.sovTarget)} · ${pctStr(p.sovPct)}` : "no target"} · {p.daysRemaining}d left</div>
        </div>
        <Tile label="GM MTD" value={gbp(p.gmMTD)} sub={`${p.ordersMTD} orders placed`} />
        <Tile label="Run Rate (SOV)" value={p.runRate != null ? gbp(p.runRate) : "—"} sub="projected end of month" />
        <Tile label="Pending Orders" value={p.pendingCount} color={p.pendingCount ? "var(--amber)" : undefined}
          sub={p.pendingCount ? `${gbp(p.pendingValueSov)} SOV to chase` : "all placed"} />
      </div>
      <div className="siq-tiles" style={{ marginTop: 16 }}>
        <MetricTile label="Connectivity SOV" mtd={p.connectivity.mtd} target={p.connectivity.target} />
        <MetricTile label="Cloud SOV" mtd={p.cloud.mtd} target={p.cloud.target} />
        <MetricTile label="Mobile SOV" mtd={p.mobile.mtd} target={p.mobile.target} />
        <div className="card siq-tile">
          <div className="siq-tile-label">QTD / YTD (SOV)</div>
          <div className="siq-tile-value" style={{ fontSize: 19 }}>{gbp(p.qtd.sov)} <span className="siq-tile-sub">QTD</span></div>
          <div className="siq-tile-sub">{p.qtd.target ? `${pctStr(p.qtd.pct)} of ${gbp(p.qtd.target)}` : ""}</div>
          <div className="siq-tile-value" style={{ fontSize: 19, marginTop: 6 }}>{gbp(p.ytd.sov)} <span className="siq-tile-sub">YTD</span></div>
          <div className="siq-tile-sub">{p.ytd.target ? `${pctStr(p.ytd.pct)} of ${gbp(p.ytd.target)}` : ""}</div>
        </div>
      </div>
    </>
  );
}

function ManagerOverall({ overall }) {
  const Card = ({ title, d }) => {
    const color = RAG_COLOR[ragOf(d.pct)];
    return (
      <div className="card siq-tile">
        <div className="siq-tile-label">{title} · Team SOV</div>
        <div className="siq-tile-value" style={{ color }}>{gbp(d.sov)}</div>
        <ProgressBar pct={d.pct} color={color} />
        <div className="siq-tile-sub">{d.target ? `of ${gbp(d.target)} · ${pctStr(d.pct)}` : "no target"}{d.orders != null ? ` · ${d.orders} orders` : ""}</div>
      </div>
    );
  };
  return (
    <div className="siq-tiles" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
      <Card title="Month" d={overall.month} />
      <Card title="Quarter" d={overall.quarter} />
      <Card title="Year" d={overall.year} />
    </div>
  );
}

function OrdersTable({ weeks }) {
  if (!weeks || weeks.length === 0) {
    return <EmptyState icon="📋" title="No orders for this month" sub="Placed and pending orders will appear here." />;
  }
  return (
    <div className="siq-orders-wrap">
      <table className="siq-orders">
        <thead>
          <tr>
            <th>Company</th><th>Product</th><th>Split With</th><th className="num">Split %</th>
            <th className="num">GM</th><th className="num">Mobile</th><th className="num">Cloud</th>
            <th className="num">Conn.</th><th className="num">Other</th><th>Placed?</th>
          </tr>
        </thead>
        <tbody>
          {weeks.map((wk, wi) => (
            <React.Fragment key={wi}>
              {wk.orders.map((o, oi) => (
                <tr key={oi} className={o.placed ? "" : "siq-row-pending"}>
                  <td>{o.company}</td>
                  <td className="siq-prod">{o.product || "—"}</td>
                  <td>{o.splitWith || ""}</td>
                  <td className="num">{o.splitPct ?? ""}</td>
                  <td className="num">{gbp(o.gm)}</td>
                  <td className="num">{o.mobile ? gbp(o.mobile) : ""}</td>
                  <td className="num">{o.cloud ? gbp(o.cloud) : ""}</td>
                  <td className="num">{o.connectivity ? gbp(o.connectivity) : ""}</td>
                  <td className="num">{o.other ? gbp(o.other) : ""}</td>
                  <td>{o.placed ? <span className="siq-y">Y</span> : <span className="siq-n">N</span>}</td>
                </tr>
              ))}
              <tr className="siq-row-subtotal">
                <td colSpan={4}>{wk.week} subtotal</td>
                <td className="num">{gbp(wk.weekSubtotal.gm)}</td>
                <td className="num">{gbp(wk.weekSubtotal.mobile)}</td>
                <td className="num">{gbp(wk.weekSubtotal.cloud)}</td>
                <td className="num">{gbp(wk.weekSubtotal.connectivity)}</td>
                <td className="num">{gbp(wk.weekSubtotal.other)}</td>
                <td />
              </tr>
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ActivityTile({ label, value, pct, sub }) {
  const color = pct != null ? RAG_COLOR[ragOf(pct)] : undefined;
  return (
    <div className="card siq-tile">
      <div className="siq-tile-label">{label}</div>
      <div className="siq-tile-value" style={color ? { color } : undefined}>{value}</div>
      {pct != null && <ProgressBar pct={pct} color={color} />}
      {sub && <div className="siq-tile-sub">{sub}</div>}
    </div>
  );
}

function LeadIntel({ leads }) {
  const b = leads.statusBreakdown || {};
  const pieces = [["Won", b.won, "var(--green)"], ["In Progress", b.inProgress, "var(--amber)"],
    ["Rejected", b.rejected, "var(--red)"], ["Not Contacted", b.notContacted, "var(--text-faint)"]];
  return (
    <div>
      <div style={{ fontSize: 22, fontWeight: 800 }}>
        {leads.totalReceived} <span className="siq-tile-sub" style={{ fontWeight: 400 }}>leads received MTD</span>
      </div>
      <div className="flex" style={{ flexWrap: "wrap", gap: 12, margin: "10px 0 4px" }}>
        {pieces.map(([l, n, c]) => (
          <span key={l} className="flex" style={{ gap: 5, fontSize: 12.5 }}>
            <span className="dot" style={{ background: c, width: 8, height: 8 }} /> {l}: <strong>{n || 0}</strong>
          </span>
        ))}
      </div>
      {leads.byBC?.length > 0 && (
        <>
          <div className="small muted" style={{ margin: "10px 0 4px" }}>By Business Creator</div>
          {leads.byBC.map((bc, i) => (
            <div key={i} className="spread small" style={{ padding: "5px 8px", borderRadius: 6, background: i % 2 === 0 ? "rgba(0,0,0,0.035)" : "transparent" }}>
              <span style={{ fontWeight: 600 }}>{bc.bcName}</span>
              <span className="muted">
                {bc.count} lead{bc.count === 1 ? "" : "s"}
                {bc.won > 0 && <> · <strong style={{ color: "var(--green)" }}>{bc.won} won</strong>
                  <span className="faint"> ({Math.round((bc.won / bc.count) * 100)}%)</span></>}
              </span>
            </div>
          ))}
        </>
      )}
      {leads.leads?.length > 0 && (
        <div style={{ overflowX: "auto", marginTop: 10 }}>
          <table className="data">
            <thead><tr><th>Company</th><th>BC</th><th>Date</th><th>Status</th></tr></thead>
            <tbody>
              {leads.leads.slice(0, 12).map((l, i) => {
                const won = (l.status || "").toLowerCase().includes("won");
                const rej = /reject|lost|declin/.test((l.status || "").toLowerCase());
                const col = won ? "var(--green)" : rej ? "var(--red)" : "var(--amber)";
                return (
                  <tr key={i} style={won ? { background: "rgba(16,185,129,0.08)" } : undefined}>
                    <td>{l.company}</td><td>{l.bc || ""}</td>
                    <td>{l.date ? l.date.slice(0, 10) : ""}</td>
                    <td><span style={{ color: col, fontWeight: won ? 700 : 500 }}>{l.status || ""}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Activity({ a, opps }) {
  if (!a?.connected) return <div className="ciq-faint">Activity unavailable.</div>;
  const pct = (x) => `${Math.round((x || 0) * 100)}%`;
  return (
    <div className="siq-tiles">
      {opps?.connected && (
        <ActivityTile label="Opps Created (MTD)" value={opps.oppsMTD} pct={opps.pct}
          sub={`target ${opps.target} (${opps.perDayTarget}/day × ${opps.workingDays} days)`} />
      )}
      <ActivityTile label="Dials Today" value={a.dialsToday} pct={a.dialsTodayPct}
        sub={`target ${a.dialsTarget}/day · ${a.dialsMTD} MTD`} />
      <ActivityTile label="Talk Today" value={formatDuration(a.talkTimeTodaySec)} pct={a.talkTodayPct}
        sub={`target ${Math.round(a.talkTargetSec / 60)}m/day`} />
      <ActivityTile label="Avg Dials / Day" value={a.avgDialsPerDay} pct={a.avgDialsPct} sub={`target ${a.dialsTarget}`} />
      <ActivityTile label="Avg Talk / Day" value={formatDuration(a.avgTalkPerDaySec)} pct={a.avgTalkPct}
        sub={`target ${Math.round(a.talkTargetSec / 60)}m`} />
      <Tile label="Dial → Conversation" value={pct(a.dialToConvRate)} sub={`${a.conversationsMTD} conversations MTD`} />
      <Tile label="Conversation → Order" value={pct(a.convToOrderRate)} sub="closing rate" />
    </div>
  );
}

// ============================================================ Business Creator view
function BcContent({ data }) {
  const p = data.performance;
  const trend = data.trend || [];
  const a = data.activity;
  return (
    <>
      <div className="siq-tiles">
        <Tile label="Leads Generated" value={p.leadsMTD} sub={`of ${p.leadTarget} target · ${pctStr(p.leadPct)}`}
          color={p.leadsMTD >= p.leadTarget ? "var(--green)" : p.leadPct >= 40 ? "var(--amber)" : "var(--red)"} />
        <Tile label="GM Generated" value={gbp(p.gmGenerated)} sub="from sourced deals" color="var(--green)" />
        <Tile label="F2F Meetings" value={p.f2f} sub={`of ${p.f2fTarget} · ${pctStr(p.f2fPct)}`} />
        <Tile label="Won" value={p.won} sub={`${pctStr(p.wonPct)} of leads`} color="var(--green)" />
        <Tile label="Rejected" value={p.rejected} />
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <h2 className="card-title">Leads &amp; Wins — Last 6 Months</h2>
        <div style={{ width: "100%", height: 190 }}>
          <ResponsiveContainer>
            <BarChart data={trend} margin={{ left: 0, right: 8, top: 8, bottom: 4 }}>
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--text-soft)" }} />
              <YAxis tick={{ fontSize: 11, fill: "var(--text-soft)" }} width={28} />
              <Tooltip cursor={{ fill: "rgba(0,0,0,0.04)" }} />
              <Bar dataKey="leads" name="Leads" fill="var(--accent)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="won" name="Won" fill="var(--green)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {a?.connected && (
        <div className="card" style={{ marginTop: 20 }}>
          <h2 className="card-title">My Activity</h2>
          <div className="siq-tiles">
            <Tile label="Dials Today" value={(a.dialsToday || 0).toLocaleString("en-GB")} />
            <Tile label="Talk Time Today" value={formatDuration(a.talkSecToday || 0)} />
            <Tile label="Leads Logged (MTD)" value={a.leadsLogged} />
          </div>
        </div>
      )}

      <div className="siq-grid2" style={{ marginTop: 20 }}>
        <div className="card">
          <h2 className="card-title">Where My Leads Go</h2>
          {data.byReceiver?.length > 0 ? (
            <div style={{ overflowX: "auto" }}>
              <table className="data siq-perf">
                <thead><tr><th>Sales Rep</th><th>Leads</th><th>Won</th><th>Conv %</th></tr></thead>
                <tbody>
                  {data.byReceiver.map((r) => (
                    <tr key={r.rep}>
                      <td>{r.rep}</td>
                      <td style={{ textAlign: "right" }}>{r.count}</td>
                      <td style={{ textAlign: "right" }}>{r.won}</td>
                      <PctCell v={r.convRate != null ? Math.round(r.convRate * 100) : null} />
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="ciq-faint">No leads this month.</div>}
        </div>
        <div className="card">
          <h2 className="card-title">Recent Leads</h2>
          {data.leads?.length > 0 ? (
            <div style={{ overflowX: "auto", maxHeight: 320, overflowY: "auto" }}>
              <table className="data siq-perf">
                <thead><tr><th>Company</th><th>Rep</th><th>Type</th><th>Status</th></tr></thead>
                <tbody>
                  {data.leads.slice(0, 30).map((l, i) => (
                    <tr key={i}><td>{l.company}</td><td>{l.rep || ""}</td><td>{l.leadType || ""}</td><td>{l.status || ""}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="ciq-faint">No leads.</div>}
        </div>
      </div>
    </>
  );
}

// ============================================================ Manager view
function KpiStrip({ k }) {
  const offPace = (k.repsOffPace || 0) > 0;
  const items = [
    ["Team GM", gbp(k.teamGm), "var(--green)", "💷"],
    ["Calls This Week", (k.callsThisWeek || 0).toLocaleString("en-GB"), "var(--accent)", "📞"],
    ["BC Leads", k.bcLeads || 0, "#3b82f6", "🤝"],
    ["Reps Off Pace", `${k.repsOffPace || 0} / ${k.repCount || 0}`, offPace ? "var(--red)" : "var(--green)", offPace ? "⚠️" : "✅"],
  ];
  return (
    <div className="siq-kpis">
      {items.map(([l, v, c, icon]) => (
        <div key={l} className="siq-kpi" style={{ borderLeft: `4px solid ${c}` }}>
          <div className="siq-kpi-top"><span className="siq-kpi-ico">{icon}</span><span className="siq-kpi-lbl">{l}</span></div>
          <div className="siq-kpi-val" style={{ color: c }}>{v}</div>
        </div>
      ))}
    </div>
  );
}

function StatusPill({ s }) {
  return <span className="siq-pill" style={{ color: toneColor(s.tone), borderColor: toneColor(s.tone), background: `color-mix(in srgb, ${toneColor(s.tone)} 10%, transparent)` }}>{s.icon} {s.label}</span>;
}

// Heat-tinted percentage cell — green→amber→red wash for instant scanning.
function HeatCell({ v, bold }) {
  const c = v == null ? "var(--text-faint)" : v >= 100 ? "var(--green)" : v >= 70 ? "#65a30d" : v >= 40 ? "var(--amber)" : "var(--red)";
  const bg = v == null ? "transparent" : `color-mix(in srgb, ${c} 14%, transparent)`;
  return <td style={{ textAlign: "right", fontWeight: bold ? 800 : 600, color: c, background: bg }}>{pctStr(v)}</td>;
}

function PctCell({ v }) {
  return <td style={{ textAlign: "right", color: v == null ? "var(--text-faint)" : v >= 100 ? "var(--green)" : v >= 50 ? "var(--text)" : "var(--red)" }}>{pctStr(v)}</td>;
}

function PillarBar({ label, pct, color }) {
  return (
    <div className="siq-pillar">
      <span className="siq-pillar-lbl">{label}</span>
      <div className="siq-pillar-track"><div style={{ width: `${Math.min(100, pct || 0)}%`, background: color }} /></div>
      <span className="siq-pillar-pct">{pctStr(pct)}</span>
    </div>
  );
}

function RepDetail({ r, onOpen }) {
  return (
    <td colSpan={7} className="siq-detail">
      <div className="siq-detail-grid">
        <div style={{ flex: 1, minWidth: 220 }}>
          <PillarBar label="Connectivity" pct={r.dataPct} color="var(--accent)" />
          <PillarBar label="Cloud" pct={r.cloudPct} color="#3b82f6" />
          <PillarBar label="Mobile" pct={r.mobilePct} color="#8b5cf6" />
        </div>
        <div className="siq-detail-stats">
          <div><span className="muted">SOV</span><strong>{gbp(r.sov)}</strong></div>
          <div><span className="muted">GM</span><strong>{gbp(r.gm)}</strong></div>
          <div><span className="muted">Weighted</span><strong>{pctStr(r.weightedPct)}</strong></div>
          <div><StatusPill s={r.status} /></div>
          {onOpen && r.userId != null && (
            <button className="btn btn-primary" onClick={() => onOpen(r.userId, r.rep)}>View full dashboard →</button>
          )}
        </div>
      </div>
    </td>
  );
}

function PerformanceSection({ perf, pace, onOpenRep }) {
  const [open, setOpen] = useState({});
  const reps = perf.groups.flatMap((g) => g.reps);
  const chart = reps.map((r) => ({ name: r.rep.split(" ")[0], gm: r.gm, tone: r.status.tone })).sort((a, b) => b.gm - a.gm);
  if (reps.length === 0) return null;
  return (
    <div className="card" style={{ marginTop: 18 }}>
      <h2 className="card-title">① Sales Performance vs Target</h2>
      {pace && <div className="siq-note">⚡ {pace}</div>}
      {chart.length > 0 && (
        <div style={{ width: "100%", height: Math.max(140, chart.length * 26) }}>
          <ResponsiveContainer>
            <BarChart data={chart} layout="vertical" margin={{ left: 8, right: 28, top: 4, bottom: 4 }}>
              <XAxis type="number" tickFormatter={gbp} tick={{ fontSize: 11, fill: "var(--text-soft)" }} />
              <YAxis type="category" dataKey="name" width={88} interval={0} tick={{ fontSize: 11, fill: "var(--text-soft)" }} />
              <Tooltip formatter={(v) => gbp(v)} cursor={{ fill: "rgba(0,0,0,0.04)" }} />
              <Bar dataKey="gm" radius={[0, 4, 4, 0]}>
                {chart.map((c, i) => <Cell key={i} fill={toneColor(c.tone)} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="muted small" style={{ margin: "2px 0 8px" }}>Tap a rep for the pillar breakdown ↓</div>
      {perf.groups.map((g) => (
        <div key={g.team} style={{ marginTop: 14 }}>
          <div className="siq-group-hd"><span>{g.team}</span><span className="muted">GM {gbp(g.gm)}</span></div>
          <div style={{ overflowX: "auto" }}>
            <table className="data siq-perf">
              <thead><tr><th>Rep</th><th>Data</th><th>Cloud</th><th>Mobile</th><th>Weighted</th><th>GM</th><th>Status</th></tr></thead>
              <tbody>
                {g.reps.map((r) => {
                  const key = r.rep;
                  const isOpen = !!open[key];
                  return (
                    <React.Fragment key={key}>
                      <tr className="siq-rep-row" onClick={() => setOpen((o) => ({ ...o, [key]: !o[key] }))}>
                        <td>{isOpen ? "▾" : "▸"} {r.rep}</td>
                        <HeatCell v={r.dataPct} /><HeatCell v={r.cloudPct} /><HeatCell v={r.mobilePct} />
                        <HeatCell v={r.weightedPct} bold />
                        <td style={{ textAlign: "right" }}>{gbp(r.gm)}</td>
                        <td><StatusPill s={r.status} /></td>
                      </tr>
                      {isOpen && <tr className="siq-detail-row"><RepDetail r={r} onOpen={onOpenRep} /></tr>}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

function MiniBar({ pct }) {
  const w = Math.min(100, pct || 0);
  return <div className="siq-mini"><div style={{ width: `${w}%`, background: pct >= 80 ? "var(--green)" : pct >= 40 ? "var(--amber)" : "var(--red)" }} /></div>;
}

function BcSection({ rows }) {
  if (!rows?.length) return null;
  return (
    <div className="card" style={{ marginTop: 18 }}>
      <h2 className="card-title">② BC Lead Conversion</h2>
      <div style={{ overflowX: "auto" }}>
        <table className="data siq-perf">
          <thead><tr><th>Business Creator</th><th>Leads</th><th>vs Target</th><th>F2F</th><th>F2F %</th><th>Won</th><th>Won %</th><th>GM</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.bc}>
                <td>{r.bc}</td>
                <td style={{ textAlign: "right" }}>{r.leads}<span className="muted" style={{ fontSize: 11 }}> / {r.leadTarget}</span></td>
                <td style={{ minWidth: 90 }}><MiniBar pct={r.leadPct} /></td>
                <td style={{ textAlign: "right" }}>{r.f2f}<span className="muted" style={{ fontSize: 11 }}> / {r.f2fTarget}</span></td>
                <PctCell v={r.f2fPct} />
                <td style={{ textAlign: "right" }}>{r.won}</td>
                <PctCell v={r.wonPct} />
                <td style={{ textAlign: "right", fontWeight: 700, color: r.gm > 0 ? "var(--green)" : "var(--text-faint)" }}>{gbp(r.gm)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ActivitySection({ a }) {
  const daily = (a.daily || []).map((d) => ({ name: d.label.replace(/ \d{4}$/, ""), calls: d.calls, talk: d.talkMins }));
  return (
    <div className="card" style={{ marginTop: 18 }}>
      <h2 className="card-title">③ Activity — Dials &amp; Talk Time</h2>
      {daily.length > 0 && (
        <>
          <div className="muted small" style={{ marginBottom: 4 }}>This week — team calls per day (avg {a.avgCallsPerDay}/day)</div>
          <div style={{ width: "100%", height: 150 }}>
            <ResponsiveContainer>
              <BarChart data={daily} margin={{ left: 0, right: 8, top: 8, bottom: 4 }}>
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "var(--text-soft)" }} />
                <YAxis tick={{ fontSize: 11, fill: "var(--text-soft)" }} width={32} />
                <Tooltip cursor={{ fill: "rgba(0,0,0,0.04)" }} />
                <ReferenceLine y={a.avgCallsPerDay} stroke="var(--text-faint)" strokeDasharray="3 3" />
                <Bar dataKey="calls" fill="var(--accent)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
      {a.reps?.length > 0 && (
        <div style={{ overflowX: "auto", marginTop: 10 }}>
          <table className="data siq-perf">
            <thead><tr><th>Rep</th><th>Days</th><th>Dials/Day</th><th>Min/Day</th><th>Opps/Day</th><th>Profile</th></tr></thead>
            <tbody>
              {a.reps.map((r) => (
                <tr key={r.agent}>
                  <td>{r.agent}</td>
                  <td style={{ textAlign: "right" }}>{r.days}</td>
                  <td style={{ textAlign: "right" }}>{r.dialsPerDay}</td>
                  <td style={{ textAlign: "right", color: r.minsPerDay >= 90 ? "var(--green)" : "var(--text)" }}>{r.minsPerDay}</td>
                  <td style={{ textAlign: "right", color: r.oppsPerDay >= 2 ? "var(--green)" : "var(--text)" }}>{r.oppsPerDay}</td>
                  <td><span className="siq-chip">{r.profile}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function leaveIcon(code, weekend) {
  if (code) {
    const c = String(code).toUpperCase();
    if (c === "H") return { ico: "🌴", t: "Holiday" };
    if (c === "H1" || c === "H2" || c === "HD") return { ico: "🏖️", t: "Half day" };
    if (c[0] === "S") return { ico: "🤒", t: "Sick" };
    if (c === "B" || c === "BH") return { ico: "·", t: "Bank holiday", muted: true };
    if (c === "C") return { ico: "🕊️", t: "Compassionate" };
    return { ico: "📋", t: "Leave" };
  }
  if (weekend) return { ico: "·", t: "Weekend", muted: true };
  return { ico: "🧍", t: "Working", work: true };
}

const HOL_LEGEND = [["🧍", "Working"], ["🌴", "Holiday"], ["🏖️", "Half day"], ["🤒", "Sick"], ["📋", "Other leave"], ["·", "Weekend / bank holiday"]];

function HolidayCalendarModal({ onClose }) {
  const toast = useToast();
  const now = new Date();
  const [ym, setYm] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const [team, setTeam] = useState("all");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/salesiq/holiday-calendar?ym=${ym}&team=${encodeURIComponent(team)}`)
      .then(setData).catch((e) => { toast(e.message, "error"); setData(null); })
      .finally(() => setLoading(false));
  }, [ym, team]);

  const shift = (delta) => {
    let [y, m] = ym.split("-").map(Number);
    m += delta;
    if (m < 1) { y -= 1; m = 12; }
    if (m > 12) { y += 1; m = 1; }
    setYm(`${y}-${String(m).padStart(2, "0")}`);
  };
  const [yy, mm] = ym.split("-").map(Number);
  const label = new Date(yy, mm - 1, 1).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  const todayDay = (yy === now.getFullYear() && mm === now.getMonth() + 1) ? now.getDate() : null;
  const teamOpts = [["all", "All Teams"], ...((data?.teamsAvailable) || []).map((tn) => [tn.toLowerCase(), tn])];

  return (
    <Modal wide title="🗓️ Holiday Calendar" onClose={onClose}>
      <div className="spread" style={{ marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
        <div className="flex" style={{ gap: 12 }}>
          <button className="btn btn-outline" onClick={() => shift(-1)} aria-label="Previous month">‹</button>
          <strong style={{ fontSize: 16, minWidth: 140, textAlign: "center" }}>{label}</strong>
          <button className="btn btn-outline" onClick={() => shift(1)} aria-label="Next month">›</button>
        </div>
        <select className="input siq-team-sel" value={team} onChange={(e) => setTeam(e.target.value)}>
          {teamOpts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      {loading ? (
        <Skeleton h={320} style={{ borderRadius: 10 }} />
      ) : !data?.found ? (
        <EmptyState icon="🗓️" title="No holiday data for this month" />
      ) : (
        <>
          <div className="hol-cal-wrap">
            <table className="hol-cal">
              <thead>
                <tr>
                  <th className="hol-corner">Employee</th>
                  {data.days.map((d) => (
                    <th key={d.day} className={(d.weekend ? "we" : "") + (todayDay === d.day ? " today" : "")} title={d.weekday}>
                      <div className="hol-dnum">{d.day}</div>
                      <div className="hol-dwk">{d.weekday[0]}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.people.map((p) => (
                  <tr key={p.name}>
                    <td className="hol-name">{p.name}</td>
                    {data.days.map((d) => {
                      const m = leaveIcon(p.cells[d.day], d.weekend);
                      return (
                        <td key={d.day} title={`${p.name} · ${d.day} ${d.weekday} · ${m.t}`}
                          className={"hol-c" + (m.muted ? " mut" : "") + (d.weekend ? " we" : "") + (todayDay === d.day ? " today" : "")}>
                          {m.ico}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="hol-legend">
            {HOL_LEGEND.map(([ico, t]) => <span key={t}><span className="hol-leg-ico">{ico}</span> {t}</span>)}
          </div>
        </>
      )}
    </Modal>
  );
}

function HolidaySection({ h }) {
  const [calOpen, setCalOpen] = useState(false);
  if (!h?.connected) return null;
  return (
    <div className="card" style={{ marginTop: 18 }}>
      <div className="spread">
        <h2 className="card-title">④ Holiday Coverage — Next Week ({h.span})</h2>
        <button className="btn btn-outline" onClick={() => setCalOpen(true)}>🗓️ View full calendar</button>
      </div>
      <div className="siq-note" style={h.count ? {} : { background: "rgba(16,185,129,0.08)", borderColor: "rgba(16,185,129,0.3)", color: "var(--green)" }}>
        {h.count ? "🌴" : "✅"} {h.note}
      </div>
      {calOpen && <HolidayCalendarModal onClose={() => setCalOpen(false)} />}
      {h.people?.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table className="data siq-perf">
            <thead><tr><th>Name</th><th>Absence</th><th>Date(s)</th><th>Impact</th></tr></thead>
            <tbody>
              {h.people.map((p) => (
                <tr key={p.name}>
                  <td>{p.name}</td>
                  <td><span className="siq-chip">{p.absence}</span></td>
                  <td className="muted">{p.dates}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{p.impact}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function IntelligenceSection({ intel, names }) {
  if (!intel) return null;
  const c = intel.coaching;
  return (
    <div className="siq-grid2" style={{ marginTop: 18 }}>
      <div className="card">
        <h2 className="card-title">⑤ Key Insights {intel.source === "ai" ? "✨" : ""}</h2>
        <ul className="siq-insights">
          {(intel.insights || []).map((t, i) => <li key={i}>{highlightNames(t, names)}</li>)}
        </ul>
      </div>
      <div className="card">
        <h2 className="card-title">🎯 Coaching Spotlight</h2>
        {c ? (
          <div>
            <div className="siq-coach-name">{c.rep} <span className="muted">· {c.role}</span></div>
            <p style={{ margin: "8px 0", color: "var(--text-soft)" }}>{highlightNames(c.diagnosis, names)}</p>
            <ul className="siq-insights">{(c.interventions || []).map((t, i) => <li key={i}>{highlightNames(t, names)}</li>)}</ul>
          </div>
        ) : <div className="ciq-faint">No coaching pick this period.</div>}
      </div>
    </div>
  );
}

const PERIODS = [["week", "Week"], ["month", "Month"], ["quarter", "Quarter"]];

const TEAM_LABEL = (t) => (t === "all" ? "All Teams" : t === "business creators" ? "Business Creators" : t.replace(/\b\w/g, (m) => m.toUpperCase()) + (/(team|creators|bdm)$/i.test(t) ? "" : " Team"));

function ManagerView({ name }) {
  const toast = useToast();
  const [period, setPeriod] = useState("month");
  const [team, setTeam] = useState("all");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drillRep, setDrillRep] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/salesiq/manager?period=${period}&team=${encodeURIComponent(team)}`)
      .then(setData).catch((e) => { toast(e.message, "error"); setData(null); })
      .finally(() => setLoading(false));
  }, [period, team, reloadKey]);

  if (drillRep) return <RepDrilldown userId={drillRep.userId} name={drillRep.name} onBack={() => setDrillRep(null)} />;

  const meta = data?.meta;
  const teamOptions = ["all", ...((meta?.teamsAvailable || []).map((t) => t.toLowerCase())), "business creators"];
  const names = data ? [
    ...(data.performance?.groups || []).flatMap((g) => g.reps).flatMap((r) => [r.rep, r.rep.split(" ")[0]]),
    ...(data.bcConversion || []).map((r) => r.bc),
    ...(data.activity?.reps || []).map((r) => r.agent),
  ] : [];
  return (
    <div className="page">
      <div className="spread" style={{ marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
        <div>
          <h1 className="page-title"><span className="flex"><TrendingUpIcon size={22} /> Team Intelligence</span></h1>
          <p className="page-sub">{meta ? `${meta.periodLabel} · ${meta.financialQuarter} · ${meta.elapsedPct}% elapsed` : "Live team performance digest"}</p>
        </div>
        <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
          <div className="siq-seg">
            {PERIODS.map(([v, l]) => (
              <button key={v} className={`siq-seg-btn${period === v ? " on" : ""}`} onClick={() => setPeriod(v)}>{l}</button>
            ))}
          </div>
          <select className="input siq-team-sel" value={team} onChange={(e) => setTeam(e.target.value)}>
            {teamOptions.map((t) => <option key={t} value={t}>{TEAM_LABEL(t)}</option>)}
          </select>
          <RefreshButton onDone={() => setReloadKey((k) => k + 1)} />
        </div>
      </div>

      {loading ? (
        <div className="siq-tiles">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} h={90} style={{ borderRadius: 10 }} />)}</div>
      ) : !data ? (
        <div className="card"><EmptyState icon="📊" title="Couldn't load the digest" sub="Try again shortly." /></div>
      ) : (
        <>
          <KpiStrip k={data.kpis} />
          {meta.salesConfigured ? <PerformanceSection perf={data.performance} pace={data.intelligence?.paceNote} onOpenRep={(userId, rep) => setDrillRep({ userId, name: rep })} />
            : <div className="card" style={{ marginTop: 18 }}><EmptyState icon="🔌" title="Sales Tracker not connected" /></div>}
          {meta.leadsConfigured && <BcSection rows={data.bcConversion} />}
          {meta.activityConfigured && <ActivitySection a={data.activity} />}
          {meta.holidayConfigured && <HolidaySection h={data.holiday} />}
          <CampaignsPanel />
          <IntelligenceSection intel={data.intelligence} names={names} />
          <p className="muted small" style={{ marginTop: 14, textAlign: "center" }}>
            Generated {meta.computedAt ? new Date(meta.computedAt).toLocaleString("en-GB") : ""} · Data: Sales Tracker · Activity Tracker · Lead Tracker · RepIQ
          </p>
        </>
      )}
    </div>
  );
}

// Rep dashboard body — reused by the rep's own page and the manager drill-through.
function RepBody({ data }) {
  const meta = data.meta;
  return (
    <>
      {data.overall ? <ManagerOverall overall={data.overall} /> : <RepPerformance p={data.performance} />}

      <div className="card" style={{ marginTop: 20 }}>
        <div className="spread" style={{ marginBottom: 8 }}>
          <h2 className="card-title" style={{ margin: 0 }}>Monthly Orders · {meta.salesMonthLabel}</h2>
        </div>
        <OrdersTable weeks={data.monthlyOrders} />
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <h2 className="card-title">Activity{data.opps?.connected ? "" : " (from RepIQ calls)"}</h2>
        <Activity a={data.activity} opps={data.opps} />
      </div>

      <div className="siq-grid2" style={{ marginTop: 20 }}>
        <div className="card">
          <h2 className="card-title">Lead Intelligence</h2>
          {data.leads?.connected ? <LeadIntel leads={data.leads} /> : (
            <EmptyState icon="🤝" title="Lead Tracker not connected"
              sub="Share the BTLB Lead Tracker link to surface leads, status and BC attribution." />
          )}
        </div>
        <div className="card">
          <h2 className="card-title">Field Activity</h2>
          {data.opps?.connected ? (
            <div className="siq-tiles" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <Tile label="Opps Created (MTD)" value={data.opps.oppsMTD} sub={`of ${data.opps.target} target`} />
              <Tile label="F2F Visits (MTD)" value={data.opps.f2fMTD ?? 0} />
            </div>
          ) : (
            <EmptyState icon="🚗" title="Activity Tracker not connected"
              sub="Share the LB Activity Tracker link to add F2F visits and opps created." />
          )}
        </div>
      </div>
    </>
  );
}

// Manager drill-through into one rep's full dashboard (fetches ?user_id=).
function RepDrilldown({ userId, name, onBack }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [month, setMonth] = useState(null);
  useEffect(() => {
    setLoading(true);
    const q = `?user_id=${userId}` + (month ? `&month=${month}` : "");
    api.get(`/api/salesiq/dashboard${q}`)
      .then(setData).catch((e) => { toast(e.message, "error"); setData(null); })
      .finally(() => setLoading(false));
  }, [userId, month]);
  const meta = data?.meta;
  return (
    <div className="page">
      <div className="spread" style={{ marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
        <div>
          <button className="btn btn-ghost" onClick={onBack} style={{ marginBottom: 6, paddingLeft: 0 }}>← Back to team</button>
          <h1 className="page-title"><span className="flex"><TrendingUpIcon size={22} /> {meta?.name || name}</span></h1>
          <p className="page-sub">{meta ? `${meta.periodLabel} · ${meta.financialQuarter}` : "Loading…"}</p>
        </div>
        {meta?.availableMonths?.length > 0 && (
          <label className="field" style={{ margin: 0 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-soft)" }}>Viewing month</span>
            <select className="input" value={meta.selectedMonth} onChange={(e) => setMonth(e.target.value)}>
              {meta.availableMonths.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          </label>
        )}
      </div>
      {loading ? (
        <div className="siq-tiles">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} h={110} style={{ borderRadius: 10 }} />)}</div>
      ) : !data ? (
        <div className="card"><EmptyState icon="📊" title="Couldn't load dashboard" /></div>
      ) : !meta.salesConfigured ? (
        <div className="card"><EmptyState icon="🔌" title="Sales Tracker not connected" /></div>
      ) : <RepBody data={data} />}
    </div>
  );
}

export default function SalesIQ() {
  const { user } = useOutletContext();
  const toast = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [month, setMonth] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    const q = month ? `?period=mtd&month=${month}` : "?period=mtd";
    api.get(`/api/salesiq/dashboard${q}`)
      .then((d) => setData(d))
      .catch((e) => { toast(e.message, "error"); setData(null); })
      .finally(() => setLoading(false));
  }, [month, reloadKey]);

  const meta = data?.meta;
  const isManager = meta?.role === "manager";
  const isBc = meta?.role === "bc";

  if (isManager) return <ManagerView name={meta.name} />;

  if (meta && meta.access === false) {
    return (
      <div className="page">
        <h1 className="page-title"><span className="flex"><TrendingUpIcon size={22} /> SalesIQ</span></h1>
        <div className="card" style={{ marginTop: 16 }}>
          <EmptyState icon="🔒" title="SalesIQ isn't available for your role"
            sub={meta.reason || "Only sales and management roles have a SalesIQ dashboard."} />
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="spread" style={{ marginBottom: 14, flexWrap: "wrap" }}>
        <div>
          <h1 className="page-title"><span className="flex"><TrendingUpIcon size={22} /> SalesIQ</span></h1>
          <p className="page-sub">
            {meta ? `${meta.name} · ${meta.periodLabel} · ${meta.financialQuarter}` : "Your live sales performance"}
          </p>
        </div>
        <div className="flex" style={{ gap: 10, alignItems: "flex-end" }}>
          {meta?.availableMonths?.length > 0 && (
            <label className="field" style={{ margin: 0 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-soft)" }}>Viewing month</span>
              <select className="input" value={meta.selectedMonth} onChange={(e) => setMonth(e.target.value)}>
                {meta.availableMonths.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </label>
          )}
          <RefreshButton onDone={() => setReloadKey((k) => k + 1)} />
        </div>
      </div>

      {loading ? (
        <div className="siq-tiles">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} h={110} style={{ borderRadius: 10 }} />)}</div>
      ) : !data ? (
        <div className="card"><EmptyState icon="📊" title="Couldn't load SalesIQ" sub="Try again shortly." /></div>
      ) : isBc ? (
        <BcContent data={data} />
      ) : !meta.salesConfigured ? (
        <div className="card"><EmptyState icon="🔌" title="Sales Tracker not connected" /></div>
      ) : (
        <RepBody data={data} />
      )}
    </div>
  );
}
