import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import { Avatar, Skeleton } from "./ui.jsx";
import { useTeamAvatars } from "./useTeamAvatars.js";

// Team league table — reps ranked by call quality, with orders and "most improved".
// Evidence-based healthy competition for the Command Centre. (Roadmap Phase 1.)
export default function TeamLeague({ days = 30 }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(false);
  const avatars = useTeamAvatars();

  useEffect(() => {
    api.get(`/api/intelligence/league?days=${days}`).then(setData).catch(() => setErr(true));
  }, [days]);

  if (err) return null;
  if (!data) return <div className="card"><Skeleton h={200} /></div>;
  const reps = data.reps || [];
  if (reps.length === 0) return null;

  const medal = (rank) => (rank === 1 ? "🥇" : rank === 2 ? "🥈" : rank === 3 ? "🥉" : `${rank}`);
  const delta = (d) => {
    if (d == null) return null;
    if (d > 0) return <span style={{ color: "var(--green)" }}>▲ {d}</span>;
    if (d < 0) return <span style={{ color: "var(--red)" }}>▼ {Math.abs(d)}</span>;
    return <span className="muted">–</span>;
  };

  return (
    <div className="card">
      <div className="spread" style={{ marginBottom: 8 }}>
        <h3 className="card-title" style={{ margin: 0 }}>🏆 Team league</h3>
        <span className="muted small">last {data.days} days · team avg quality {data.teamQuality ?? "—"}</span>
      </div>
      {data.mostImproved && (
        <div className="small" style={{ marginBottom: 10 }}>
          <b>Most improved:</b> {data.mostImproved.name} <span style={{ color: "var(--green)" }}>▲ {data.mostImproved.delta}</span> on call quality 👏
        </div>
      )}
      <table className="hr-doc-table">
        <thead><tr><th style={{ width: 36 }}>#</th><th>Rep</th><th style={{ textAlign: "right" }}>Quality</th><th style={{ textAlign: "right" }}>Δ</th><th style={{ textAlign: "right" }}>Orders</th><th style={{ textAlign: "right" }}>Calls</th></tr></thead>
        <tbody>
          {reps.map((r) => (
            <tr key={r.userId}>
              <td style={{ fontSize: 16 }}>{medal(r.rank)}</td>
              <td>
                <Link to={`/command-centre?rep=${r.userId}`} className="flex" style={{ gap: 8, alignItems: "center", color: "inherit" }}>
                  <Avatar name={r.name} size={26} photo={avatars?.[String(r.userId)]} />
                  <b>{r.name}</b>
                </Link>
              </td>
              <td style={{ textAlign: "right", fontWeight: 700, color: (r.quality ?? 0) >= (data.teamQuality ?? 0) ? "var(--green)" : "var(--text)" }}>{r.quality ?? "—"}</td>
              <td style={{ textAlign: "right" }}>{delta(r.deltaQuality)}</td>
              <td style={{ textAlign: "right" }}>{r.orders}</td>
              <td style={{ textAlign: "right" }} className="muted">{r.calls}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
