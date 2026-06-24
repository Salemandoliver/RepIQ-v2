import React, { useEffect, useRef, useState } from "react";
import { useOutletContext, Link } from "react-router-dom";
import { api } from "../api";
import { EmptyState } from "../components/ui.jsx";
import WeeklyVideo from "../components/WeeklyVideo.jsx";
import ReviewVideo from "../components/ReviewVideo.jsx";
import TeamCompareCard from "../components/TeamCompareCard.jsx";
import LiveCampaigns from "../components/LiveCampaigns.jsx";
import WeeklyForecast from "../components/WeeklyForecast.jsx";
import { MyFocus } from "../components/Insights.jsx";
import { useToast } from "../components/Toast.jsx";

/* Feature 1 (v2) — the Rep / BC co-pilot "Today".
   Action-first: what you promised, what to build, who to call, how to improve — plus a voice
   "Ask RepIQ". Fast: data is pre-computed in the pipeline; cached in-session so returning
   from a call is instant. */

const PLAN_TTL = 10 * 60 * 1000;
const cacheKey = (uid) => `calliq_plan_${uid || "me"}`;
function readCache(uid) {
  try {
    const r = sessionStorage.getItem(cacheKey(uid));
    if (r) { const o = JSON.parse(r); if (Date.now() - o.at < PLAN_TTL) return o.data; }
  } catch { /* ignore */ }
  return null;
}
function writeCache(uid, d) {
  try { sessionStorage.setItem(cacheKey(uid), JSON.stringify({ data: d, at: Date.now() })); } catch { /* ignore */ }
}

const gbp = (n) => n == null ? "—" : "£" + Math.round(n).toLocaleString("en-GB");
const ragColor = (r) => ({ green: "var(--green)", amber: "var(--amber)", red: "var(--red)" }[r] || "var(--text-soft)");

function ProgressBar() {
  const [p, setP] = useState(8);
  useEffect(() => {
    const id = setInterval(() => setP((x) => Math.min(92, x + Math.random() * 16)), 170);
    return () => clearInterval(id);
  }, []);
  return (
    <div style={{ height: 4, background: "#e9ebef", borderRadius: 3, overflow: "hidden", margin: "14px 0 22px" }}>
      <div style={{ width: `${p}%`, height: "100%", background: "var(--accent-grad)", transition: "width .2s ease" }} />
    </div>
  );
}

