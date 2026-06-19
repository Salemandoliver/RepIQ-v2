import React, { useEffect, useState } from "react";
import { api } from "../api";
import { Spinner } from "./ui.jsx";
import { mmss, formatDuration } from "../utils";

/* Feature 2 — Post-Call AI Coaching Card.
   Fetches /api/intelligence/coaching/{callId}. The "One Thing to Do Differently" is the
   visual centrepiece; outcome logging is one tap. */

function rag(value, [lo, hi], higherBetter) {
  if (value == null) return "var(--text-faint)";
  if (higherBetter === false) return value <= hi ? "var(--green)" : "var(--red)";
  if (higherBetter === true) return value >= lo ? "var(--green)" : "var(--amber)";
  return value >= lo && value <= hi ? "var(--green)" : "var(--amber)";
}

function Metric({ label, children, hint }) {
  return (
    <div style={{ padding: "12px 0", borderTop: "1px solid var(--border)" }}>
      <div className="spread" style={{ alignItems: "baseline" }}>
        <span style={{ fontWeight: 700, fontSize: 13.5 }}>{label}</span>
        <span style={{ fontSize: 13 }}>{children}</span>
      </div>
      {hint && <div className="muted small" style={{ marginTop: 5, lineHeight: 1.45 }}>{hint}</div>}
    </div>
  );
}

const OBJ_LABEL = {
  price: "Price", timing: "Timing", incumbent: "Incumbent provider",
  decision_maker: "Decision maker", not_interested: "Not interested", other: "Other",
};
const ASSESS = {
  handled: { t: "Handled well", c: "var(--green)" },
  partial: { t: "Partially handled", c: "var(--amber)" },
  missed: { t: "Missed", c: "var(--red)" },
};

