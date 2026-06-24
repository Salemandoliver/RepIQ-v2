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

function polar(cx, cy, r, deg) {
  const a = (deg * Math.PI) / 180;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}
// Half-circle arc from 180° (left) to 0° (right), swept by `frac` (0..1).
function arc(cx, cy, r, frac) {
  const end = 180 - 180 * Math.max(0, Math.min(1, frac));
  const [x1, y1] = polar(cx, cy, r, 180);
  const [x2, y2] = polar(cx, cy, r, end);
  const large = 180 - end > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
}

/* A half-circle gauge. `value` is a percentage (may exceed 100 — the arc caps at full but the
   number shows the true figure). `color`/`band` optional; otherwise derived from achievement bands. */
export function Gauge({ value, label, sub, size = 132, color, band, track = "#eef0f3", thickness = 11 }) {
  const w = size;
  const h = size * 0.62;
  const cx = w / 2;
  const cy = h - 6;
  const r = w / 2 - thickness / 2 - 2;
  const has = value != null && !Number.isNaN(value);
  const frac = has ? Math.min(value, 100) / 100 : 0;
  const stroke = color || RAG[band || achievementBand(has ? value : null)] || "var(--text-faint)";
  return (
    <div style={{ textAlign: "center", minWidth: w }}>
      <svg width={w} height={h + 4} viewBox={`0 0 ${w} ${h + 4}`} role="img"
        aria-label={`${label || "value"}: ${has ? Math.round(value) + "%" : "no data"}`}>
        <path d={arc(cx, cy, r, 1)} fill="none" stroke={track} strokeWidth={thickness} strokeLinecap="round" />
        {has && <path d={arc(cx, cy, r, frac)} fill="none" stroke={stroke} strokeWidth={thickness} strokeLinecap="round" />}
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
