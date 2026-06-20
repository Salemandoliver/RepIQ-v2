import React, { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import api from "../api";
import { useToast } from "../components/Toast.jsx";
import { Skeleton, EmptyState, Modal } from "../components/ui.jsx";

const STATUS_COLOR = { pending: "var(--amber)", approved: "var(--green)", declined: "var(--red)", cancelled: "var(--text-faint)" };

function MyLeave({ me, toast }) {
  const [reqs, setReqs] = useState(null);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.get(`/api/v1/hr/employees/${me.id}/leave-requests`).then((d) => setReqs(d.requests || [])).catch(() => setReqs([]));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const submit = async () => {
    if (!form.start_date) { toast("Pick a start date", "error"); return; }
    setBusy(true);
    try {
      await api.post(`/api/v1/hr/employees/${me.id}/leave-requests`, {
        leave_type: form.leave_type, start_date: form.start_date,
        end_date: form.end_date || form.start_date, start_half: form.start_half, end_half: form.end_half, reason: form.reason,
      });
      toast("Leave request submitted", "success"); setForm(null); load();
    } catch (e) { toast(e.message || "Could not submit", "error"); } finally { setBusy(false); }
  };
  const cancel = async (rid) => {
    if (!window.confirm("Cancel this leave request?")) return;
    try { await api.post(`/api/v1/hr/leave-requests/${rid}/cancel`, {}); toast("Cancelled", "success"); load(); }
    catch (e) { toast(e.message, "error"); }
  };

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="spread" style={{ marginBottom: 10 }}>
        <h3 className="card-title" style={{ margin: 0 }}>My leave</h3>
        <button className="btn btn-primary btn-sm" onClick={() => setForm({ leave_type: "Holiday", start_date: "", end_date: "", start_half: false, end_half: false, reason: "" })}>Request leave</button>
      </div>
      {reqs === null ? <Skeleton h={40} /> : reqs.length === 0 ? (
        <div className="muted small">No leave requests yet. Click “Request leave” to book time off.</div>
      ) : (
        <div>
          {reqs.map((r) => (
            <div key={r.id} className="flex small" style={{ justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
              <span>{new Date(r.startDate).toLocaleDateString("en-GB")}{r.endDate !== r.startDate ? ` – ${new Date(r.endDate).toLocaleDateString("en-GB")}` : ""} · <b>{r.leaveType}</b> · {r.days}d
                {r.reason ? <span className="muted"> — {r.reason}</span> : ""}</span>
              <span className="flex" style={{ gap: 10 }}>
                <span style={{ color: STATUS_COLOR[r.status], fontWeight: 600, textTransform: "capitalize" }}>{r.status}</span>
                {(r.status === "pending" || r.status === "approved") && <a className="hr-action" style={{ padding: 0 }} onClick={() => cancel(r.id)}>Cancel</a>}
              </span>
            </div>
          ))}
        </div>
      )}
      {form && (
        <Modal title="Request leave" onClose={() => setForm(null)}
          footer={<>
            <button className="btn btn-ghost btn-sm" onClick={() => setForm(null)} disabled={busy}>Cancel</button>
            <button className="btn btn-primary btn-sm" onClick={submit} disabled={busy}>{busy ? "Submitting…" : "Submit request"}</button>
          </>}>
          <label className="field"><span>Type</span>
            <select className="input" value={form.leave_type} onChange={(e) => setForm((f) => ({ ...f, leave_type: e.target.value }))}>
              {["Holiday", "Compassionate", "Unpaid", "Appointment", "Other"].map((t) => <option key={t} value={t}>{t}</option>)}
            </select></label>
          <div className="flex" style={{ gap: 10 }}>
            <label className="field" style={{ flex: 1 }}><span>From</span>
              <input className="input" type="date" value={form.start_date} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))} /></label>
            <label className="field" style={{ flex: 1 }}><span>To</span>
              <input className="input" type="date" value={form.end_date} onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))} /></label>
          </div>
          <div className="flex" style={{ gap: 16, margin: "4px 0 8px" }}>
            <label className="flex small" style={{ gap: 6 }}><input type="checkbox" checked={form.start_half} onChange={(e) => setForm((f) => ({ ...f, start_half: e.target.checked }))} /> First day is a half day</label>
            <label className="flex small" style={{ gap: 6 }}><input type="checkbox" checked={form.end_half} onChange={(e) => setForm((f) => ({ ...f, end_half: e.target.checked }))} /> Last day is a half day</label>
          </div>
          <label className="field"><span>Reason (optional)</span>
            <input className="input" value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} /></label>
        </Modal>
      )}
    </div>
  );
}

