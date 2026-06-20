import React, { useEffect, useState } from "react";
import api from "../api";

// Campaigns needing attention (Roadmap Phase 4 alerts) — weak adoption or ending soon.
// Manager-only; renders nothing when all campaigns are healthy.
export default function CampaignAlerts() {
  const [items, setItems] = useState(null);
  useEffect(() => {
    api.get("/api/v1/campaigns/attention").then((d) => setItems(d.items || [])).catch(() => setItems([]));
  }, []);

  if (!items || items.length === 0) return null;

  return (
    <div className="card" style={{ marginBottom: 16, borderLeft: "4px solid var(--amber)" }}>
      <h3 className="card-title" style={{ margin: "0 0 8px" }}>📣 Campaigns needing a nudge</h3>
      {items.map((c) => (
        <div key={c.id} className="spread" style={{ padding: "6px 0", borderTop: "1px solid var(--border)" }}>
          <div>
            <b>{c.type === "incentive" ? "🎯" : "📣"} {c.name}</b>
            <div className="small muted">
              {c.calls} call{c.calls === 1 ? "" : "s"} tracked{c.rate != null ? ` · ${c.rate}% adoption` : ""}
            </div>
          </div>
          <div className="flex" style={{ gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
            {c.flags.map((f, i) => (
              <span key={i} className="siq-chip" style={{ color: "var(--amber)", borderColor: "var(--amber)" }}>{f}</span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
