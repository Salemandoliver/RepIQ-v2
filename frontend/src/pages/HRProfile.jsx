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

// Sections that are part of the wider HR roadmap (brief §12) but not yet wired to data.
// Shown so the profile reads as the full record and grows in place as each phase lands.
const SOON_TABS = [
  ["role", "Role", "Job title history, manager, department and role changes."],
  ["contract", "Contract", "Contract type, start date, notice period and working pattern."],
  ["holiday", "Holiday", "Allowance, booked and remaining days, and requests."],
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
            {k === "dob" ? fmtDate(data[k]) : (data[k] != null && data[k] !== "" ? String(data[k]) : "—")}
          </div>
        </div>
      ))}
    </div>
  );
}

function EditGrid({ labels, draft, setDraft }) {
  const keys = Object.keys(labels).filter((k) => k in draft);
  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  return (
    <div className="hr-field-grid">
      {keys.map((k) => (
        <div key={k} className="hr-field">
          <label className="hr-field-label" htmlFor={`f-${k}`}>{labels[k]}</label>
          {k === "about" ? (
            <textarea id={`f-${k}`} className="input" rows={3} value={draft[k] || ""} onChange={(e) => set(k, e.target.value)} />
          ) : (
            <input id={`f-${k}`} className="input" type={k === "dob" ? "date" : "text"}
              value={(draft[k] ?? "") === null ? "" : (draft[k] || "")} onChange={(e) => set(k, e.target.value)} />
          )}
        </div>
      ))}
    </div>
  );
}

export default function HRProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { user: me } = useOutletContext() || {};
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("summary");
  const [editing, setEditing] = useState(null);   // "personal" | "contact" | null
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);

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
    if (data?.emergencyContacts !== undefined) t.push(["emergency", "Emergency contacts"]);
    if (canSeePay) t.push(["pay", "Pay"]);
    SOON_TABS.forEach(([k, label]) => t.push([k, label]));
    return t;
  }, [data, canSeePay]);

  const startEdit = (which, source) => {
    // Build a draft of exactly the editable (present) fields.
    const labels = which === "personal" ? PERSONAL_LABELS : CONTACT_LABELS;
    const d = {};
    Object.keys(labels).forEach((k) => { if (k in (source || {})) d[k] = source[k] ?? ""; });
    setDraft(d);
    setEditing(which);
  };

  const save = async () => {
    setSaving(true);
    try {
      const path = editing === "personal" ? "personal" : "contact";
      await api.put(`/api/v1/hr/employees/${id}/${path}`, draft);
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
