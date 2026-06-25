import React from "react";

/* Reusable dashboard visual kit — gauges + KPI tiles in the app's own light/accent palette
   (NOT a dark theme). Use these to give any surface a clean "dashboard" feel while staying
   consistent with our colours. */

export const RAG = { green: "var(--green)", amber: "var(--amber)", red: "var(--red)" };

// Achievement banding: ≥100% green, ≥70% amber, else red. Pass an explicit band/color to override.
export function achievementBand(pct) {
  if (pct == null) return "none";
  if (pct >= 100) return "green";
  if (pct >= 70) return "amber";
  return "red";
}

// The top half-circle, left → right. (Sweep flag 1 renders it over the top in SVG's y-down space.)
// We draw this once and reveal a fraction of it with stroke-dasharray + pathLength — reliable for
// any value (no per-value trig, so partial fills can't land below the centre line).
function semiPath(cx, cy, r) {
  return `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
}

/* A half-circle gauge. `value` is a percentage (may exceed 100 — the fill caps at full but the
   number shows the true figure). `color`/`band` optional; otherwise derived from achievement bands. */
export function Gauge({ value, label, sub, size = 132, color, band, track = "#eef0f3", thickness = 11 }) {
  const w = size;
  const h = size * 0.62;
  const cx = w / 2;
  const cy = h - 6;
  const r = w / 2 - thickness / 2 - 2;
  const has = value != null && !Number.isNaN(value);
  const fillPct = has ? Math.max(0, Math.min(value, 100)) : 0;   // 0..100 of the arc
  const stroke = color || RAG[band || achievementBand(has ? value : null)] || "var(--text-faint)";
  const d = semiPath(cx, cy, r);
  return (
    <div style={{ textAlign: "center", minWidth: w }}>
      <svg width={w} height={h + 4} viewBox={`0 0 ${w} ${h + 4}`} role="img"
        aria-label={`${label || "value"}: ${has ? Math.round(value) + "%" : "no data"}`}>
        <path d={d} fill="none" stroke={track} strokeWidth={thickness} strokeLinecap="round" pathLength="100" />
        {has && fillPct > 0 && (
          <path d={d} fill="none" stroke={stroke} strokeWidth={thickness} strokeLinecap="round"
            pathLength="100" strokeDasharray={`${fillPct} 100`} />
        )}
        <text x={cx} y={cy - 6} textAnchor="middle" style={{ fontSize: size * 0.21, fontWeight: 800, fill: "var(--text)" }}>
          {has ? `${Math.round(value)}%` : "—"}
        </text>
      </svg>
      {label && <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-soft)", marginTop: -2 }}>{label}</div>}
      {sub && <div style={{ fontSize: 11.5, color: "var(--text-faint)", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

/* Big-number KPI tile. */
export function KpiTile({ label, value, sub, accent, style }) {
  return (
    <div className="siq-tile" style={{ border: "1px solid var(--border)", borderRadius: 12, background: "#fff", ...style }}>
      <div className="siq-tile-label">{label}</div>
      <div className="siq-tile-value" style={accent ? { color: accent } : undefined}>{value}</div>
      {sub && <div className="siq-tile-sub">{sub}</div>}
    </div>
  );
}

/* A slim labelled progress bar (actual vs target), RAG-coloured. */
export function ProgressRow({ label, actual, forecast, pct, money = (n) => `£${Math.round(n).toLocaleString()}` }) {
  const band = achievementBand(pct);
  const frac = pct == null ? 0 : Math.min(pct, 100) / 100;
  return (
    <div style={{ marginBottom: 10 }}>
      <div className="spread" style={{ fontSize: 12.5, marginBottom: 4 }}>
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span className="muted">{money(actual)} / {money(forecast)}{pct != null ? ` · ${Math.round(pct)}%` : " · —"}</span>
      </div>
      <div className="siq-bar"><div style={{ width: `${frac * 100}%`, background: RAG[band] || "var(--text-faint)" }} /></div>
    </div>
  );
}
