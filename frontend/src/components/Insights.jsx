import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import { Skeleton } from "./ui.jsx";

// Insight feed (Intelligence Phase 3) — the evidence-bound action list the engine generates.
// InsightsFeed = manager (Command Centre); MyFocus = the rep's own (Today). Feedback teaches the engine.

const SEV = {
  high: { c: "var(--red)", label: "Priority" },
  medium: { c: "var(--amber)", label: "Worth a look" },
  low: { c: "var(--text-faint)", label: "Minor" },
  positive: { c: "var(--green)", label: "Win" },
};
const CAT_ICON = {
  skill_gap: "🎯", coaching: "🗣️", momentum: "📈", win: "🏆", risk: "⚠️",
  campaign: "📣", outcome: "🧾", process: "🧾",
};

function Evidence({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="flex" style={{ gap: 6, flexWrap: "wrap", marginTop: 8 }}>
      {items.map((e, i) =>
        e.callId ? (
          <Link key={i} to={`/calls/${e.callId}`} className="siq-chip" style={{ fontSize: 11 }}>▶ {e.label}</Link>
        ) : (
          <span key={i} className="siq-chip" style={{ fontSize: 11 }}>{e.label}</span>
        )
      )}
    </div>
  );
}

function InsightCard({ ins, onFeedback, compact }) {
  const sev = SEV[ins.severity] || SEV.medium;
  const [busy, setBusy] = useState(false);
  const act = async (patch) => {
    setBusy(true);
    try { await api.post(`/api/intelligence/insights/${ins.id}/feedback`, patch); onFeedback(ins.id); }
    catch { setBusy(false); }
  };
  return (
    <div className="card" style={{ marginBottom: 10, borderLeft: `4px solid ${sev.c}`, opacity: busy ? 0.5 : 1 }}>
      <div className="spread" style={{ alignItems: "flex-start", gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div className="flex" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <span>{CAT_ICON[ins.category] || "💡"}</span>
            <strong style={{ fontSize: 14.5 }}>{ins.title}</strong>
            {ins.subjectName && <span className="siq-chip" style={{ fontSize: 11 }}>{ins.subjectName}</span>}
          </div>
          <div className="small" style={{ marginTop: 5, color: "var(--text-soft)" }}>{ins.body}</div>
          {ins.recommendation && (
            <div className="small" style={{ marginTop: 6 }}><b style={{ color: sev.c }}>→ </b>{ins.recommendation}</div>
          )}
          <Evidence items={ins.evidence} />
        </div>
        <span className="small" style={{ color: sev.c, fontWeight: 700, whiteSpace: "nowrap" }}>{sev.label}</span>
      </div>
      <div className="flex" style={{ gap: 6, marginTop: 10, flexWrap: "wrap" }}>
        {compact ? (
          <button className="btn btn-outline btn-sm" disabled={busy} onClick={() => act({ status: "acknowledged", feedback: "helpful" })}>Got it 👍</button>
        ) : (
          <>
            <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => act({ status: "actioned", feedback: "helpful" })}>✓ Actioned</button>
            <button className="btn btn-outline btn-sm" disabled={busy} onClick={() => act({ status: "acknowledged" })}>Seen</button>
            <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => act({ status: "dismissed", feedback: "not_helpful" })}>Dismiss</button>
          </>
        )}
      </div>
    </div>
  );
}

function useInsights(params) {
  const [list, setList] = useState(null);
  const [err, setErr] = useState(false);
  const load = () => api.get(`/api/intelligence/insights${params}`).then((d) => setList(d.insights || [])).catch(() => setErr(true));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  const remove = (id) => setList((l) => (l || []).filter((x) => x.id !== id));
  return { list, err, remove };
}

// ---- Manager feed (Command Centre) ----
export function InsightsFeed() {
  const { list, err, remove } = useInsights("?status=open");
  const [showAll, setShowAll] = useState(false);
  const [gen, setGen] = useState(false);

  const regenerate = async () => {
    setGen(true);
    try { await api.post("/api/intelligence/insights/generate", {}); window.location.reload(); }
    catch { setGen(false); }
  };

  if (err) return null;
  if (!list) return <div className="card" style={{ marginBottom: 16 }}><Skeleton h={120} /></div>;

  const wins = list.filter((i) => i.severity === "positive");
  const prio = list.filter((i) => i.severity !== "positive");
  const shownPrio = showAll ? prio : prio.slice(0, 6);

  return (
    <div style={{ marginBottom: 16 }}>
      <div className="spread" style={{ marginBottom: 8 }}>
        <h3 className="card-title" style={{ margin: 0 }}>🧠 What needs your attention</h3>
        <button className="btn btn-ghost btn-sm" onClick={regenerate} disabled={gen} title="Regenerate from the latest calls">
          {gen ? "Refreshing…" : "↻ Refresh"}
        </button>
      </div>
      {prio.length === 0 && wins.length === 0 ? (
        <div className="card"><div className="muted small">Nothing flagged right now — the team's tracking well. New insights appear after the next round of calls.</div></div>
      ) : (
        <>
          {shownPrio.map((i) => <InsightCard key={i.id} ins={i} onFeedback={remove} />)}
          {prio.length > 6 && (
            <button className="btn btn-outline btn-sm" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Show fewer" : `Show ${prio.length - 6} more`}
            </button>
          )}
          {wins.length > 0 && (
            <>
              <div className="muted small" style={{ margin: "12px 0 6px" }}>🎉 WINS TO CELEBRATE</div>
              {wins.map((i) => <InsightCard key={i.id} ins={i} onFeedback={remove} />)}
            </>
          )}
        </>
      )}
    </div>
  );
}

// ---- Rep focus (Today) ----
export function MyFocus() {
  const { list, err, remove } = useInsights("?status=open");
  if (err || !list || list.length === 0) return null;
  const top = list.slice(0, 4);
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3 className="card-title" style={{ marginTop: 0 }}>🧠 Your focus this week</h3>
      {top.map((i) => <InsightCard key={i.id} ins={i} onFeedback={remove} compact />)}
    </div>
  );
}
