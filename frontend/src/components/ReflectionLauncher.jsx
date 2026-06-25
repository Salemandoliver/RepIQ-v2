import React, { useState } from "react";
import { api } from "../api";
import { useCachedGet } from "../useCachedGet.js";
import ReflectionChat from "./ReflectionChat.jsx";

/* A button that opens the reflection chat for a given review video. Shown under the rep's own
   weekly (Oliver) / review (Gary) videos. */
export default function ReflectionLauncher({ videoId, presenter = "Oliver", label }) {
  const [open, setOpen] = useState(false);
  if (!videoId) return null;
  return (
    <>
      <div style={{ marginTop: 12 }}>
        <button className="btn btn-primary btn-sm" onClick={() => setOpen(true)}>
          💬 {label || `Reflect with ${presenter}`}
        </button>
      </div>
      {open && <ReflectionChat videoId={videoId} presenter={presenter} onClose={() => setOpen(false)} />}
    </>
  );
}

/* Today nudge — prompts the rep to reflect on a fresh review, or celebrates their streak when they're
   up to date. */
export function ReflectionNudge() {
  const { data } = useCachedGet("/api/reflection/me/status", { ttl: 5 * 60 * 1000 });
  const [open, setOpen] = useState(false);
  if (!data) return null;
  const p = data.pending;
  const streak = data.streak || 0;

  if (!p) {
    if (streak < 2) return null;   // nothing to nudge and no streak worth shouting about
    return (
      <div className="card" style={{ marginTop: 16, borderLeft: "3px solid var(--green)" }}>
        <div className="flex" style={{ gap: 10, alignItems: "center" }}>
          <span aria-hidden="true" style={{ fontSize: 18 }}>🔥</span>
          <div className="small"><b>{streak}-review reflection streak</b> — you're consistently learning from your reviews. Nice work.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ marginTop: 16, borderLeft: "3px solid var(--accent)" }}>
      <div className="flex" style={{ gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span aria-hidden="true" style={{ fontSize: 18 }}>💬</span>
        <div style={{ flex: 1, minWidth: 180 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>
            {p.started ? `Finish your ${p.period} reflection` : `Reflect on your ${p.period} review`} with {p.presenter}
          </div>
          <div className="muted small">
            A 5-minute chat to lock in what to improve — and {p.presenter} will listen.
            {streak >= 2 ? ` Keep your 🔥 ${streak}-review streak going.` : ""}
          </div>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => setOpen(true)}>{p.started ? "Continue" : "Start"}</button>
      </div>
      {open && <ReflectionChat videoId={p.videoId} presenter={p.presenter} onClose={() => setOpen(false)} />}
    </div>
  );
}