function Approvals({ toast }) {
  const [reqs, setReqs] = useState(null);
  const load = () => api.get("/api/v1/hr/leave-requests/pending").then((d) => setReqs(d.requests || [])).catch(() => setReqs([]));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  const decide = async (rid, approve) => {
    let note = null;
    if (!approve) { note = window.prompt("Reason for declining (optional):") || ""; }
    try { await api.post(`/api/v1/hr/leave-requests/${rid}/decision`, { approve, note }); toast(approve ? "Approved" : "Declined", "success"); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  if (reqs === null || reqs.length === 0) return null;
  return (
    <div className="card" style={{ marginBottom: 16, borderColor: "var(--amber)" }}>
      <h3 className="card-title" style={{ marginTop: 0 }}>🌴 Pending leave approvals <span className="chip" style={{ background: "var(--amber)", color: "#fff", fontSize: 11 }}>{reqs.length}</span></h3>
      {reqs.map((r) => (
        <div key={r.id} className="flex" style={{ justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--border)", flexWrap: "wrap", gap: 8 }}>
          <span className="small"><b>{r.employeeName}</b> · {r.leaveType} · {new Date(r.startDate).toLocaleDateString("en-GB")}{r.endDate !== r.startDate ? ` – ${new Date(r.endDate).toLocaleDateString("en-GB")}` : ""} ({r.days}d){r.reason ? <span className="muted"> — {r.reason}</span> : ""}</span>
          <span className="flex" style={{ gap: 8 }}>
            <button className="btn btn-primary btn-sm" onClick={() => decide(r.id, true)}>Approve</button>
            <button className="btn btn-outline btn-sm" onClick={() => decide(r.id, false)}>Decline</button>
          </span>
        </div>
      ))}
    </div>
  );
}

// Company holiday calendar — visible to every signed-in user. Reads RepIQ's own leave data.
function leaveIcon(code, weekend) {
  if (code) {
    const c = String(code).toUpperCase();
    if (c === "H") return { ico: "🌴", t: "Holiday" };
    if (c === "H1" || c === "H2" || c === "HD") return { ico: "🏖️", t: "Half day" };
    if (c[0] === "S") return { ico: "🤒", t: "Sick" };
    if (c === "B" || c === "BH") return { ico: "·", t: "Bank holiday", muted: true };
    if (c === "C") return { ico: "🕊️", t: "Compassionate" };
    return { ico: "📋", t: "Leave" };
  }
  if (weekend) return { ico: "·", t: "Weekend", muted: true };
  return { ico: "🧍", t: "Working", work: true };
}
const HOL_LEGEND = [["🧍", "Working"], ["🌴", "Holiday"], ["🏖️", "Half day"], ["🤒", "Sick"],
  ["🕊️", "Compassionate"], ["📋", "Other leave"], ["·", "Weekend / bank holiday"]];

export default function HolidayCalendar() {
  const toast = useToast();
  const { user: me } = useOutletContext() || {};
  const canApprove = me && (me.role === "admin" || me.sales_role === "manager");
  const now = new Date();
  const [ym, setYm] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const [team, setTeam] = useState("all");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/salesiq/holiday-calendar?ym=${ym}&team=${encodeURIComponent(team)}`)
      .then(setData).catch((e) => { toast(e.message, "error"); setData(null); })
      .finally(() => setLoading(false));
  }, [ym, team]);

  const shift = (delta) => {
    let [y, m] = ym.split("-").map(Number);
    m += delta;
    if (m < 1) { y -= 1; m = 12; }
    if (m > 12) { y += 1; m = 1; }
    setYm(`${y}-${String(m).padStart(2, "0")}`);
  };
  const [yy, mm] = ym.split("-").map(Number);
  const label = new Date(yy, mm - 1, 1).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  const todayDay = (yy === now.getFullYear() && mm === now.getMonth() + 1) ? now.getDate() : null;
  const teamOpts = [["all", "All Teams"], ...((data?.teamsAvailable) || []).map((tn) => [tn.toLowerCase(), tn])];

  return (
    <div className="page" style={{ maxWidth: 1180, margin: "0 auto", padding: "28px 22px 60px" }}>
      <div style={{ marginBottom: 6 }}>
        <h1 style={{ margin: 0, fontSize: 24 }}>AdminIQ</h1>
        <div className="muted small">Leave approvals &amp; the company holiday calendar. Performance reviews, 1-to-1s and goals live on each person's profile (People).</div>
      </div>
      <div className="spread" style={{ marginBottom: 18, flexWrap: "wrap", gap: 10, marginTop: 12 }}>
        <h3 style={{ margin: 0 }}>🗓️ Holiday calendar</h3>
        <div className="flex" style={{ gap: 12, flexWrap: "wrap" }}>
          <div className="flex" style={{ gap: 8 }}>
            <button className="btn btn-outline" onClick={() => shift(-1)} aria-label="Previous month">‹</button>
            <strong style={{ fontSize: 16, minWidth: 140, textAlign: "center", alignSelf: "center" }}>{label}</strong>
            <button className="btn btn-outline" onClick={() => shift(1)} aria-label="Next month">›</button>
          </div>
          <select className="input siq-team-sel" value={team} onChange={(e) => setTeam(e.target.value)}>
            {teamOpts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      </div>

      {canApprove && <Approvals toast={toast} />}
      {me && <MyLeave me={me} toast={toast} />}

      <div className="card">
        {loading ? (
          <Skeleton h={320} style={{ borderRadius: 10 }} />
        ) : !data?.found ? (
          <EmptyState icon="🗓️" title="No holiday data for this month" sub="Run the holiday sync in Settings → HR Import once, then it refreshes automatically." />
        ) : (
          <>
            <div className="hol-cal-wrap">
              <table className="hol-cal">
                <thead>
                  <tr>
                    <th className="hol-corner">Employee</th>
                    {data.days.map((d) => (
                      <th key={d.day} className={(d.weekend ? "we" : "") + (todayDay === d.day ? " today" : "")} title={d.weekday}>
                        <div className="hol-dnum">{d.day}</div>
                        <div className="hol-dwk">{d.weekday[0]}</div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.people.map((p) => (
                    <tr key={p.name}>
                      <td className="hol-name">{p.name}</td>
                      {data.days.map((d) => {
                        const m = leaveIcon(p.cells[d.day], d.weekend);
                        return (
                          <td key={d.day} title={`${p.name} · ${d.day} ${d.weekday} · ${m.t}`}
                            className={"hol-c" + (m.muted ? " mut" : "") + (d.weekend ? " we" : "") + (todayDay === d.day ? " today" : "")}>
                            {m.ico}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex" style={{ gap: 14, flexWrap: "wrap", marginTop: 14 }}>
              {HOL_LEGEND.map(([ico, t]) => (
                <span key={t} className="small muted" style={{ display: "inline-flex", gap: 5, alignItems: "center" }}>{ico} {t}</span>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
