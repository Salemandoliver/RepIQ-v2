import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import { Skeleton } from "./ui.jsx";

// The Org Oracle + knowledge library (Intelligence Phase 5). Managers ask cross-rep, org-wide
// questions; answers cite real calls. The library holds mined 'what works' + pinned exemplars.

const EXAMPLES = [
  "Who is strongest at objection handling, and why?",
  "What's working on our Cloud Voice calls right now?",
  "Draft a hiring scorecard from our top performers' patterns.",
  "Who should mentor the team on discovery questions?",
  "Where are we losing deals most often?",
];

function Sources({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="flex" style={{ gap: 6, flexWrap: "wrap", marginTop: 10 }}>
      <span className="muted small">Evidence:</span>
      {items.map((s, i) => (
        <Link key={i} to={`/calls/${s.callId}`} className="siq-chip" style={{ fontSize: 11 }}>▶ {s.label}</Link>
      ))}
    </div>
  );
}

function KnowledgeLibrary() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ title: "", body: "" });
  const load = () => api.get("/api/intelligence/knowledge").then((d) => setData(d.entries || [])).catch(() => setData([]));
  useEffect(() => { load(); }, []);

  const KIND = { mined: "🔬 What works", exemplar: "🏅 Exemplar", note: "📝 Note" };

  const mine = async () => {
    setBusy(true);
    try { const r = await api.post("/api/intelligence/mine", {}); load();
      if (r.reason) alert(r.reason); } catch { /* ignore */ } finally { setBusy(false); }
  };
  const add = async () => {
    if (!form.title.trim()) return;
    await api.post("/api/intelligence/knowledge", { kind: "note", ...form });
    setForm({ title: "", body: "" }); setAdding(false); load();
  };
  const remove = async (id) => { await api.delete(`/api/intelligence/knowledge/${id}`); load(); };

  if (!data) return null;
  return (
    <div style={{ marginTop: 14 }}>
      <div className="spread" style={{ marginBottom: 8 }}>
        <div className="muted small" style={{ fontWeight: 600 }}>📚 KNOWLEDGE LIBRARY — what works</div>
        <div className="flex" style={{ gap: 6 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => setAdding((v) => !v)}>+ Note</button>
          <button className="btn btn-outline btn-sm" onClick={mine} disabled={busy}>{busy ? "Mining…" : "↻ Refresh what-works"}</button>
        </div>
      </div>
      {adding && (
        <div className="siq-note" style={{ marginBottom: 8 }}>
          <input className="input" placeholder="Title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} style={{ marginBottom: 6 }} />
          <textarea className="input" rows={2} placeholder="What works / playbook note" value={form.body} onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))} />
          <div className="flex" style={{ gap: 6, marginTop: 6 }}>
            <button className="btn btn-primary btn-sm" onClick={add}>Save</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </div>
      )}
      {data.length === 0 ? (
        <div className="muted small">No entries yet — run “Refresh what-works” once there are some won and lost calls, or add a note.</div>
      ) : data.map((e) => (
        <div key={e.id} className="siq-note" style={{ marginBottom: 6 }}>
          <div className="spread">
            <b>{KIND[e.kind] || "📝"} · {e.title}</b>
            <a className="hr-action" style={{ padding: 0, cursor: "pointer" }} onClick={() => remove(e.id)}>Remove</a>
          </div>
          {e.body && <div className="small" style={{ marginTop: 3 }}>{e.body}</div>}
          {e.callId && <Link to={`/calls/${e.callId}`} className="siq-chip" style={{ fontSize: 11, marginTop: 6, display: "inline-block" }}>▶ Listen</Link>}
        </div>
      ))}
    </div>
  );
}

export default function OracleAsk() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(true);

  const ask = async (question) => {
    const text = (question ?? q).trim();
    if (!text) return;
    setBusy(true); setRes(null);
    try { setRes(await api.post("/api/intelligence/oracle", { question: text })); }
    catch (e) { setRes({ answer: e.message || "The Oracle hit an error.", sources: [] }); }
    finally { setBusy(false); }
  };

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="spread" style={{ cursor: "pointer" }} onClick={() => setOpen((v) => !v)}>
        <h3 className="card-title" style={{ margin: 0 }}>🔮 Ask the Oracle</h3>
        <button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}>{open ? "▲" : "▼"}</button>
      </div>
      {open && (
        <>
          <div className="muted small" style={{ margin: "4px 0 8px" }}>
            Cross-team questions — strengths, what's working, hiring, mentoring. Answers cite real calls.
          </div>
          <div className="flex" style={{ gap: 8, marginBottom: 8 }}>
            <input className="input" placeholder="Ask anything about the team…" value={q}
              onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()} style={{ flex: 1 }} />
            <button className="btn btn-primary" onClick={() => ask()} disabled={busy}>{busy ? "Thinking…" : "Ask"}</button>
          </div>
          <div className="flex" style={{ gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
            {EXAMPLES.map((ex, i) => (
              <button key={i} className="siq-chip" style={{ cursor: "pointer", fontSize: 11.5 }}
                onClick={() => { setQ(ex); ask(ex); }}>{ex}</button>
            ))}
          </div>
          {busy && <Skeleton h={80} />}
          {res && (
            <div className="siq-note">
              <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{res.answer}</div>
              <Sources items={res.sources} />
              {res.semantic === false && (
                <div className="muted small" style={{ marginTop: 8 }}>
                  💡 Evidence is keyword-matched. Set a Voyage embeddings key to switch on semantic recall for sharper sourcing.
                </div>
              )}
            </div>
          )}
          <KnowledgeLibrary />
        </>
      )}
    </div>
  );
}
