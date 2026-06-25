import React, { useState } from "react";
import { api } from "../api";
import { CollapsibleCard, Modal, Avatar } from "./ui.jsx";
import { useCachedGet } from "../useCachedGet.js";

/* Manager view of review reflections for the Command Centre — who's reflected, blockers that need
   the manager, recurring themes, and a per-rep summary with drill-in to the full transcript. */

const ENG = (e) => (e == null ? "var(--text-faint)" : e >= 70 ? "var(--green)" : e >= 45 ? "var(--amber)" : "var(--red)");
const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "—");

function TranscriptModal({ userId, name, onClose }) {
  const { data } = useCachedGet(`/api/reflection/rep/${userId}`, { ttl: 5 * 60 * 1000 });
  const latest = data?.reflections?.find((r) => r.status === "complete") || data?.reflections?.[0];
  return (
    <Modal title={`🪞 ${name}'s reflection`} onClose={onClose} wide>
      {!data ? <div className="muted small">Loading…</div> : !latest ? (
        <div className="muted small">No reflection yet.</div>
      ) : (
        <>
          {latest.summary && (
            <div className="siq-note" style={{ marginBottom: 12 }}><b>Summary:</b> {latest.summary}</div>
          )}
          {(latest.commitments || []).length > 0 && (
            <div className="small" style={{ marginBottom: 10 }}>
              <b>Commitments:</b>
              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                {latest.commitments.map((c, i) => <li key={i}>{c.text}{c.target ? ` — ${c.target}` : ""}</li>)}
              </ul>
            </div>
          )}
          {(latest.blockers || []).length > 0 && (
            <div className="small" style={{ marginBottom: 10 }}>
              <b>Blockers:</b> {latest.blockers.map((b, i) => (
                <span key={i} className="chip" style={{ fontSize: 11, marginRight: 4 }}>{b.text}{b.needsManager ? " · wants help" : ""}</span>
              ))}
            </div>
          )}
          {latest.selfAwarenessNote && <div className="muted small" style={{ marginBottom: 10 }}>Self-awareness: {latest.selfAwarenessNote}</div>}
          <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
            <div className="muted small" style={{ fontWeight: 700, marginBottom: 6 }}>Full conversation</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: "50vh", overflowY: "auto" }}>
              {(latest.turns || []).map((t, i) => (
                <div key={i} style={{ alignSelf: t.role === "rep" ? "flex-end" : "flex-start", maxWidth: "85%",
                  background: t.role === "rep" ? "var(--accent-grad)" : "var(--surface-2,#f3f4f6)",
                  color: t.role === "rep" ? "#fff" : "var(--text)", borderRadius: 12, padding: "8px 12px", fontSize: 13, whiteSpace: "pre-wrap" }}>
                  {t.text}
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </Modal>
  );
}

export default function ReflectionsManager({ team }) {
  const url = `/api/reflection/team${team && team !== "all" ? `?team=${encodeURIComponent(team)}` : ""}`;
  const { data } = useCachedGet(url);
  const [view, setView] = useState(null);   // {userId, name}
  if (!data || !data.signals) return null;

  const sigs = data.signals;
  const reflected = sigs.filter((s) => s.lastReflectedAt);

  return (
    <CollapsibleCard title="🪞 Review Reflections" style={{ marginBottom: 16 }}
      actions={<span className="muted small">{reflected.length}/{sigs.length} reflected</span>}>
      {data.notReflected?.length > 0 && (
        <div className="siq-note" style={{ marginBottom: 10 }}>
          💬 Not yet reflected: {data.notReflected.join(", ")}
        </div>
      )}
      {data.blockersForHelp?.length > 0 && (
        <div className="siq-note" style={{ marginBottom: 10, background: "rgba(245,158,11,0.1)", borderColor: "rgba(245,158,11,0.3)" }}>
          🪻 Blockers needing help: {data.blockersForHelp.map((b) => `${b.name} (${(b.blockers || []).join(", ")})`).join(" · ")}
        </div>
      )}
      {data.topThemes?.length > 0 && (
        <div className="small" style={{ marginBottom: 10 }}>
          <b>Recurring themes:</b> {data.topThemes.map((t, i) => <span key={i} className="chip" style={{ fontSize: 11, marginRight: 4 }}>{t}</span>)}
        </div>
      )}

      <table className="hr-doc-table">
        <thead>
          <tr><th>Rep</th><th>Status</th><th style={{ textAlign: "right" }}>Engagement</th><th>Latest commitment</th><th></th></tr>
        </thead>
        <tbody>
          {sigs.map((s) => (
            <tr key={s.userId}>
              <td><div className="flex" style={{ gap: 8, alignItems: "center" }}><Avatar name={s.name} size={24} />{s.name}</div></td>
              <td className="small">
                {s.lastReflectedAt ? <span className="muted">reflected {fmtDate(s.lastReflectedAt)}{s.streak >= 2 ? ` · 🔥${s.streak}` : ""}</span>
                  : s.flags?.notReflected ? <span style={{ color: "var(--accent)" }}>not yet</span> : <span className="muted">—</span>}
              </td>
              <td style={{ textAlign: "right", fontWeight: 700, color: ENG(s.engagement) }}>{s.engagement != null ? `${s.engagement}` : "—"}</td>
              <td className="small muted" style={{ maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {s.openCommitments?.[0] || "—"}
              </td>
              <td style={{ textAlign: "right" }}>
                {s.lastReflectedAt && <button className="btn btn-ghost btn-sm" onClick={() => setView({ userId: s.userId, name: s.name })}>View</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {view && <TranscriptModal userId={view.userId} name={view.name} onClose={() => setView(null)} />}
    </CollapsibleCard>
  );
}