/* --- Ask RepIQ (voice + text) --- */
const PRESETS = ["What did I promise yesterday?", "Who should I call back first?", "How am I tracking to target?"];
function AskCopilot() {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [scope, setScope] = useState("yesterday");
  const [messages, setMessages] = useState([]);
  const [thinking, setThinking] = useState(false);
  const [listening, setListening] = useState(false);
  const recRef = useRef(null);
  const finalRef = useRef("");
  const threadRef = useRef(null);

  useEffect(() => { const e = threadRef.current; if (e) e.scrollTop = e.scrollHeight; }, [messages, thinking]);
  useEffect(() => () => { try { recRef.current?.abort?.(); } catch { /* ignore */ } }, []);

  const ask = async (text) => {
    const question = (text || "").trim();
    if (!question || thinking) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setQ("");
    setThinking(true);
    try {
      const d = await api.post("/api/intelligence/ask", { question, scope });
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
        <span aria-hidden="true">✨</span> Ask RepIQ
        <span className="muted small" style={{ fontWeight: 400 }}>— your day, your calls, your prospects</span>
      </div>
      {(messages.length > 0 || thinking) && (
        <div ref={threadRef} style={{ maxHeight: 280, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
          {messages.map((m, i) => (
            <div key={i} style={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "85%",
              background: m.role === "user" ? "var(--accent-grad)" : "var(--surface-2, #f3f4f6)",
              color: m.role === "user" ? "#fff" : "var(--text)", borderRadius: 12, padding: "8px 12px", fontSize: 13.5, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
              {m.text}
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
          <option value="yesterday">Yesterday</option>
          <option value="week">This week</option>
          <option value="month">This month</option>
        </select>
        <button type="button" onClick={toggleVoice} className="btn btn-outline" title={listening ? "Stop" : "Ask by voice"}
          style={listening ? { color: "#fff", background: "var(--red)", borderColor: "var(--red)" } : {}} aria-label="Ask by voice">🎤</button>
        <button className="btn btn-primary" type="submit" disabled={thinking || !q.trim()}>Ask</button>
      </form>
      <div className="flex" style={{ flexWrap: "wrap", gap: 6, marginTop: 10 }}>
        {PRESETS.map((p) => (
          <button key={p} className="btn btn-ghost btn-sm" onClick={() => ask(p)} disabled={thinking}>{p}</button>
        ))}
      </div>
    </div>
  );
}

/* --- persisted UI state (collapse + "being actioned" highlight) --- */
const COL_KEY = "calliq_open_v2";   // stores explicit open=true; default is rolled up
const ACT_KEY = "calliq_actioned_v1";
function loadMap(key) { try { return JSON.parse(localStorage.getItem(key) || "{}"); } catch { return {}; } }
function saveMap(key, m) { try { localStorage.setItem(key, JSON.stringify(m)); } catch { /* ignore */ } }

/* --- a clickable action row: tap anywhere to mark it "being actioned" (highlighted),
   tap again to clear back to white. "Open call" doesn't trigger the toggle. --- */
function ActionRow({ icon, company, text, callId, first, itemKey, actioned, onToggle }) {
  const on = !!actioned[itemKey];
  return (
    <div onClick={() => onToggle(itemKey)} role="button" aria-pressed={on}
      className="flex"
      style={{ gap: 11, alignItems: "flex-start", padding: "11px 12px", cursor: "pointer",
        borderTop: first ? "none" : "1px solid var(--border)",
        background: on ? "rgba(109,40,217,0.10)" : "transparent",
        borderLeft: on ? "3px solid var(--accent, #6d28d9)" : "3px solid transparent",
        borderRadius: 8, transition: "background .12s ease" }}>
      <span style={{ fontSize: 17 }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14 }}><strong>{company}</strong> — {text}</div>
        {on && <div className="small" style={{ color: "var(--accent, #6d28d9)", marginTop: 3, fontWeight: 600 }}>● Being actioned — tap to clear</div>}
      </div>
      <Link to={`/calls/${callId}`} onClick={(e) => e.stopPropagation()} className="btn btn-outline btn-sm" style={{ flexShrink: 0 }}>Open call</Link>
    </div>
  );
}

function Section({ icon, title, count, children, dashed, collapsible = true }) {
  const [open, setOpen] = useState(() => (collapsible ? loadMap(COL_KEY)[title] === true : true));
  const toggle = () => setOpen((o) => {
    const nv = !o;
    if (collapsible) { const m = loadMap(COL_KEY); m[title] = nv; saveMap(COL_KEY, m); }
    return nv;
  });
  return (
    <div className="card" style={dashed ? { borderStyle: "dashed", marginTop: 16 } : { marginTop: 16 }}>
      <div className="flex" onClick={collapsible ? toggle : undefined}
        role={collapsible ? "button" : undefined} aria-expanded={collapsible ? open : undefined}
        style={{ gap: 8, marginBottom: open ? 6 : 0, alignItems: "center", cursor: collapsible ? "pointer" : "default", userSelect: "none" }}>
        {collapsible && (
          <span aria-hidden="true" style={{ fontSize: 11, color: "var(--text-soft)", display: "inline-block",
            transition: "transform .15s ease", transform: open ? "rotate(90deg)" : "rotate(0deg)" }}>▶</span>
        )}
        <span aria-hidden="true">{icon}</span>
        <span style={{ fontWeight: 700, fontSize: 15 }}>{title}</span>
        {count != null && <span className="muted small" style={{ marginLeft: "auto" }}>{count}</span>}
      </div>
      {open && children}
    </div>
  );
}

export default function MorningDashboard() {
  const { user } = useOutletContext() || {};
  const toast = useToast();
  const uid = user?.id;
  const [plan, setPlan] = useState(() => readCache(uid));
  const [loading, setLoading] = useState(!plan);
  const [actioned, setActioned] = useState(loadMap(ACT_KEY));
  const toggleActioned = (key) => setActioned((prev) => {
    const nv = { ...prev };
    if (nv[key]) delete nv[key]; else nv[key] = true;
    saveMap(ACT_KEY, nv);
    return nv;
  });

  const load = (force) => {
    if (!force) { const c = readCache(uid); if (c) { setPlan(c); setLoading(false); return; } }
    setLoading(true);
    api.get("/api/intelligence/plan").then((d) => { setPlan(d); writeCache(uid, d); })
      .catch(() => toast("Couldn't load your day — try refresh", "error"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(false); /* eslint-disable-next-line */ }, [uid]);

  const greeting = (() => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"; })();
  const first = user?.preferred_name || (user?.name || "there").split(" ")[0];

  if (loading && !plan) {
    return (
      <div className="page" style={{ maxWidth: 760, margin: "0 auto", padding: "24px 22px" }}>
        <h1 style={{ margin: 0, fontSize: 26 }}>{greeting}, {first}</h1>
        <div className="muted small">Pulling together your day…</div>
        <ProgressBar />
      </div>
    );
  }
  if (!plan) return <EmptyState icon="📭" title="Couldn't load your day" sub="Try refreshing." />;

  const callbacks = plan.promises.filter((p) => p.type === "callback");
  const emails = plan.promises.filter((p) => p.type === "email");
  const ordered = [...callbacks, ...emails];
  const m = plan.momentum || {};
  // The brief is generated server-side with a fixed "Good morning"; align it to the viewer's
  // local time so it matches the header greeting.
  const brief = (plan.brief || "").replace(/^Good (morning|afternoon|evening)/i, greeting);

  return (
    <div className="page" style={{ maxWidth: 1180, margin: "0 auto", padding: "24px 22px 60px" }}>
      <div className="spread" style={{ alignItems: "flex-start" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26 }}>{greeting}, {first}</h1>
          <div className="muted">{plan.meta.date}</div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => load(true)} disabled={loading}>{loading ? "Refreshing…" : "↻ Refresh"}</button>
      </div>
      {loading && <ProgressBar />}
      <div style={{ display: "flex", gap: 20, alignItems: "flex-start", flexWrap: "wrap", marginTop: 16 }}>
        <div style={{ flex: "1 1 540px", minWidth: 0 }}>

      {/* AI brief */}
      <div className="card" style={{ background: "linear-gradient(135deg,#3b1d6e,#6d28d9)", color: "#fff", border: "none" }}>
        <div style={{ fontSize: 16, fontWeight: 600, lineHeight: 1.5 }}>{brief}</div>
      </div>

      {/* Weekly Forecast — rep commits Data/Cloud/Mobile SOV, then tracks against placed orders */}
      <WeeklyForecast />

      <div style={{ marginTop: 16 }}><AskCopilot /></div>

      <MyFocus />

      <LiveCampaigns />

      <div style={{ marginTop: 16 }}><TeamCompareCard /></div>

      {/* Keep your promises */}
      {ordered.length > 0 && (
        <Section icon="✅" title="Keep your promises" count="from yesterday's calls">
          {ordered.map((p, i) => (
            <ActionRow key={i} icon={p.type === "callback" ? "📞" : "✉️"} company={p.company} text={p.text}
              callId={p.callId} first={i === 0} itemKey={`prom:${p.callId}:${p.text}`}
              actioned={actioned} onToggle={toggleActioned} />
          ))}
        </Section>
      )}

      {/* Proposals to build */}
      {plan.proposals.length > 0 && (
        <Section icon="📄" title="Proposals to build" count={`${plan.proposals.length} due`}>
          {plan.proposals.map((p, i) => (
            <ActionRow key={i} icon="🏢" company={p.company} text={p.text} callId={p.callId} first={i === 0}
              itemKey={`prop:${p.callId}:${p.text}`} actioned={actioned} onToggle={toggleActioned} />
          ))}
        </Section>
      )}

      {/* Missing info to chase */}
      {plan.missingInfo.length > 0 && (
        <Section icon="❓" title="Details to chase" count="capture on your next call">
          {plan.missingInfo.map((p, i) => (
            <ActionRow key={i} icon="🔎" company={p.company} text={p.text} callId={p.callId} first={i === 0}
              itemKey={`miss:${p.callId}:${p.text}`} actioned={actioned} onToggle={toggleActioned} />
          ))}
        </Section>
      )}

      {/* Today's priority calls — Stage 2 */}
      <Section icon="🎯" title="Today's priority calls" dashed>
        <div className="muted small" style={{ lineHeight: 1.55 }}>{plan.priorityCalls.message}</div>
      </Section>

      {/* Coaching focus */}
      {(plan.coachingFocus || plan.quickWins.length > 0) && (
        <Section icon="💡" title="Coaching focus" count="real sales calls only">
          {plan.coachingFocus && (
            <div style={{ background: "var(--surface-2, #f3f4f6)", borderRadius: 10, padding: "11px 13px", fontSize: 14, lineHeight: 1.5 }}>
              <strong>One thing today:</strong> {plan.coachingFocus}
            </div>
          )}
          {plan.quickWins.map((w, i) => (
            <div key={i} className="muted small" style={{ marginTop: 8, lineHeight: 1.5 }}>→ {w}</div>
          ))}
        </Section>
      )}

      {/* Momentum */}
      {m && !m.unavailable && (
        <Section icon="📈" title="Your month" count={m.salesMonthLabel || ""}>
          {m.type === "bc" ? (
            <div className="flex" style={{ gap: 12, flexWrap: "wrap" }}>
              <Stat label="Leads" value={`${m.leadsMTD ?? "—"} / ${m.leadTarget ?? "—"}`} color={ragColor(m.rag)} />
              <Stat label="F2F leads" value={m.f2f ?? "—"} />
              <Stat label="GM" value={gbp(m.gmGenerated)} />
              <Stat label="Orders signed" value={m.ordersSigned ?? "—"} color={m.ordersSigned ? "var(--green)" : null} />
              <Stat label="Days left" value={m.daysRemaining ?? "—"} sub={m.leaveDays > 0 ? `−${m.leaveDays} leave` : null} />
              <Stat label="To target" value={m.leadPct != null ? `${m.leadPct}%` : "—"} color={ragColor(m.rag)} />
            </div>
          ) : (
            <>
              <div className="flex" style={{ gap: 12, flexWrap: "wrap" }}>
                <Stat label="Data SOV" value={gbp(m.dataSov)} />
                <Stat label="Cloud SOV" value={gbp(m.cloudSov)} />
                <Stat label="Mobile SOV" value={gbp(m.mobileSov)} />
                <Stat label="GM" value={gbp(m.gmMTD)} />
                <Stat label="Orders" value={m.ordersMTD ?? "—"} />
                <Stat label="Days left" value={m.daysRemaining ?? "—"} sub={m.leaveDays > 0 ? `−${m.leaveDays} leave` : null} />
                <Stat label="Pending" value={m.pendingCount ?? "—"} sub={m.pendingSov ? gbp(m.pendingSov) : null} color={m.pendingCount ? "var(--amber)" : null} />
              </div>
              {m.predictor?.projectedFinishPct != null && (
                <div className="small" style={{ marginTop: 12, padding: "10px 12px", borderRadius: 10, background: m.predictor.rag === "green" ? "rgba(34,197,94,0.1)" : m.predictor.rag === "amber" ? "rgba(245,158,11,0.1)" : "rgba(239,68,68,0.1)" }}>
                  At your current pace you'll finish at <b style={{ color: ragColor(m.predictor.rag) }}>{m.predictor.projectedFinishPct}%</b> of target{m.predictor.gapToTarget > 0 ? ` — ${gbp(m.predictor.gapToTarget)} to go` : ""}.
                </div>
              )}
              {m.pendingCount > 0 && m.withPendingPct != null && (
                <div className="small" style={{ marginTop: 8, padding: "10px 12px", borderRadius: 10, background: "var(--surface-2, #f3f4f6)" }}>
                  Keep this pace and close your {m.pendingCount} pending order{m.pendingCount === 1 ? "" : "s"} and you'll finish at <b style={{ color: m.withPendingPct >= 100 ? "var(--green)" : "var(--amber)" }}>{m.withPendingPct}%</b> of target.
                </div>
              )}
            </>
          )}
        </Section>
      )}
        </div>
        <aside style={{ flex: "0 1 360px", minWidth: 280, marginLeft: "0.5cm", position: "sticky", top: 24 }}>
          <ReviewVideo />
          <WeeklyVideo />
        </aside>
      </div>
    </div>
  );
}

function Stat({ label, value, sub, color }) {
  return (
    <div style={{ flex: "1 1 110px", background: "#fff", border: "1px solid var(--border)", borderRadius: 10, padding: "10px 12px" }}>
      <div className="muted small">{label}</div>
      <div style={{ fontSize: 20, fontWeight: 800, color: color || "var(--text)" }}>{value}</div>
      {sub && <div className="muted small">{sub}</div>}
    </div>
  );
}
