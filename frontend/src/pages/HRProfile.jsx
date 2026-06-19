import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, useOutletContext } from "react-router-dom";
import api from "../api";
import { Avatar, Spinner, EmptyState } from "../components/ui.jsx";
import { useToast } from "../components/Toast.jsx";

// Labels for the fields the HR module currently exposes. Only fields the viewer is permitted
// to see come back from the API, so we simply render whatever keys are present.
const PERSONAL_LABELS = {
  preferred_name: "Known as",
  title: "Title",
  first_name: "First name",
  middle_name: "Middle name",
  last_name: "Last name",
  dob: "Date of birth",
  sex: "Sex",
  gender_identity: "Gender identity",
  nationality: "Nationality",
  ni_number: "NI number",
  about: "About",
};
const CONTACT_LABELS = {
  personal_email: "Personal email",
  personal_mobile: "Personal mobile",
  addr_line1: "Address line 1",
  addr_line2: "Address line 2",
  town: "Town / city",
  county: "County",
  postcode: "Postcode",
  country: "Country",
  preferred_contact_method: "Preferred contact",
  work_email: "Work email",
  work_phone: "Work phone",
};
const EMERGENCY_LABELS = {
  full_name: "Name",
  relation: "Relationship",
  phone_primary: "Primary phone",
  phone_secondary: "Secondary phone",
  email: "Email",
  address: "Address",
  notes: "Notes",
};
// Role: job_title + reports_to_name are read-only context; the editable set is below.
const ROLE_VIEW_LABELS = {
  job_title: "Job title",
  reports_to_name: "Reports to",
  department: "Department",
  grade: "Grade / band",
  role_effective_date: "In role since",
};
const ROLE_EDIT_FIELDS = ["reports_to", "department", "grade", "role_effective_date"];
const CONTRACT_LABELS = {
  contract_type: "Contract type",
  working_pattern: "Working pattern",
  weekly_hours: "Weekly hours",
  fte: "FTE",
  start_date: "Start date",
  continuous_service_date: "Continuous service date",
  probation_end_date: "Probation ends",
  notice_period: "Notice period",
  work_location: "Work location",
};
const SELECT_OPTIONS = {
  contract_type: ["Permanent", "Fixed-term", "Contractor", "Apprentice", "Zero-hours"],
  working_pattern: ["Full-time", "Part-time"],
  work_location: ["Office", "Hybrid", "Remote"],
};
const DATE_KEYS = new Set(["dob", "role_effective_date", "start_date", "continuous_service_date", "probation_end_date"]);
// Endpoint + payload-source mapping for the editable sections.
const SAVE_PATH = { personal: "personal", contact: "contact", role: "role", contract: "contract-details", holiday: "holiday" };

// Sections that are part of the wider HR roadmap (brief §12) but not yet wired to data.
// Shown so the profile reads as the full record and grows in place as each phase lands.
const SOON_TABS = [
  ["absence", "Sick & absence", "Absence records, return-to-work and Bradford factor."],
  ["reviews", "Performance & reviews", "1-to-1s, probation and review cycles."],
  ["documents", "Documents", "Contracts, right-to-work and signed policies."],
  ["assets", "Assets", "Company equipment issued to this person."],
  ["training", "Training & qualifications", "Courses, certifications and renewals."],
];

function fmtDate(v) {
  if (!v) return "—";
  try {
    const d = new Date(v);
    if (!isNaN(d)) return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  } catch { /* ignore */ }
  return v;
}

function FieldGrid({ data, labels }) {
  const keys = Object.keys(labels).filter((k) => k in (data || {}));
  if (!keys.length) return <div className="muted small">No details recorded.</div>;
  return (
    <div className="hr-field-grid">
      {keys.map((k) => (
        <div key={k} className="hr-field">
          <div className="hr-field-label">{labels[k]}</div>
          <div className="hr-field-value">
            {DATE_KEYS.has(k) ? fmtDate(data[k]) : (data[k] != null && data[k] !== "" ? String(data[k]) : "—")}
          </div>
        </div>
      ))}
    </div>
  );
}

