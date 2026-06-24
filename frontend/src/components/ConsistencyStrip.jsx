import React from "react";

/* Forecast Reliability — an 8-week consistency strip: the score, the hit record, a small bar per
   week (green = hit ≥100%, amber/red = miss, faint = on-leave/excused), and the component
   breakdown. Reusable on the rep Today card, SalesIQ, and the manager rep view. */

const BANDC = { green: "var(--green)", amber: "var(--amber)", red: "var(--red)" };

export default function ConsistencyStrip({ reliability, title = "Forecast reliability" }) {
  if (!reliability) return null;
  const { score, band, weeks, hitCount, components, history = [] } = reliability;

  if (!weeks) {
    return (
      <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
        <div className="muted small">{title}: building history — your weekly record starts once this week closes.</div>
      </div>
    );
  }

  const bars = [...history].reverse();   // oldest → newest, left to right
  const barColor = (h) => (h.excused ? "var(--text-faint)"
    : h.hit ? "var(--green)" : (h.achievementPct >= 70 ? "var(--amber)" : "var(--red)"));

  return (
    <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
      <div className="spread" style={{ alignItems: "baseline", marginBottom: 8 }}>
        <span className="small" style={{ fontWeight: 700 }}>{title}</span>
        <span className="small">
          <b style={{ color: BANDC[band] || "var(--text)", fontSize: 16 }}>{score}</b>
          <span className="muted"> /100 · {hitCount}/{weeks} weeks hit</span>
        </span>
      </div>
      <div className="flex" style={{ gap: 4, alignItems: "flex-end", height: 46, marginBottom: 8 }}>
        {bars.map((h, i) => (
          <div key={i} title={`Wk ${h.weekNumber}: ${h.excused ? "on leave" : Math.round(h.achievementPct || 0) + "%"}`}
            style={{
              flex: 1, borderRadius: 3, background: barColor(h), opacity: h.excused ? 0.45 : 1,
              height: `${Math.max(6, Math.min(h.achievementPct || 0, 120) / 120 * 100)}%`,
            }} />
        ))}
      </div>
      {components && (
        <div className="flex" style={{ gap: 12, flexWrap: "wrap" }}>
          {[["Hit rate", "hitRate"], ["Accuracy", "accuracy"], ["Trend", "trend"], ["Discipline", "discipline"]].map(([l, k]) => (
            <span key={k} className="muted small">{l}: <b style={{ color: "var(--text)" }}>{components[k]}%</b></span>
          ))}
        </div>
      )}
    </div>
  );
}
