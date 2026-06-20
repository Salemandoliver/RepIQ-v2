import React, { useEffect, useState } from "react";
import api from "../api";

// Campaign badges on the call detail (Roadmap Phase 2) — did the rep address each live campaign,
// and how did the customer react. Reps see their own; managers see all.

const ADDR = {
  yes: { c: "var(--green)", ico: "✓", label: "Addressed" },
  weak: { c: "var(--amber)", ico: "~", label: "Briefly" },
  missed: { c: "var(--red)", ico: "✕", label: "Missed" },
};
const TYPE_ICO = { promotion: "📣", incentive: "🎯" };
const REACT = { positive: "🙂 Positive", neutral: "😐 Neutral", objection: "🚧 Objection", "n/a": "" };

export default function CampaignBadges({ callId }) {
  const [mentions, setMentions] = useState(null);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    api.get(`/api/v1/campaigns/call/${callId}/mentions`)
      .then((d) => setMentions(d.mentions || [])).catch(() => setMentions([]));
  }, [callId]);

  if (!mentions || mentions.length === 0) return null;

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="muted small" style={{ marginBottom: 8, fontWeight: 600 }}>CAMPAIGNS LIVE ON THIS CALL</div>
      <div className="flex" style={{ gap: 8, flexWrap: "wrap" }}>
        {mentions.map((m, i) => {
          const a = ADDR[m.addressed] || ADDR.missed;
          const isOpen = open === i;
          return (
            <button key={i} onClick={() => setOpen(isOpen ? null : i)}
              className="siq-chip" style={{ cursor: "pointer", borderColor: a.c,
                background: `color-mix(in srgb, ${a.c} 12%, transparent)`, color: "var(--text)" }}>
              {TYPE_ICO[m.type]} {m.name} · <span style={{ color: a.c, fontWeight: 700 }}>{a.ico} {a.label}</span>
            </button>
          );
        })}
      </div>
      {open != null && mentions[open] && (
        <div className="siq-note" style={{ marginTop: 10 }}>
          <div style={{ fontWeight: 600 }}>{mentions[open].name}</div>
          {mentions[open].evidence && <div className="small" style={{ marginTop: 4 }}>{mentions[open].evidence}</div>}
          <div className="small muted" style={{ marginTop: 4 }}>
            {REACT[mentions[open].customerReaction] || ""}
            {mentions[open].outcome ? ` · ${mentions[open].outcome}` : ""}
          </div>
          {mentions[open].addressed !== "yes" && mentions[open].talkingPoints && (
            <div className="small" style={{ marginTop: 8 }}>
              <span className="muted">Next time:</span> {mentions[open].talkingPoints.split("\n")[0]}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