function EditGrid({ labels, draft, setDraft, userOptions }) {
  const keys = Object.keys(labels).filter((k) => k in draft);
  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  return (
    <div className="hr-field-grid">
      {keys.map((k) => (
        <div key={k} className="hr-field">
          <label className="hr-field-label" htmlFor={`f-${k}`}>{labels[k]}</label>
          {k === "about" ? (
            <textarea id={`f-${k}`} className="input" rows={3} value={draft[k] || ""} onChange={(e) => set(k, e.target.value)} />
          ) : k === "reports_to" ? (
            <select id={`f-${k}`} className="input" value={draft[k] ?? ""} onChange={(e) => set(k, e.target.value || null)}>
              <option value="">— none —</option>
              {(userOptions || []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          ) : SELECT_OPTIONS[k] ? (
            <select id={`f-${k}`} className="input" value={draft[k] || ""} onChange={(e) => set(k, e.target.value)}>
              <option value="">—</option>
              {SELECT_OPTIONS[k].map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : (
            <input id={`f-${k}`} className="input"
              type={DATE_KEYS.has(k) ? "date" : (k === "weekly_hours" || k === "fte" ? "number" : "text")}
              step={k === "fte" ? "0.1" : undefined}
              value={(draft[k] ?? "") === null ? "" : (draft[k] || "")} onChange={(e) => set(k, e.target.value)} />
          )}
        </div>
      ))}
    </div>
  );
}

const ROLE_EDIT_LABELS = {
  reports_to: "Reports to", department: "Department", grade: "Grade / band", role_effective_date: "In role since",
};

export default function HRProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { user: me } = useOutletContext() || {};
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("summary");
  const [editing, setEditing] = useState(null);   // "personal" | "contact" | "role" | "contract" | null
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);
  const [userOptions, setUserOptions] = useState([]);   // for the "reports to" picker (admin)

  const canEdit = me && (me.role === "admin" || Number(me.id) === Number(id));
  const canSeePay = me && (me.role === "admin" || (me.scopes || []).includes("financial"));

  const load = () => {
    setLoading(true);
    api.get(`/api/v1/hr/employees/${id}`)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e.message || "Could not load profile"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const s = data?.summary || {};

  const tabs = useMemo(() => {
    const t = [["summary", "Summary"]];
    if (data?.personal) t.push(["personal", "Personal"]);
    if (data?.contact) t.push(["contact", "Contact"]);
    if (data?.role) t.push(["role", "Role"]);
    if (data?.contractDetails) t.push(["contract", "Contract"]);
    if (data?.holiday) t.push(["holiday", "Holiday"]);
    if (data?.emergencyContacts !== undefined) t.push(["emergency", "Emergency contacts"]);
    if (canSeePay) t.push(["pay", "Pay"]);
    SOON_TABS.forEach(([k, label]) => t.push([k, label]));
    return t;
  }, [data, canSeePay]);

  // The "reports to" picker (role edit, admin only) needs the user list. Load it lazily.
  const ensureUserOptions = () => {
    if (userOptions.length || me?.role !== "admin") return;
    api.get("/api/admin/users")
      .then((us) => setUserOptions((us || []).filter((u) => u.active).map((u) => ({ id: u.id, name: u.name }))))
      .catch(() => {});
  };

  const startEdit = (which, source) => {
    // Build a draft of exactly the editable (present) fields for this section.
    const editKeys =
      which === "personal" ? Object.keys(PERSONAL_LABELS)
      : which === "contact" ? Object.keys(CONTACT_LABELS)
      : which === "role" ? ROLE_EDIT_FIELDS
      : which === "holiday" ? ["allowance_days", "carried_over_days", "includes_bank_holidays"]
      : Object.keys(CONTRACT_LABELS);
    const d = {};
    editKeys.forEach((k) => { if (k in (source || {})) d[k] = source[k] ?? ""; });
    if (which === "role") { ensureUserOptions(); if (!("reports_to" in d)) d.reports_to = source?.reports_to ?? ""; }
    setDraft(d);
    setEditing(which);
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/api/v1/hr/employees/${id}/${SAVE_PATH[editing]}`, draft);
      toast("Saved", "success");
      setEditing(null);
      load();
    } catch (e) {
      toast(e.message || "Could not save", "error");
    } finally {
      setSaving(false);
    }
  };

  const addEmergency = async () => {
    const full_name = window.prompt("Emergency contact name?");
    if (!full_name) return;
    const relation = window.prompt("Relationship? (e.g. Partner, Parent)") || "";
    const phone_primary = window.prompt("Phone number?") || "";
    try {
      await api.post(`/api/v1/hr/employees/${id}/emergency-contacts`, { full_name, relation, phone_primary });
      toast("Emergency contact added", "success");
      load();
    } catch (e) { toast(e.message || "Could not add", "error"); }
  };

  const removeEmergency = async (ecId) => {
    if (!window.confirm("Remove this emergency contact?")) return;
    try {
      await api.del(`/api/v1/hr/employees/${id}/emergency-contacts/${ecId}`);
      toast("Removed", "success");
      load();
    } catch (e) { toast(e.message || "Could not remove", "error"); }
  };

  if (loading) return <div className="page"><Spinner /></div>;
  if (error) return (
    <div className="page">
      <button className="btn btn-outline btn-sm" onClick={() => navigate("/people")}>← Back to People</button>
      <div style={{ marginTop: 20 }}><EmptyState icon="🔒" title="Can't show this profile" sub={error} /></div>
    </div>
  );

  return (
    <div className="page hr-profile">
      <button className="btn btn-ghost btn-sm" style={{ marginBottom: 14 }} onClick={() => navigate("/people")}>← People</button>

      <div className="hr-profile-header card">
        <Avatar name={s.name} color={s.avatarColor} size={72} photo={s.photo} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <h2 style={{ margin: "0 0 2px" }}>{s.knownAs || s.name}</h2>
          {s.knownAs && s.knownAs !== s.name && <div className="muted" style={{ marginTop: -2 }}>{s.name}</div>}
          <div className="hr-chips">
            {s.jobTitle && <span className="chip">{s.jobTitle}</span>}
            {s.platformRole && <span className="chip chip-role">{s.platformRole}</span>}
            {s.status && <span className={"chip " + (s.status === "active" ? "chip-ok" : "chip-muted")}>{s.status}</span>}
            {s.employeeCode && <span className="chip chip-muted">#{s.employeeCode}</span>}
          </div>
        </div>
      </div>

      <div className="hr-tabs">
        {tabs.map(([k, label]) => (
          <button key={k} className={"hr-tab" + (tab === k ? " active" : "")} onClick={() => { setTab(k); setEditing(null); }}>
            {label}
          </button>
        ))}
      </div>

      <div className="card hr-panel">
        {tab === "summary" && (
          <div className="hr-field-grid">
            <div className="hr-field"><div className="hr-field-label">Full name</div><div className="hr-field-value">{s.name || "—"}</div></div>
            <div className="hr-field"><div className="hr-field-label">Known as</div><div className="hr-field-value">{s.preferredName || "—"}</div></div>
            <div className="hr-field"><div className="hr-field-label">Work email</div><div className="hr-field-value">{s.email || "—"}</div></div>
            <div className="hr-field"><div className="hr-field-label">Job title</div><div className="hr-field-value">{s.jobTitle || "—"}</div></div>
            <div className="hr-field"><div className="hr-field-label">Start date</div><div className="hr-field-value">{fmtDate(s.startDate)}</div></div>
            <div className="hr-field"><div className="hr-field-label">Status</div><div className="hr-field-value" style={{ textTransform: "capitalize" }}>{s.status || "—"}</div></div>
          </div>
        )}

        {tab === "personal" && (
          <>
            <div className="spread" style={{ marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>Personal details</h3>
              {canEdit && editing !== "personal" && (
                <button className="btn btn-outline btn-sm" onClick={() => startEdit("personal", data.personal)}>Edit</button>
              )}
            </div>
            {editing === "personal" ? (
              <>
                <EditGrid labels={PERSONAL_LABELS} draft={draft} setDraft={setDraft} />
                <div className="flex" style={{ justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setEditing(null)} disabled={saving}>Cancel</button>
                  <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
                </div>
              </>
            ) : <FieldGrid data={data.personal} labels={PERSONAL_LABELS} />}
          </>
        )}

        {tab === "contact" && (
          <>
            <div className="spread" style={{ marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>Contact details</h3>
              {canEdit && editing !== "contact" && (
                <button className="btn btn-outline btn-sm" onClick={() => startEdit("contact", data.contact)}>Edit</button>
              )}
            </div>
            {editing === "contact" ? (
              <>
                <EditGrid labels={CONTACT_LABELS} draft={draft} setDraft={setDraft} />
                <div className="flex" style={{ justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setEditing(null)} disabled={saving}>Cancel</button>
                  <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
                </div>
              </>
            ) : <FieldGrid data={data.contact} labels={CONTACT_LABELS} />}
          </>
        )}

        {tab === "role" && (
          <>
            <div className="spread" style={{ marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>Role</h3>
              {me?.role === "admin" && editing !== "role" && (
                <button className="btn btn-outline btn-sm" onClick={() => startEdit("role", data.role)}>Edit</button>
              )}
            </div>
            {editing === "role" ? (
              <>
                <EditGrid labels={ROLE_EDIT_LABELS} draft={draft} setDraft={setDraft} userOptions={userOptions} />
                <div className="muted small" style={{ marginTop: 8 }}>Job title is set on the People record.</div>
                <div className="flex" style={{ justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setEditing(null)} disabled={saving}>Cancel</button>
                  <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
                </div>
              </>
            ) : <FieldGrid data={data.role} labels={ROLE_VIEW_LABELS} />}
          </>
        )}

        {tab === "contract" && (
          <>
            <div className="spread" style={{ marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>Contract</h3>
              {me?.role === "admin" && editing !== "contract" && (
                <button className="btn btn-outline btn-sm" onClick={() => startEdit("contract", data.contractDetails)}>Edit</button>
              )}
            </div>
            {editing === "contract" ? (
              <>
                <EditGrid labels={CONTRACT_LABELS} draft={draft} setDraft={setDraft} />
                <div className="flex" style={{ justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setEditing(null)} disabled={saving}>Cancel</button>
                  <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
                </div>
              </>
            ) : <FieldGrid data={data.contractDetails} labels={CONTRACT_LABELS} />}
          </>
        )}

        {tab === "holiday" && data.holiday && (
          <>
            <div className="spread" style={{ marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>Holiday <span className="muted small" style={{ fontWeight: 400 }}>· leave year {data.holiday.leaveYear}</span></h3>
              {me?.role === "admin" && editing !== "holiday" && (
                <button className="btn btn-outline btn-sm" onClick={() => startEdit("holiday", data.holiday)}>Edit allowance</button>
              )}
            </div>
            {editing === "holiday" ? (
              <>
                <div className="hr-field-grid">
                  <div className="hr-field"><label className="hr-field-label">Annual allowance (days)</label>
                    <input className="input" type="number" step="0.5" value={draft.allowance_days ?? ""} onChange={(e) => setDraft((d) => ({ ...d, allowance_days: e.target.value }))} /></div>
                  <div className="hr-field"><label className="hr-field-label">Carried over (days)</label>
                    <input className="input" type="number" step="0.5" value={draft.carried_over_days ?? ""} onChange={(e) => setDraft((d) => ({ ...d, carried_over_days: e.target.value }))} /></div>
                  <div className="hr-field"><label className="hr-field-label">Includes bank holidays</label>
                    <label className="flex" style={{ gap: 8 }}><input type="checkbox" checked={!!draft.includes_bank_holidays} onChange={(e) => setDraft((d) => ({ ...d, includes_bank_holidays: e.target.checked }))} /> <span className="small">Allowance includes bank holidays</span></label></div>
                </div>
                <div className="flex" style={{ justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setEditing(null)} disabled={saving}>Cancel</button>
                  <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
                </div>
              </>
            ) : (
              <>
                <div className="hr-stat-row">
                  <div className="hr-stat"><div className="hr-stat-num">{data.holiday.entitlement ?? "—"}</div><div className="hr-stat-lbl">Entitlement</div></div>
                  <div className="hr-stat"><div className="hr-stat-num">{data.holiday.takenHoliday ?? 0}</div><div className="hr-stat-lbl">Taken</div></div>
                  <div className="hr-stat"><div className="hr-stat-num" style={{ color: (data.holiday.remaining ?? 0) < 0 ? "var(--red)" : "var(--green)" }}>{data.holiday.remaining ?? "—"}</div><div className="hr-stat-lbl">Remaining</div></div>
                  <div className="hr-stat"><div className="hr-stat-num">{data.holiday.takenSick ?? 0}</div><div className="hr-stat-lbl">Sick days</div></div>
                </div>
                <div className="muted small" style={{ margin: "10px 0 4px" }}>
                  Allowance {data.holiday.allowance_days ?? "—"} days{data.holiday.carried_over_days ? ` + ${data.holiday.carried_over_days} carried over` : ""}
                  {data.holiday.includes_bank_holidays != null && ` · ${data.holiday.includes_bank_holidays ? "includes" : "excludes"} bank holidays`}
                </div>
                {(data.holiday.records || []).length > 0 ? (
                  <div style={{ marginTop: 10 }}>
                    <div className="hr-field-label" style={{ marginBottom: 6 }}>This year's leave ({data.holiday.records.length} days)</div>
                    <div className="hr-leave-list">
                      {data.holiday.records.map((r, i) => (
                        <span key={i} className={"hr-leave-pill " + (r.type === "Sick" ? "sick" : r.type === "Holiday" ? "hol" : "other")}>
                          {fmtDate(r.date)}{r.portion === 0.5 ? " ½" : ""}{r.type !== "Holiday" ? ` · ${r.type}` : ""}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : <div className="muted small" style={{ marginTop: 8 }}>No leave recorded this year. Run “Sync holiday from tracker” in Settings to import it.</div>}
              </>
            )}
          </>
        )}

        {tab === "emergency" && (
          <>
            <div className="spread" style={{ marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>Emergency contacts</h3>
              {canEdit && <button className="btn btn-outline btn-sm" onClick={addEmergency}>Add</button>}
            </div>
            {(data.emergencyContacts || []).length === 0 ? (
              <EmptyState icon="🆘" title="No emergency contacts" sub="Add a next of kin in case of emergency." />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {data.emergencyContacts.map((ec) => (
                  <div key={ec.id} className="hr-ec-card">
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600 }}>{ec.full_name} {ec.relation && <span className="muted">· {ec.relation}</span>}</div>
                      <div className="small">{[ec.phone_primary, ec.phone_secondary, ec.email].filter(Boolean).join(" · ") || "—"}</div>
                      {ec.address && <div className="small muted">{ec.address}</div>}
                    </div>
                    {canEdit && <button className="btn btn-ghost btn-sm" onClick={() => removeEmergency(ec.id)}>Remove</button>}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {tab === "pay" && (
          <EmptyState icon="💷" title="Pay & financial"
            sub="Salary, pay history and bank details land in a later HR phase. This tab is visible to you because you hold the financial scope." />
        )}

        {SOON_TABS.some(([k]) => k === tab) && (() => {
          const meta = SOON_TABS.find(([k]) => k === tab);
          return <EmptyState icon="🚧" title={`${meta[1]} — coming soon`} sub={meta[2]} />;
        })()}
      </div>
    </div>
  );
}
