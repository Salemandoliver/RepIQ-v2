import React, { useState } from "react";
import { api } from "../api";
import { useToast } from "./Toast.jsx";
import { useCachedGet } from "../useCachedGet.js";
import { Gauge, ProgressRow } from "./Dashboard.jsx";
import { Chevron } from "./ui.jsx";
import ConsistencyStrip from "./ConsistencyStrip.jsx";

/* Rep-facing Weekly Forecast card (Today). Two modes:
   - ENTRY: three £ inputs (Data / Cloud / Mobile) → submit (locks for the week).
   - PROGRESS: gauges + actual-vs-forecast bars from this week's placed orders. Read-only once
     submitted (only a manager can change it). Renders nothing for non-reps. */

const money = (n) => `£${Math.round(n || 0).toLocaleString()}`;

export default function WeeklyForecast() {
  const toast = useToast();
  const { data, loading, setData } = useCachedGet("/api/forecast/me", { ttl: 5 * 60 * 1000 });
  const [form, setForm] = useState({ data: "", cloud: "", mobile: "" });
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(true);

  if (loading && !data) return null;
  if (!data || data.isRep === false) return null;       // only Sales Reps see this card

  const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) && n >= 0 ? n : 0; };
  const total = num(form.data) + num(form.cloud) + num(form.mobile);

  const submit = async () => {
    setBusy(true);
    try {
      const r = await api.post("/api/forecast/me", { data: num(form.data), cloud: num(form.cloud), mobile: num(form.mobile) });
      setData((d) => ({ ...(d || {}), forecast: r.forecast, achievement: r.achievement, needsSubmit: false }));
      toast("Forecast submitted — locked for the week.", "success");
    } catch (e) { toast(e.message || "Couldn't submit forecast", "error"); }
    finally { setBusy(false); }
  };

  // -------- ENTRY MODE --------
  if (data.needsSubmit) {
    return (
      <div className="card" style={{ marginTop: 16 }}>
        <div className="flex" style={{ gap: 8, marginBottom: 4 }}>
          <span aria-hidden="true">🎯</span>
          <span style={{ fontWeight: 700, fontSize: 15 }}>This week's forecast</span>
          <span className="muted small" style={{ marginLeft: "auto" }}>{data.week}</span>
        </div>
        <div className="muted small" style={{ marginBottom: 12 }}>
          Commit your SOV for the week (£). It locks once submitted — only a manager can change it.
        </div>
        <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
          {[["data", "Data"], ["cloud", "Cloud"], ["mobile", "Mobile"]].map(([k, label]) => (
            <label key={k} className="field" style={{ flex: "1 1 120px" }}>
              <span>{label} SOV</span>
              <input className="input" type="number" min="0" inputMode="decimal" placeholder="£0"
                value={form[k]} onChange={(e) => setForm((ff) => ({ ...ff, [k]: e.target.value }))} />
            </label>
          ))}
        </div>
        <div className="spread" style={{ marginTop: 12, alignItems: "center" }}>
          <div className="muted small">Total forecast: <b style={{ color: "var(--text)" }}>{money(total)}</b></div>
          <button className="btn btn-primary" disabled={busy || total <= 0} onClick={submit}>
            {busy ? "Submitting…" : "Submit forecast"}
          </button>
        </div>
      </div>
    );
  }

  // -------- PROGRESS MODE --------
  const ach = data.achievement || {};
  const f = ach.forecast || {}, a = ach.actual || {}, p = ach.pct || {};
  const pacing = ach.pacing;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="flex" style={{ gap: 8, marginBottom: open ? 12 : 0, alignItems: "center", cursor: "pointer", userSelect: "none" }}
        onClick={() => setOpen((v) => !v)} role="button" aria-expanded={open}>
        <Chevron open={open} />
        <span aria-hidden="true">🎯</span>
        <span style={{ fontWeight: 700, fontSize: 15 }}>This week's forecast</span>
        <span className="muted small" style={{ marginLeft: "auto" }}>{data.week} · 🔒 locked</span>
      </div>
      {open && (<>
      <div className="flex" style={{ gap: 14, flexWrap: "wrap", justifyContent: "space-around", marginBottom: 8 }}>
        <Gauge value={p.overall} label="Overall" sub={`${money(a.total)} / ${money(f.total)}`} size={150} />
        <Gauge value={p.data} label="Data" sub={money(a.data)} />
        <Gauge value={p.cloud} label="Cloud" sub={money(a.cloud)} />
        <Gauge value={p.mobile} label="Mobile" sub={money(a.mobile)} />
      </div>
      {pacing && (
        <div className="small" style={{ textAlign: "center", fontWeight: 600, marginBottom: 10,
          color: pacing.onTrack ? "var(--green)" : "var(--amber)" }}>
          {pacing.onTrack ? "✓ On track" : "↑ Behind pace"} — day {pacing.workingDaysElapsed} of {pacing.workingDaysTotal}, expected ~{pacing.expectedPct}%
        </div>
      )}
      <ProgressRow label="Data (Connectivity)" actual={a.data} forecast={f.data} pct={p.data} />
      <ProgressRow label="Cloud" actual={a.cloud} forecast={f.cloud} pct={p.cloud} />
      <ProgressRow label="Mobile" actual={a.mobile} forecast={f.mobile} pct={p.mobile} />
      {ach.salesConfigured === false && (
        <div className="muted small" style={{ marginTop: 6 }}>Sales Tracker not connected — actuals appear once it's linked.</div>
      )}
      <ConsistencyStrip reliability={data.reliability} />
      </>)}
    </div>
  );
}
