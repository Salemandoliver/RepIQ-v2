import React, { useEffect, useState } from "react";
import { api } from "../api";
import { Modal } from "./ui.jsx";
import { useToast } from "./Toast.jsx";

/* App-level reminder: if a Sales Rep hasn't entered this week's forecast by 11:00 on a weekday
   (and isn't on leave), pop a dismissible modal with inline entry. Reps on leave are skipped
   server-side (status.needsForecast). Non-reps never see it. */

const money = (n) => `£${Math.round(n || 0).toLocaleString()}`;

export default function ForecastReminder() {
  const toast = useToast();
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({ data: "", cloud: "", mobile: "" });
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => { api.get("/api/forecast/status").then(setStatus).catch(() => {}); }, []);

  const now = new Date();
  const afterEleven = now.getHours() >= 11;
  const weekday = now.getDay() >= 1 && now.getDay() <= 5;
  if (!(status?.needsForecast && afterEleven && weekday && !dismissed)) return null;

  const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) && n >= 0 ? n : 0; };
  const total = num(form.data) + num(form.cloud) + num(form.mobile);

  const submit = async () => {
    setBusy(true);
    try {
      await api.post("/api/forecast/me", { data: num(form.data), cloud: num(form.cloud), mobile: num(form.mobile) });
      toast("Forecast submitted — thanks!", "success");
      setStatus((s) => ({ ...s, needsForecast: false }));
    } catch (e) { toast(e.message || "Couldn't submit forecast", "error"); }
    finally { setBusy(false); }
  };

  return (
    <Modal title="🎯 Set this week's forecast" onClose={() => setDismissed(true)}
      footer={
        <div className="flex" style={{ gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={() => setDismissed(true)}>Remind me later</button>
          <button className="btn btn-primary" disabled={busy || total <= 0} onClick={submit}>
            {busy ? "Submitting…" : "Submit forecast"}
          </button>
        </div>
      }>
      <div className="muted small" style={{ marginBottom: 12 }}>
        It's {status.week} and your forecast isn't in yet. Commit your SOV (£) for the week — it locks
        once submitted, and only a manager can change it afterward.
      </div>
      <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
        {[["data", "Data"], ["cloud", "Cloud"], ["mobile", "Mobile"]].map(([k, l]) => (
          <label key={k} className="field" style={{ flex: "1 1 110px" }}>
            <span>{l} SOV</span>
            <input className="input" type="number" min="0" inputMode="decimal" placeholder="£0"
              value={form[k]} onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))} />
          </label>
        ))}
      </div>
      <div className="small" style={{ marginTop: 10 }}>Total: <b>{money(total)}</b></div>
    </Modal>
  );
}
