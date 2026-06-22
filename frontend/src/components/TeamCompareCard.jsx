import React from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid } from "recharts";
import { useCachedGet } from "../useCachedGet.js";

// "You vs the team" — call quality over time against the team average, plus rank.
// A gentle, evidence-based nudge to improve and compete. (Roadmap Phase 0/1.) Cached across nav.

// Lightweight hover tooltip — a dotted-underline number with a brief that explains the metric,
// what's good, and who's currently top. No new deps; scoped CSS injected once below.
function Tip({ children, brief }) {
  if (!brief) return children;
  return (
    <span className="tc-tip" tabIndex={0}>
      {children}
      <span className="tc-bubble" role="tooltip">{brief}</span>
    </span>
  );
}

const tipCss = `
.tc-tip { position: relative; cursor: help; outline: none; }
.tc-tip > :first-child { border-bottom: 1px dotted var(--text-soft); }
.tc-bubble {
  position: absolute; left: 50%; top: calc(100% + 8px); transform: translateX(-50%) translateY(-4px);
  width: 244px; background: #1f2430; color: #fff; border-radius: 8px; padding: 9px 11px;
  font-size: 12px; font-weight: 400; line-height: 1.45; text-align: left; letter-spacing: 0;
  box-shadow: 0 8px 24px rgba(0,0,0,.22); opacity: 0; visibility: hidden; transition: .12s ease;
  z-index: 40; pointer-events: none;
}
.tc-bubble::before {
  content: ""; position: absolute; left: 50%; top: -5px; transform: translateX(-50%);
  border-left: 6px solid transparent; border-right: 6px solid transparent; border-bottom: 6px solid #1f2430;
}
.tc-tip:hover .tc-bubble, .tc-tip:focus .tc-bubble { opacity: 1; visibility: visible; transform: translateX(-50%) translateY(0); }
`;

export default function TeamCompareCard({ userId, title = "You vs the team" }) {
  const { data, error: err } = useCachedGet(`/api/intelligence/benchmarks${userId ? `?user_id=${userId}` : ""}`);

  if (err) return null;
  if (!data) return <div className="card"><div className="skeleton" style={{ height: 180 }} /></div>;

  const chart = (data.repSeries || []).map((p, i) => ({
    label: p.label,
    you: p.quality,
    team: data.teamSeries?.[i]?.quality ?? null,
  }));
  const hasData = chart.some((p) => p.you != null || p.team != null);
  const wk = data.weeks;

  const leaderTxt = (l) => {
    if (!l || l.name == null) return "";
    return l.isMe ? " That's you — you're top of the team." : ` Top right now: ${l.name} (${l.value}).`;
  };

  const qualityBrief = data.qualityRank
    ? `Where your average call-quality score ranks among the ${data.qualityRank.of} people who took calls in the last ${wk} weeks — you're ${data.qualityRank.label}` +
      `${data.qualityRank.percentile != null ? ` (top ${100 - data.qualityRank.percentile}%)` : ""}.` +
      ` Quality is a 0–100 score blending talk-ratio, questions asked, discovery and other call signals.${leaderTxt(data.qualityLeader)}`
    : null;

  const ordersBrief = data.ordersRank
    ? `Your rank by number of orders placed on calls in the last ${wk} weeks — you're ${data.ordersRank.label}` +
      `${data.ordersRank.percentile != null ? ` (top ${100 - data.ordersRank.percentile}%)` : ""}.` +
      ` You've logged ${data.myOrders} (team average ${data.teamOrdersAvg}).${leaderTxt(data.ordersLeader)}`
    : null;

  const qualityNumBrief =
    `Your average call-quality score (0–100) over the last ${wk} weeks. ` +
    `The team average is ${data.teamQuality ?? "—"} — higher is better, and being above the team line means your calls are scoring better than the typical rep.`;

  const Rank = ({ label, r, brief }) => {
    if (!r) return null;
    const tone = r.percentile >= 67 ? "var(--green)" : r.percentile >= 34 ? "var(--amber)" : "var(--text-soft)";
    return (
      <div style={{ textAlign: "center" }}>
        <Tip brief={brief}>
          <div style={{ fontSize: 22, fontWeight: 700, color: tone }}>{r.label}</div>
        </Tip>
        <div className="small muted">{label}{r.percentile != null ? ` · top ${100 - r.percentile}%` : ""}</div>
      </div>
    );
  };

  return (
    <div className="card">
      <style>{tipCss}</style>
      <div className="spread" style={{ marginBottom: 8 }}>
        <h3 className="card-title" style={{ margin: 0 }}>{title}</h3>
        <span className="muted small">last {data.weeks} weeks</span>
      </div>
      <div className="flex" style={{ gap: 24, justifyContent: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <Rank label="Call quality" r={data.qualityRank} brief={qualityBrief} />
        <Rank label="Orders" r={data.ordersRank} brief={ordersBrief} />
        <div style={{ textAlign: "center" }}>
          <Tip brief={qualityNumBrief}>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{data.myQuality ?? "—"}</div>
          </Tip>
          <div className="small muted">your quality · team {data.teamQuality ?? "—"}</div>
        </div>
      </div>
      {hasData ? (
        <div style={{ width: "100%", height: 200 }}>
          <ResponsiveContainer>
            <LineChart data={chart} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef0f3" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} width={34} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="team" name="Team avg" stroke="#9aa3af" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="you" name="You" stroke="var(--accent)" strokeWidth={2.5} dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : <div className="muted small" style={{ padding: "16px 0" }}>Not enough calls yet to chart a trend.</div>}
    </div>
  );
}
