import React, { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid } from "recharts";
import api from "../api";

// "You vs the team" — call quality over time against the team average, plus rank.
// A gentle, evidence-based nudge to improve and compete. (Roadmap Phase 0/1.)
export default function TeamCompareCard({ userId, title = "You vs the team" }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    const q = userId ? `?user_id=${userId}` : "";
    api.get(`/api/intelligence/benchmarks${q}`).then(setData).catch(() => setErr(true));
  }, [userId]);

  if (err) return null;
  if (!data) return <div className="card"><div className="skeleton" style={{ height: 180 }} /></div>;

  const chart = (data.repSeries || []).map((p, i) => ({
    label: p.label,
    you: p.quality,
    team: data.teamSeries?.[i]?.quality ?? null,
  }));
  const hasData = chart.some((p) => p.you != null || p.team != null);

  const Rank = ({ label, r, suffix }) => {
    if (!r) return null;
    const tone = r.percentile >= 67 ? "var(--green)" : r.percentile >= 34 ? "var(--amber)" : "var(--text-soft)";
    return (
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: tone }}>{r.label}</div>
        <div className="small muted">{label}{r.percentile != null ? ` · top ${100 - r.percentile}%` : ""}{suffix || ""}</div>
      </div>
    );
  };

  return (
    <div className="card">
      <div className="spread" style={{ marginBottom: 8 }}>
        <h3 className="card-title" style={{ margin: 0 }}>{title}</h3>
        <span className="muted small">last {data.weeks} weeks</span>
      </div>
      <div className="flex" style={{ gap: 24, justifyContent: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <Rank label="Call quality" r={data.qualityRank} />
        <Rank label="Orders" r={data.ordersRank} />
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{data.myQuality ?? "—"}</div>
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
