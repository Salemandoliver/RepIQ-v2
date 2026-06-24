import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Avatar, Skeleton } from "./ui.jsx";
import { useTeamAvatars } from "./useTeamAvatars.js";
import { useCachedGet } from "../useCachedGet.js";

// Team league table — Sales Reps / BCs ranked by call quality, with orders and "most improved".
// Collapsible (defaults to rolled up) + team filters. Managers and Operations are excluded
// server-side, so only reps and business creators appear. (Roadmap Phase 1.)

const FILTERS = [
  ["all", "Teams"],
  ["business_creators", "Business Creators"],
  ["value", "Value Team"],
  ["volume", "Volume Team"],
];

const mean = (xs) => {
  const v = xs.filter((x) => x != null);
  return v.length ? Math.round((v.reduce((a, b) => a + b, 0) / v.length) * 10) / 10 : null;
};

export default function TeamLeague({ days = 30 }) {
  const { data, error: err } = useCachedGet(`/api/intelligence/league?days=${days}`);
  const [open, setOpen] = useState(false);         // default rolled up
  const [filter, setFilter] = useState("all");
  const avatars = useTeamAvatars();

  const reps = useMemo(() => {
    const all = data?.reps || [];
    return filter === "all" ? all : all.filter((r) => r.group === filter);
  }, [data, filter]);

  const teamAvg = useMemo(() => mean(reps.map((r) => r.quality)), [reps]);
  const mostImproved = useMemo(() => {
    const imp = reps.filter((r) => r.deltaQuality && r.deltaQuality > 0);
    return imp.length ? imp.reduce((a, b) => (b.deltaQuality > a.deltaQuality ? b : a)) : null;
  }, [reps]);

  if (err) return null;
  if (!data) return <div className="card"><Skeleton h={200} /></div>;

  const medal = (i) => (i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : `${i + 1}`);
  const delta = (d) => {
    if (d == null) return null;
    if (d > 0) return <span style={{ color: "var(--green)" }}>▲ {d}</span>;
    if (d < 0) return <span style={{ color: "var(--red)" }}>▼ {Math.abs(d)}</span>;
    return <span className="muted">–</span>;
  };

  return (
    <div className="card">
      <div className="spread" style={{ marginBottom: open ? 8 : 0, cursor: "pointer" }} onClick={() => setOpen((v) => !v)}>
        <h3 className="card-title" style={{ margin: 0 }}>🏆 Team league</h3>
        <div className="flex" style={{ gap: 10, alignItems: "center" }}>
          <span className="muted small">last {data.days} days · avg quality {teamAvg ?? "—"}</span>
          <button className="btn btn-ghost btn-sm" aria-label={open ? "Collapse" : "Expand"}
            onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}>{open ? "▲" : "▼"}</button>
        </div>
      </div>

      {open && (
        <>
          <div className="siq-seg" style={{ marginBottom: 10, flexWrap: "wrap" }}>
            {FILTERS.map(([v, l]) => (
              <button key={v} className={`siq-seg-btn${filter === v ? " on" : ""}`} onClick={() => setFilter(v)}>{l}</button>
            ))}
          </div>

          {reps.length === 0 ? (
            <div className="muted small" style={{ padding: "8px 0" }}>No reps in this group for the period.</div>
          ) : (
            <>
              {mostImproved && (
                <div className="small" style={{ marginBottom: 10 }}>
                  <b>Most improved:</b> {mostImproved.name} <span style={{ color: "var(--green)" }}>▲ {mostImproved.deltaQuality}</span> on call quality 👏
                </div>
              )}
              <table className="hr-doc-table">
                <thead><tr><th style={{ width: 36 }}>#</th><th>Rep</th><th style={{ textAlign: "right" }}>Quality</th><th style={{ textAlign: "right" }}>Δ</th><th style={{ textAlign: "right" }}>Orders</th><th style={{ textAlign: "right" }}>Calls</th><th style={{ textAlign: "right" }} title="Forecast Reliability Score (rolling 8 weeks)">Forecast</th></tr></thead>
                <tbody>
                  {reps.map((r, i) => (
                    <tr key={r.userId}>
                      <td style={{ fontSize: 16 }}>{medal(i)}</td>
                      <td>
                        <Link to={`/command-centre?rep=${r.userId}`} className="flex" style={{ gap: 8, alignItems: "center", color: "inherit" }}>
                          <Avatar name={r.name} size={26} photo={avatars?.[String(r.userId)]} />
                          <b>{r.name}</b>
                        </Link>
                      </td>
                      <td style={{ textAlign: "right", fontWeight: 700, color: (r.quality ?? 0) >= (teamAvg ?? 0) ? "var(--green)" : "var(--text)" }}>{r.quality ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{delta(r.deltaQuality)}</td>
                      <td style={{ textAlign: "right" }}>{r.orders}</td>
                      <td style={{ textAlign: "right" }} className="muted">{r.calls}</td>
                      <td style={{ textAlign: "right" }}>
                        {r.reliabilityScore != null
                          ? <b style={{ color: { green: "var(--green)", amber: "var(--amber)", red: "var(--red)" }[r.reliabilityBand] || "var(--text)" }}>{r.reliabilityScore}</b>
                          : <span className="muted small">{r.reliabilityWeeks ? `${r.reliabilityWeeks}/8` : "—"}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </div>
  );
}
