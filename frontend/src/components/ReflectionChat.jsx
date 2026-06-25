import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Modal } from "./ui.jsx";
import { useToast } from "./Toast.jsx";
import { speak, stopSpeaking } from "./tts.js";

/* The reflection dialogue — a voice + text coaching chat with the review's presenter (Oliver/Gary).
   Speech-to-text in (reuses the browser mic), and the presenter's replies are spoken back (presenter
   voice via backend TTS, browser voice as fallback). On completion it shows the summary + commitments. */

export default function ReflectionChat({ videoId, presenter = "Oliver", onClose, onComplete }) {
  const toast = useToast();
  const [r, setR] = useState(null);          // the reflection (turns/status/summary/commitments)
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [listening, setListening] = useState(false);
  const [speakOn, setSpeakOn] = useState(true);     // speak the presenter's replies
  const [voiceMode, setVoiceMode] = useState(false); // hands-free: auto-listen after it speaks
  const threadRef = useRef(null);
  const recRef = useRef(null);
  const finalRef = useRef("");
  const voiceModeRef = useRef(false);
  const speakOnRef = useRef(true);
  useEffect(() => { voiceModeRef.current = voiceMode; }, [voiceMode]);
  useEffect(() => { speakOnRef.current = speakOn; }, [speakOn]);

  const turns = r?.turns || [];
  const done = r?.status === "complete";
  const lastAi = [...turns].reverse().find((t) => t.role === "ai");

  // Load (or resume) the reflection; speak the opening line.
  useEffect(() => {
    let live = true;
    api.get(`/api/reflection/video/${videoId}`).then((d) => {
      if (!live) return;
      setR(d.reflection); setLoading(false);
      const ai = [...(d.reflection?.turns || [])].reverse().find((t) => t.role === "ai");
      if (ai && speakOnRef.current) speak(ai.text, presenter);
    }).catch((e) => { if (live) { setLoading(false); toast(e.message || "Couldn't open the reflection", "error"); } });
    return () => { live = false; stopSpeaking(); try { recRef.current?.abort?.(); } catch { /* ignore */ } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  useEffect(() => { const e = threadRef.current; if (e) e.scrollTop = e.scrollHeight; }, [turns.length, thinking]);

  const startListening = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { if (!voiceModeRef.current) toast("Voice input isn't supported in this browser", "error"); return; }
    if (listening) { try { recRef.current?.stop(); } catch { /* ignore */ } return; }
    const rec = new SR();
    rec.lang = "en-GB"; rec.interimResults = true; rec.continuous = false;
    rec.onresult = (e) => {
      let interim = "", fin = "";
      for (let i = 0; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) fin += res[0].transcript; else interim += res[0].transcript;
      }
      if (fin) { finalRef.current = fin.trim(); setInput(fin.trim()); } else if (interim) setInput(interim);
    };
    rec.onend = () => { setListening(false); recRef.current = null; const t = finalRef.current.trim(); finalRef.current = ""; if (t) send(t); };
    rec.onerror = () => { setListening(false); };
    recRef.current = rec; finalRef.current = ""; setListening(true);
    try { rec.start(); } catch { setListening(false); recRef.current = null; }
  };

  const send = async (text) => {
    const t = (text ?? input).trim();
    if (!t || thinking || done) return;
    stopSpeaking();
    setR((prev) => ({ ...prev, turns: [...(prev?.turns || []), { role: "rep", text: t }] }));
    setInput(""); setThinking(true);
    try {
      const d = await api.post(`/api/reflection/${r.id}/message`, { text: t });
      setR(d.reflection);
      if (speakOnRef.current && d.message) {
        speak(d.message, presenter, () => { if (voiceModeRef.current && !d.done) startListening(); });
      } else if (voiceModeRef.current && !d.done) {
        startListening();
      }
      if (d.done) onComplete && onComplete(d.reflection);
    } catch (e) { toast(e.message || "Couldn't send", "error"); }
    finally { setThinking(false); }
  };

  return (
    <Modal title={`💬 Reflect with ${presenter}`} onClose={() => { stopSpeaking(); onClose && onClose(); }} wide>
      <div className="muted small" style={{ marginBottom: 10 }}>
        A short, honest chat to help you get the most from your review. Shared with your manager to support you — not to judge.
      </div>

      {loading ? (
        <div className="muted small" style={{ padding: 20, textAlign: "center" }}>Opening your reflection…</div>
      ) : (
        <>
          <div ref={threadRef} style={{ maxHeight: 340, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
            {turns.map((t, i) => (
              <div key={i} style={{
                alignSelf: t.role === "rep" ? "flex-end" : "flex-start", maxWidth: "85%",
                background: t.role === "rep" ? "var(--accent-grad)" : "var(--surface-2, #f3f4f6)",
                color: t.role === "rep" ? "#fff" : "var(--text)",
                borderRadius: 12, padding: "9px 13px", fontSize: 13.5, lineHeight: 1.5, whiteSpace: "pre-wrap",
              }}>{t.text}</div>
            ))}
            {thinking && <div className="muted small" style={{ fontStyle: "italic" }}>{presenter} is thinking…</div>}
          </div>

          {done ? (
            <div className="siq-note" style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.25)", color: "var(--text)" }}>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>✓ Reflection complete</div>
              {r.summary && <div className="small" style={{ marginBottom: 8 }}>{r.summary}</div>}
              {(r.commitments || []).length > 0 && (
                <div className="small">
                  <b>Your commitments:</b>
                  <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                    {r.commitments.map((c, i) => <li key={i}>{c.text}{c.target ? ` — ${c.target}` : ""}</li>)}
                  </ul>
                </div>
              )}
              <div style={{ textAlign: "right", marginTop: 10 }}>
                <button className="btn btn-primary btn-sm" onClick={() => { stopSpeaking(); onClose && onClose(); }}>Done</button>
              </div>
            </div>
          ) : (
            <>
              <form className="flex" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); send(); }}>
                <input className="input" style={{ flex: 1, minWidth: 120 }} value={input} onChange={(e) => setInput(e.target.value)}
                  placeholder="Type your answer…" aria-label="Your answer" disabled={thinking} />
                <button type="button" onClick={startListening} className="btn btn-outline" title={listening ? "Stop" : "Answer by voice"}
                  style={listening ? { color: "#fff", background: "var(--red)", borderColor: "var(--red)" } : {}} aria-label="Answer by voice">🎤</button>
                <button className="btn btn-primary" type="submit" disabled={thinking || !input.trim()}>Send</button>
              </form>
              <div className="flex" style={{ gap: 14, marginTop: 8, flexWrap: "wrap" }}>
                <label className="flex small" style={{ gap: 6, alignItems: "center", cursor: "pointer" }}>
                  <input type="checkbox" checked={speakOn} onChange={(e) => { setSpeakOn(e.target.checked); if (!e.target.checked) stopSpeaking(); }} />
                  🔊 Speak {presenter}'s replies
                </label>
                <label className="flex small" style={{ gap: 6, alignItems: "center", cursor: "pointer" }}>
                  <input type="checkbox" checked={voiceMode} onChange={(e) => { setVoiceMode(e.target.checked); if (e.target.checked) setSpeakOn(true); }} />
                  🎙️ Hands-free voice mode
                </label>
              </div>
            </>
          )}
        </>
      )}
    </Modal>
  );
}
