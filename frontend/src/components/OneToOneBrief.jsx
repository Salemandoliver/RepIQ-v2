import React, { useState } from "react";
import api from "../api";

// Auto 1-to-1 brief (Intelligence Phase 3) — manager prep generated from the rep's insights +
// metrics + benchmark rank. Lives in the HR Performance/Reviews tab. Generated on demand.
export default function OneToOneBrief({ userId }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const generate = async () => {
    setBusy(true); setErr(null);
    try { setData(await api.get(`/api/intelligence/one-to-one/${userId}`)); }
    catch (e) { setErr(e.message || "Couldn't generate the brief"); }
    finally { setBusy(false); }
  };

  return (
    <div className="card" style={{ marginBottom: 16, borderLeft: "4px solid var(--accent)" }}>
      <div className="spread" style={{ alignItems: "center" }}>
        <h3 className="hr-sec-title" style={{ margin: 0 }}>🧠 AI 1-to-1 brief</h3>
        <button className="btn btn-primary btn-sm" onClick={generate} disabled={busy}>
          {busy ? "Preparing…" : data ? "Regenerate" : "Prepare brief"}
        </button>
      </div>
      {err && <div className="small" style={{ color: "var(--red)", marginTop: 8 }}>{err}</div>}
      {!data && !busy && !err && (
        <div className="muted small" style={{ marginTop: 8 }}>
          Pulls this rep's live insights, metrics vs the team and rank into a ready-to-use 1-to-1 prep —
          strengths, focus areas with evidence, and questions to ask.
        </div>
      )}
      {data && (
        <div style={{ marginTop: 10 }}>
          {data.headline && <div style={{ fontWeight: 600, fontSize: 15 }}>{data.headline}</div>}

          {data.goingWell?.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div className="muted small" style={{ marginBottom: 4 }}>✅ GOING WELL</div>
              <ul className="siq-insights">{data.goingWell.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </div>
          )}

          {data.focusAreas?.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div className="muted small" style={{ marginBottom: 4 }}>🎯 FOCUS AREAS</div>
              {data.focusAreas.map((f, i) => (
                <div key={i} className="siq-note" style={{ marginBottom: 6 }}>
                  <b>{f.title}</b>
                  {f.evidence && <div className="small" style={{ marginTop: 3 }}>{f.evidence}</div>}
                  {f.action && <div className="small" style={{ marginTop: 3 }}><b style={{ color: "var(--accent)" }}>→ </b>{f.action}</div>}
                </div>
              ))}
            </div>
          )}

          {data.talkingPoints?.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div className="muted small" style={{ marginBottom: 4 }}>💬 QUESTIONS TO ASK</div>
              <ul className="siq-insights">{data.talkingPoints.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </div>
          )}

          <div className="muted small" style={{ marginTop: 8 }}>
            {data.source === "ai" ? "AI-generated" : "From your data"} · {data.generatedAt ? new Date(data.generatedAt).toLocaleString("en-GB") : ""}
          </div>
        </div>
      )}
    </div>
  );
}
