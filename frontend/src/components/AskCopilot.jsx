import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useToast } from "./Toast.jsx";

/* Ask RepIQ — voice + text Q&A over the dashboard context, with a scope selector
   (yesterday / this week / this month). The /ask endpoint is role-aware (a rep is answered
   about their own calls, a manager about the whole team) and scope-aware. */
const SCOPES = [
  { v: "yesterday", label: "Yesterday" },
  { v: "week", label: "This week" },
  { v: "month", label: "This month" },
];

export default function AskCopilot({ presets, subtitle, title }) {
  const toast = useToast();
  const chips = presets || ["What did I promise?", "Who should I call back first?", "How am I tracking to target?"];
  const [q, setQ] = useState("");
  const [scope, setScope] = useState("yesterday");
  const [messages, setMessages] = useState([]);
  const [thinking, setThinking] = useState(false);
  const [listening, setListening] = useState(false);
  const recRef = useRef(null);
  const finalRef = useRef("");
  const scopeRef = useRef("yesterday");
  const threadRef = useRef(null);
  useEffect(() => { scopeRef.current = scope; }, [scope]);

  useEffect(() => { const e = threadRef.current; if (e) e.scrollTop = e.scrollHeight; }, [messages, thinking]);
  useEffect(() => () => { try { recRef.current?.abort?.(); } catch { /* ignore */ } }, []);

  const ask = async (text) => {
    const question = (text || "").trim();
    if (!question || thinking) return;
    const sc = scopeRef.current;
    const scopeLabel = (SCOPES.find((s) => s.v === sc) || SCOPES[0]).label.toLowerCase();
    setMessages((m) => [...m, { role: "user", text: question, scope: scopeLabel }]);
    setQ("");
    setThinking(true);
    try {
      const d = await api.post("/api/intelligence/ask", { question, scope: sc });
      setMessages((m) => [...m, { role: "ai", text: d?.answer || "No answer." }]);
    } catch (e) { toast(e.message, "error"); } finally { setThinking(false); }
  };

  const toggleVoice = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { toast("Voice input isn't supported in this browser", "error"); return; }
    if (listening) { try { recRef.current?.stop(); } catch { /* ignore */ } return; }
    const rec = new SR();
    rec.lang = "en-GB"; rec.interimResults = true; rec.continuous = false;
    rec.onresult = (e) => {
      let interim = "", final = "";
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) final += r[0].transcript; else interim += r[0].transcript;
      }
      if (final) { finalRef.current = final.trim(); setQ(final.trim()); } else if (interim) setQ(interim);
    };
    rec.onend = () => { setListening(false); recRef.current = null; const t = finalRef.current.trim(); finalRef.current = ""; if (t) ask(t); };
    rec.onerror = () => {};
    recRef.current = rec; finalRef.current = ""; setListening(true);
    try { rec.start(); } catch { setListening(false); recRef.current = null; }
  };

  return (
    <div className="card ask-card">
      <div className="flex" style={{ gap: 8, fontWeight: 700, fontSize: 15, marginBottom: messages.length ? 12 : 10 }}>
        <span aria-hidden="true">✨</span> {title || "Ask RepIQ"}
        <span className="muted small" style={{ fontWeight: 400 }}>— {subtitle || "your calls, your prospects, your numbers"}</span>
      </div>
      {(messages.length > 0 || thinking) && (
        <div ref={threadRef} style={{ maxHeight: 300, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
          {messages.map((m, i) => (
            <div key={i} style={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "85%",
              background: m.role === "user" ? "var(--accent-grad)" : "var(--surface-2, #f3f4f6)",
              color: m.role === "user" ? "#fff" : "var(--text)", borderRadius: 12, padding: "8px 12px", fontSize: 13.5, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
              {m.text}{m.role === "user" && m.scope ? <span style={{ opacity: 0.75, fontSize: 11 }}> · {m.scope}</span> : null}
            </div>
          ))}
          {thinking && <div className="muted small" style={{ fontStyle: "italic" }}>RepIQ is thinking…</div>}
        </div>
      )}
      <form className="flex" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <input className="input" style={{ flex: 1, minWidth: 120 }} value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Ask anything…" aria-label="Ask RepIQ" />
        <select className="input" value={scope} onChange={(e) => setScope(e.target.value)}
          style={{ width: "auto", flex: "0 0 auto" }} aria-label="Which calls to ask about" title="Which calls to ask about">
          {SCOPES.map((s) => <option key={s.v} value={s.v}>{s.label}</option>)}
        </select>
        <button type="button" onClick={toggleVoice} className="btn btn-outline" title={listening ? "Stop" : "Ask by voice"}
          style={listening ? { color: "#fff", background: "var(--red)", borderColor: "var(--red)" } : {}} aria-label="Ask by voice">🎤</button>
        <button className="btn btn-primary" type="submit" disabled={thinking || !q.trim()}>Ask</button>
      </form>
      <div className="flex" style={{ flexWrap: "wrap", gap: 6, marginTop: 10 }}>
        {chips.map((p) => (
          <button key={p} className="btn btn-ghost btn-sm" onClick={() => ask(p)} disabled={thinking}>{p}</button>
        ))}
      </div>
    </div>
  );
}
