import React, { useEffect, useState } from "react";
import { api } from "../api";
import { Spinner } from "./ui.jsx";

/* Feature 8 — weekly AI performance video / briefing. Shows the rendered HeyGen video when
   ready AND always shows the written briefing beneath it, so the rep always has readable
   content even if the video is still rendering or won't play.
   userId omitted = the signed-in rep/BC's own; userId set = a manager viewing that person's. */
export default function WeeklyVideo({ userId }) {
  const [v, setV] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(false);

  const load = () => {
    setLoading(true); setErr(false);
    const path = userId ? `/api/intelligence/video/${userId}` : "/api/intelligence/video";
    api.get(path).then((d) => setV(d)).catch(() => setErr(true)).finally(() => setLoading(false));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [userId]);

  if (loading) return (
    <div className="card flex" style={{ justifyContent: "center", alignItems: "center", gap: 10, padding: 28 }}>
      <Spinner /><span className="muted small">Preparing the weekly briefing…</span>
    </div>
  );
  if (err || !v) return (
    <div className="card">
      <div className="flex" style={{ gap: 8, marginBottom: 6 }}>
        <span aria-hidden="true">🎬</span><span style={{ fontWeight: 700, fontSize: 15 }}>Weekly performance video</span>
      </div>
      <div className="muted small">Couldn't load the weekly briefing right now. <button className="btn btn-ghost btn-sm" onClick={load}>Try again</button></div>
    </div>
  );

  const wk = v.weekStart ? new Date(v.weekStart).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "";
  return (
    <div className="card">
      <div className="flex" style={{ gap: 8, marginBottom: 10 }}>
        <span aria-hidden="true">🎬</span>
        <span style={{ fontWeight: 700, fontSize: 15 }}>{userId ? (v.title || "Weekly performance video") : "Your weekly performance video"}</span>
        <span className="muted small" style={{ marginLeft: "auto" }}>{wk ? `presented by Oliver · week of ${wk}` : "presented by Oliver"}</span>
      </div>

      {v.hasVideo && (
        <video src={v.videoUrl} controls style={{ width: "100%", borderRadius: 10, background: "#000", display: "block", marginBottom: 12 }} />
      )}

      {v.headline && <div style={{ fontWeight: 600, marginBottom: 8 }}>{v.headline}</div>}
      <div style={{ background: "var(--surface-2, #f3f4f6)", borderRadius: 10, padding: "13px 15px", lineHeight: 1.65, fontSize: 14, whiteSpace: "pre-wrap", maxHeight: "62vh", overflowY: "auto" }}>
        {v.script || "Your briefing for this week is being prepared."}
      </div>
      <div className="muted small" style={{ marginTop: 8 }}>
        {v.hasVideo ? "Your weekly briefing — watch above or read here."
          : v.status === "rendering" ? "🎥 The presenter video is rendering — it'll appear above shortly; read the briefing meanwhile."
          : v.status === "failed" ? "The video couldn't be rendered this week — here's your written briefing."
          : "Your AI weekly briefing. The presenter-video version appears once video rendering is enabled for your team."}
      </div>
      {v.error && <div className="small" style={{ color: "var(--red)", marginTop: 6 }}>Error: {v.error}</div>}
    </div>
  );
}
