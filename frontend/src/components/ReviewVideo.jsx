import React, { useEffect, useState } from "react";
import { api } from "../api";
import Markdown from "./Markdown.jsx";
import { Chevron } from "./ui.jsx";
import ReflectionLauncher from "./ReflectionLauncher.jsx";

/* Monthly / quarterly intelligent performance REVIEW, presented by Gary. Renders nothing unless a
   review exists for the period (so it only appears from the first Monday of the month onward).
   userId omitted = the signed-in rep's own; userId set = a manager viewing that person's. */
export default function ReviewVideo({ userId, reloadKey }) {
  const [v, setV] = useState(null);
  const [open, setOpen] = useState(true);   // rolls up only the written review; the video stays
  useEffect(() => {
    const path = userId ? `/api/intelligence/video/review?user_id=${userId}` : "/api/intelligence/video/review";
    api.get(path).then((d) => setV(d)).catch(() => {});
  }, [userId, reloadKey]);

  if (!v || !v.hasReview) return null;
  const label = v.type === "quarterly_review" ? "Quarterly review" : "Monthly review";
  return (
    <div className="card" style={{ borderTop: "3px solid var(--accent)", marginBottom: 16 }}>
      <div className="flex" style={{ gap: 8, marginBottom: 10, alignItems: "center", cursor: "pointer", userSelect: "none" }}
        onClick={() => setOpen((o) => !o)} role="button" aria-expanded={open} title="Roll the written review up or down (the video stays)">
        <Chevron open={open} />
        <span aria-hidden="true">🏆</span>
        <span style={{ fontWeight: 700, fontSize: 15 }}>{userId ? (v.title || label) : `Your ${label.toLowerCase()}`}</span>
        <span className="siq-chip" style={{ fontSize: 11, fontWeight: 700, color: "var(--accent)", borderColor: "var(--accent)" }}>{label}</span>
        <span className="muted small" style={{ marginLeft: "auto" }}>presented by Gary</span>
      </div>

      {v.hasVideo && (
        <video src={v.videoUrl} controls style={{ width: "100%", borderRadius: 10, background: "#000", display: "block", marginBottom: 12 }} />
      )}

      {open && (<>
        {v.headline && <div style={{ fontWeight: 600, marginBottom: 8 }}>{v.headline}</div>}
        <div style={{ background: "var(--surface-2, #f3f4f6)", borderRadius: 10, padding: "13px 15px", maxHeight: "60vh", overflowY: "auto" }}>
          <Markdown text={v.script || "Your review is being prepared."} />
        </div>
        <div className="muted small" style={{ marginTop: 8 }}>
          {v.hasVideo ? "Your performance review from Gary — watch above or read here."
            : v.status === "rendering" ? "🎥 Gary's review video is rendering — it'll appear above shortly; read it meanwhile."
            : v.status === "failed" ? "The review video couldn't be rendered — here's the written review."
            : "Gary's written performance review. The presenter-video version appears once HeyGen rendering is enabled."}
        </div>
        {v.error && <div className="small" style={{ color: "var(--red)", marginTop: 6 }}>Note: {v.error}</div>}
      </>)}
      {!userId && v.id && <ReflectionLauncher videoId={v.id} presenter="Gary" />}
    </div>
  );
}