export default function CoachingCard({ callId, onSeek }) {
  const [card, setCard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null);

  const load = () => api.get(`/api/intelligence/coaching/${callId}`).then(setCard).catch(() => setCard(null)).finally(() => setLoading(false));
  useEffect(() => { setLoading(true); load(); /* eslint-disable-next-line */ }, [callId]);

  const logOutcome = async (value) => {
    setSaving(value);
    try {
      await api.post(`/api/intelligence/calls/${callId}/outcome`, { outcome: value });
      await load();
    } catch { /* toast handled globally */ } finally { setSaving(null); }
  };

  if (loading) return <div className="card flex" style={{ justifyContent: "center", padding: 40 }}><Spinner /></div>;
  if (!card) return null;
  if (!card.ready) {
    return (
      <div className="card">
        <div className="muted small">The coaching card is generated once this call has finished transcribing and scoring{card.status ? ` (currently: ${card.status})` : ""}. Check back in a couple of minutes.</div>
      </div>
    );
  }

  const h = card.header;
  const tl = card.talkListen;
  const q = card.questions;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Header metrics */}
      <div className="card">
        <div className="spread" style={{ alignItems: "flex-start" }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 16 }}>{h.company}</div>
            <div className="muted small">{h.contact} · {formatDuration(h.durationSec)} · {h.activityType}</div>
          </div>
          {h.quality != null && (
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 30, fontWeight: 800, lineHeight: 1,
                color: h.quality >= 70 ? "var(--green)" : h.quality >= 50 ? "var(--amber)" : "var(--red)" }}>
                {Math.round(h.quality)}
              </div>
              <div className="muted small">quality / 100</div>
              {h.qualityVsAvg != null && (
                <div className="small" style={{ fontWeight: 700, marginTop: 2,
                  color: h.qualityVsAvg >= 0 ? "var(--green)" : "var(--red)" }}>
                  {h.qualityVsAvg >= 0 ? "+" : ""}{h.qualityVsAvg} vs avg
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* THE ONE THING — centrepiece */}
      {card.oneThing && (
        <div className="card" style={{ background: "linear-gradient(135deg,#3b1d6e,#6d28d9)", color: "#fff", border: "none" }}>
          <div style={{ textTransform: "uppercase", letterSpacing: 1, fontSize: 11, opacity: 0.85, fontWeight: 700 }}>
            One thing to do differently
          </div>
          <div style={{ fontSize: 19, fontWeight: 700, lineHeight: 1.4, marginTop: 8 }}>{card.oneThing}</div>
        </div>
      )}

      {/* Outcome logging — one tap */}
      <div className="card">
        <div className="card-title">Log the outcome</div>
        <div className="flex" style={{ gap: 8, flexWrap: "wrap" }}>
          {card.outcome.options.map((o) => {
            const active = card.outcome.value === o.value;
            return (
              <button key={o.value} disabled={saving} onClick={() => logOutcome(o.value)}
                className={"btn btn-sm " + (active ? "btn-primary" : "btn-outline")}>
                {o.label}{active ? " ✓" : ""}
              </button>
            );
          })}
        </div>
        {card.outcome.loggedAt && (
          <div className="muted small" style={{ marginTop: 8 }}>Logged — feeds your close rate and the achievement predictor.</div>
        )}
      </div>

      {/* Behavioural breakdown */}
      <div className="card">
        <div className="card-title">How the call went</div>

        <Metric label="Talk / listen"
          hint={tl.note || (tl.repAvg != null ? `Your 30-day average is ${tl.repAvg}%.` : null)}>
          {tl.repPct != null
            ? <span style={{ fontWeight: 700, color: rag(tl.repPct, tl.band, null) }}>{Math.round(tl.repPct)}% you</span>
            : "—"}
          <span className="muted"> · target {tl.band[0]}–{tl.band[1]}%</span>
        </Metric>
        {tl.repPct != null && (
          <div style={{ height: 8, borderRadius: 5, overflow: "hidden", background: "#e9ebef", display: "flex", marginTop: -4, marginBottom: 4 }}>
            <div style={{ width: `${Math.min(100, tl.repPct)}%`, background: rag(tl.repPct, tl.band, null) }} />
          </div>
        )}

        <Metric label="Interruptions"
          hint={card.interruptions.tip || (card.interruptions.repAvg != null ? `Your average is ${card.interruptions.repAvg}.` : null)}>
          <span style={{ fontWeight: 700, color: rag(card.interruptions.count, [0, 1], false) }}>{card.interruptions.count ?? "—"}</span>
        </Metric>

        <Metric label="Questions asked"
          hint={q.note || (q.repAvg != null ? `Your average is ${q.repAvg}.` : null)}>
          <span style={{ fontWeight: 700 }}>{q.total ?? "—"}</span>
          {(q.breakdown.discovery || q.breakdown.closing || q.breakdown.clarifying) ? (
            <span className="muted"> · {q.breakdown.discovery} discovery / {q.breakdown.closing} closing / {q.breakdown.clarifying} clarifying</span>
          ) : null}
        </Metric>

        {card.filler.show && (
          <Metric label="Filler words" hint="Above your usual — worth a light touch on the next call.">
            <span style={{ fontWeight: 700, color: "var(--amber)" }}>{card.filler.count}</span>
          </Metric>
        )}

        {card.energyNote && (
          <Metric label="Energy & pacing">{""}<span className="muted">{card.energyNote}</span></Metric>
        )}
      </div>

      {/* Objection map */}
      {card.objections.length > 0 && (
        <div className="card">
          <div className="card-title">Objection map</div>
          {card.objections.map((o, i) => {
            const a = ASSESS[o.assessment] || ASSESS.partial;
            return (
              <div key={i} style={{ padding: "10px 0", borderTop: i ? "1px solid var(--border)" : "none" }}>
                <div className="spread">
                  <strong style={{ fontSize: 13.5 }}>{OBJ_LABEL[o.type] || o.type}</strong>
                  <span className="small" style={{ fontWeight: 700, color: a.c }}>{a.t}</span>
                </div>
                {o.rep_response && <div className="muted small" style={{ marginTop: 4 }}>You: “{o.rep_response}”</div>}
                {o.suggested && <div className="small" style={{ marginTop: 4, color: "var(--accent, #6d28d9)" }}>Try: {o.suggested}</div>}
              </div>
            );
          })}
        </div>
      )}

      {/* Best moment */}
      {card.bestMoment && (
        <div className="card">
          <div className="card-title">Your best moment</div>
          <div style={{ fontStyle: "italic", lineHeight: 1.5 }}>“{card.bestMoment.quote}”</div>
          {card.bestMoment.reason && <div className="muted small" style={{ marginTop: 6 }}>{card.bestMoment.reason}</div>}
          {card.bestMoment.startSec != null && onSeek && (
            <button className="btn btn-outline btn-sm" style={{ marginTop: 10 }} onClick={() => onSeek(card.bestMoment.startSec)}>
              ▶ Play from {mmss(card.bestMoment.startSec)}
            </button>
          )}
        </div>
      )}

      {/* Strengths + improvements */}
      {(card.strengths.length > 0 || card.improvements.length > 0) && (
        <div className="card">
          <div className="grid2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div>
              <div className="small" style={{ fontWeight: 700, color: "var(--green)", marginBottom: 6 }}>Strengths</div>
              {card.strengths.map((s, i) => <div key={i} className="small" style={{ marginBottom: 6, lineHeight: 1.45 }}>✓ {s}</div>)}
            </div>
            <div>
              <div className="small" style={{ fontWeight: 700, color: "var(--amber)", marginBottom: 6 }}>To work on</div>
              {card.improvements.map((s, i) => <div key={i} className="small" style={{ marginBottom: 6, lineHeight: 1.45 }}>→ {s}</div>)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
