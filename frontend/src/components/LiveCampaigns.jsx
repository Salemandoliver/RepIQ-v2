import React, { useEffect, useState } from "react";
import api from "../api";

// Rep-facing "Live now" campaigns card (Roadmap Phase 4) — what's running today for the rep's team,
// with the talking points to use on calls. Promotions show the offer; incentives show the qualifying
// product framing only (never the bonus £).

function daysLeft(end) {
  return Math.ceil((new Date(end + "T23:59:59") - new Date()) / 86400000);
}

export default function LiveCampaigns() {
  const [camps, setCamps] = useState(null);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    api.get("/api/v1/campaigns/live").then((d) => setCamps(d.campaigns || [])).catch(() => setCamps([]));
  }, []);

  if (!camps || camps.length === 0) return null;

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="spread" style={{ marginBottom: 8 }}>
        <h3 className="card-title" style={{ margin: 0 }}>📣 Live now — push these today</h3>
        <span className="muted small">{camps.length} running</span>
      </div>
      {camps.map((c, i) => {
        const isOpen = open === i;
        const left = daysLeft(c.endDate);
        const points = (c.talkingPoints || "").split("\n").map((s) => s.trim()).filter(Boolean);
        return (
          <div key={c.id} className="siq-note" style={{ marginBottom: 8, cursor: "pointer" }}
            onClick={() => setOpen(isOpen ? null : i)}>
            <div className="spread">
              <div>
                <b>{c.type === "incentive" ? "🎯" : "📣"} {c.name}</b>
                {c.type === "promotion" && c.offer && <div className="small" style={{ marginTop: 2 }}>{c.offer}</div>}
                {c.type === "incentive" && c.qualifyingRule && <div className="small" style={{ marginTop: 2 }}>Pitch: {c.qualifyingRule}</div>}
              </div>
              <span className="small muted" style={{ whiteSpace: "nowrap", color: left <= 3 ? "var(--amber)" : undefined }}>
                {left >= 0 ? `${left}d left` : ""}
              </span>
            </div>
            {isOpen && points.length > 0 && (
              <ul className="siq-insights" style={{ marginTop: 8 }}>
                {points.map((p, j) => <li key={j}>{p.replace(/^[•\-*]\s*/, "")}</li>)}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
