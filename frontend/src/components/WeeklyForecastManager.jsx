import React, { useState } from "react";
import { api } from "../api";
import { CollapsibleCard, Modal, Avatar } from "./ui.jsx";
import { useToast } from "./Toast.jsx";
import { useCachedGet } from "../useCachedGet.js";
import { Gauge, KpiTile } from "./Dashboard.jsx";

/* Manager Weekly Forecast dashboard for the Command Centre — team totals (gauges + KPI tiles),
   a per-rep table with reliability, the missing-forecast list, and manager edit/unlock. BCs are
   excluded server-side. */

const money = (n) => `£${Math.round(n || 0).toLocaleString()}`;
const RELC = { green: "var(--green)", amber: "var(--amber)", red: "var(--red)" };
const pctColor = (p) => (p == null ? "var(--text-faint)" : p >= 100 ? "var(--green)" : p >= 70 ? "var(--amber)" : "var(--red)");

function EditModal({ row, onClose, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState({
    data: row.forecast?.data ?? "", cloud: row.forecast?.cloud ?? "", mobile: row.forecast?.mobile ?? "",
  });
  const [unlock, setUnlock] = useState(false);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const r = await api.put(`/api/forecast/rep/${row.userId}`,
        { data: form.data, cloud: form.cloud, mobile: form.mobile, unlock });
      toast("Forecast updated.", "success");
      onSaved(row.userId, r.forecast);
      onClose();
    } catch (e) { toast(e.message || "Couldn't save", "error"); }
    finally { setBusy(false); }
  };
  return (
    <Modal title={`Edit forecast — ${row.name}`} onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save"}</button>
      </>}>
      <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
        {[["data", "Data"], ["cloud", "Cloud"], ["mobile", "Mobile"]].map(([k, l]) => (
          <label key={k} className="field" style={{ flex: "1 1 110px" }}>
            <span>{l} SOV</span>
            <input className="input" type="number" min="0" value={form[k]}
              onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))} />
          </label>
        ))}
      </div>
      <label className="flex" style={{ gap: 8, marginTop: 12, alignItems: "center", fontSize: 13 }}>
        <input type="checkbox" checked={unlock} onChange={(e) => setUnlock(e.target.checked)} />
        Unlock so the rep can re-enter it themselves
      </label>
    </Modal>
  );
}

export default function WeeklyForecastManager({ team }) {
  const url = `/api/forecast/team${team && team !== "all" ? `?team=${encodeURIComponent(team)}` : ""}`;
  const { data, setData } = useCachedGet(url);
  const [edit, setEdit] = useState(null);
  if (!data || !data.totals) return null;

  const t = data.totals;
  const missing = data.missing || [];
  const onSaved = (userId, forecast) => setData((d) => ({
    ...d, reps: d.reps.map((r) => (r.userId === userId ? { ...r, forecast, submitted: true } : r)),
  }));

  return (
    <CollapsibleCard title="🎯 Weekly Forecast" style={{ marginBottom: 16 }}
      actions={<span className="muted small">{data.week?.label} · {data.repCount} reps</span>}>
      {data.salesConfigured === false && (
        <div className="muted small" style={{ marginBottom: 10 }}>Sales Tracker not connected — actuals appear once it's linked.</div>
      )}

      <div className="flex" style={{ gap: 14, flexWrap: "wrap", justifyContent: "space-around", marginBottom: 12 }}>
        <Gauge value={t.pct.overall} label="Overall" sub={`${money(t.actual.total)} / ${money(t.forecast.total)}`} size={150} />
        <Gauge value={t.pct.data} label="Data" sub={money(t.actual.data)} />
        <Gauge value={t.pct.cloud} label="Cloud" sub={money(t.actual.cloud)} />
        <Gauge value={t.pct.mobile} label="Mobile" sub={money(t.actual.mobile)} />
      </div>

      <div className="flex" style={{ gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        <KpiTile label="Team forecast" value={money(t.forecast.total)} sub="Data + Cloud + Mobile" style={{ flex: "1 1 150px" }} />
        <KpiTile label="Placed so far" value={money(t.actual.total)} style={{ flex: "1 1 150px" }} />
        <KpiTile label="Achievement" value={t.pct.overall != null ? `${Math.round(t.pct.overall)}%` : "—"}
          accent={pctColor(t.pct.overall)} style={{ flex: "1 1 150px" }} />
      </div>

      {missing.length > 0 && (
        <div className="siq-note" style={{ marginBottom: 12 }}>
          ⚠️ {missing.length} rep{missing.length > 1 ? "s" : ""} haven't set this week's forecast: {missing.map((m) => m.name).join(", ")}
        </div>
      )}

      <table className="hr-doc-table">
        <thead>
          <tr>
            <th>Rep</th>
            <th style={{ textAlign: "right" }}>Forecast</th>
            <th style={{ textAlign: "right" }}>Placed</th>
            <th style={{ textAlign: "right" }}>%</th>
            <th style={{ textAlign: "right" }} title="Forecast Reliability Score (rolling 8 weeks)">Reliability</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.reps.map((r) => (
            <tr key={r.userId}>
              <td>
                <div className="flex" style={{ gap: 8, alignItems: "center" }}>
                  <Avatar name={r.name} color={r.avatarColor} size={24} />{r.name}
                  {!r.submitted && <span className="muted small">· no forecast</span>}
                </div>
              </td>
              <td style={{ textAlign: "right" }}>{money(r.forecast.total)}</td>
              <td style={{ textAlign: "right" }}>{money(r.actual.total)}</td>
              <td style={{ textAlign: "right", fontWeight: 700, color: pctColor(r.pct.overall) }}>
                {r.pct.overall != null ? `${Math.round(r.pct.overall)}%` : "—"}
              </td>
              <td style={{ textAlign: "right" }}>
                {r.reliabilityScore != null
                  ? <span style={{ fontWeight: 700, color: RELC[r.reliabilityBand] || "var(--text)" }}>{r.reliabilityScore}</span>
                  : <span className="muted small">{r.reliabilityWeeks ? `${r.reliabilityWeeks}/8 wk` : "new"}</span>}
              </td>
              <td style={{ textAlign: "right" }}>
                <button className="btn btn-ghost btn-sm" onClick={() => setEdit(r)}>Edit</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {edit && <EditModal row={edit} onClose={() => setEdit(null)} onSaved={onSaved} />}
    </CollapsibleCard>
  );
}
