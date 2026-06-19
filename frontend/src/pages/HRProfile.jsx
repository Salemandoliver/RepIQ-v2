import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, useOutletContext } from "react-router-dom";
import api from "../api";
import { Spinner, EmptyState, Modal } from "../components/ui.jsx";
import { useToast } from "../components/Toast.jsx";

/* HR employee profile — SafeHR-style layout: a full tab set, each tab laid out as content
   sections with an Actions sidebar. Content is permission-projected by the API; unbuilt
   sections show a placeholder and a few tabs are disabled until their phase lands. */

const PERSONAL_LABELS = {
  preferred_name: "Known as", title: "Title", first_name: "First name", middle_name: "Middle name",
  last_name: "Last name", dob: "Date of birth", sex: "Sex", gender_identity: "Gender identity",
  nationality: "Nationality", ni_number: "NI number", about: "About",
};
const CONTACT_LABELS = {
  personal_email: "Personal email", personal_mobile: "Personal mobile", addr_line1: "Address line 1",
  addr_line2: "Address line 2", town: "Town / city", county: "County", postcode: "Postcode",
  country: "Country", preferred_contact_method: "Preferred contact", work_email: "Work email", work_phone: "Work phone",
};
const ROLE_EDIT_LABELS = { reports_to: "Reports to", department: "Department", grade: "Grade / band", role_effective_date: "In role since" };
const ROLE_EDIT_FIELDS = ["reports_to", "department", "grade", "role_effective_date"];
const CONTRACT_LABELS = {
  contract_type: "Contract type", working_pattern: "Working pattern", weekly_hours: "Weekly hours",
  fte: "FTE", start_date: "Start date", continuous_service_date: "Continuous service date",
  probation_end_date: "Probation ends", notice_period: "Notice period", work_location: "Work location",
};
const SELECT_OPTIONS = {
  contract_type: ["Permanent", "Fixed-term", "Contractor", "Apprentice", "Zero-hours"],
  working_pattern: ["Full-time", "Part-time"],
  work_location: ["Office", "Hybrid", "Remote"],
};
const DATE_KEYS = new Set(["dob", "role_effective_date", "start_date", "continuous_service_date", "probation_end_date"]);
const SAVE_PATH = { personal: "personal", contact: "contact", role: "role", contract: "contract-details", holiday: "holiday" };

// Tab set + order mirrors SafeHR. `true` = disabled (greyed, not selectable) until that phase lands.
const TABS = [
  ["personal", "Personal Details"], ["role", "Role"], ["location", "Location"], ["contract", "Contract"],
  ["pay", "Pay"], ["benefits", "Benefits"], ["hours", "Hours"], ["holiday", "Holiday"],
  ["performance", "Performance"], ["assets", "Assets"], ["documents", "Documents"], ["feedback", "Feedback", true],
  ["absence", "Sick & Absence"], ["training", "Training", true], ["qualifications", "Qualifications", true], ["goals", "Goals"],
];
const SOON = {
  location: "Work location and home address detail will expand in a later HR phase.",
  benefits: "Benefits & perks (pension, healthcare, etc.) are part of a later HR phase.",
  performance: "Performance reviews and 1-to-1s are part of a later HR phase.",
  assets: "Company assets issued to this person will be listed here.",
  documents: "Document storage (contracts, right-to-work) lands with secure file storage.",
  goals: "Goals & objectives are part of a later HR phase.",
};

const Flower = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2.4" strokeLinecap="round" style={{ flex: "0 0 auto" }}>
    <path d="M12 3v18M5 6.5l14 11M19 6.5l-14 11" />
  </svg>
);

function fmtDate(v) {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d) ? v : d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

function DL({ rows }) {
  return (
    <dl className="hr-dl">
      {rows.map(([label, value], i) => (
        <React.Fragment key={i}>
          <dt>{label}</dt>
          <dd>{(value || value === 0) ? value : "—"}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

function Section({ title, children }) {
  return (<div className="hr-col"><h3 className="hr-sec-title">{title}</h3>{children}</div>);
}

function Actions({ items }) {
  const real = (items || []).filter(Boolean);
  if (!real.length) return null;
  return (
    <div className="hr-col">
      <h3 className="hr-sec-title">Actions</h3>
      <div className="hr-actions">
        {real.map((a, i) => a.disabled
          ? <span key={i} className="hr-action disabled" title="Coming in a later phase"><Flower /> {a.label}</span>
          : <a key={i} className="hr-action" onClick={a.onClick}><Flower /> {a.label}</a>)}
      </div>
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

export default function HRProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { user: me } = useOutletContext() || {};
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("personal");
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);
  const [userOptions, setUserOptions] = useState([]);
  const [absForm, setAbsForm] = useState(null);   // record-absence modal
  const [histRows, setHistRows] = useState(null);  // history modal
  const [ecEdit, setEcEdit] = useState(null);      // edit-emergency modal

  const isAdmin = me?.role === "admin";
  const isManager = me?.sales_role === "manager";
  const isSelf = Number(me?.id) === Number(id);
  const canEdit = isAdmin || isSelf;
  const canRecordAbsence = isAdmin || (isManager && !isSelf);

  const load = () => {
    setLoading(true);
    api.get(`/api/v1/hr/employees/${id}`)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e.message || "Could not load profile"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const ensureUserOptions = () => {
    if (userOptions.length || !isAdmin) return;
    api.get("/api/admin/users")
      .then((us) => setUserOptions((us || []).filter((u) => u.active).map((u) => ({ id: u.id, name: u.name }))))
      .catch(() => {});
  };

  const startEdit = (which, source) => {
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
    } catch (e) { toast(e.message || "Could not save", "error"); }
    finally { setSaving(false); }
  };

  const addEmergency = async () => {
    const full_name = window.prompt("Emergency contact name?");
    if (!full_name) return;
    const relation = window.prompt("Relationship? (e.g. Partner, Parent)") || "";
    const phone_primary = window.prompt("Phone number?") || "";
    try {
      await api.post(`/api/v1/hr/employees/${id}/emergency-contacts`, { full_name, relation, phone_primary });
      toast("Emergency contact added", "success"); load();
    } catch (e) { toast(e.message || "Could not add", "error"); }
  };
  const removeEmergency = async (ecId) => {
    if (!window.confirm("Remove this emergency contact?")) return;
    try { await api.del(`/api/v1/hr/employees/${id}/emergency-contacts/${ecId}`); toast("Removed", "success"); load(); }
    catch (e) { toast(e.message || "Could not remove", "error"); }
  };

  const saveAbsence = async () => {
    if (!absForm?.leave_date) { toast("Pick a date", "error"); return; }
    setSaving(true);
    try {
      await api.post(`/api/v1/hr/employees/${id}/leave`, absForm);
      toast("Absence recorded", "success"); setAbsForm(null); load();
    } catch (e) { toast(e.message || "Could not record", "error"); } finally { setSaving(false); }
  };
  const removeLeave = async (leaveId) => {
    if (!window.confirm("Remove this absence record?")) return;
    try { await api.del(`/api/v1/hr/employees/${id}/leave/${leaveId}`); toast("Removed", "success"); load(); }
    catch (e) { toast(e.message || "Could not remove", "error"); }
  };
  const openHistory = async () => {
    try { const r = await api.get(`/api/v1/hr/employees/${id}/history`); setHistRows(r.history || []); }
    catch (e) { toast(e.message || "Could not load history", "error"); }
  };
  const saveEcEdit = async () => {
    setSaving(true);
    try {
      await api.put(`/api/v1/hr/employees/${id}/emergency-contacts/${ecEdit.id}`, ecEdit);
      toast("Saved", "success"); setEcEdit(null); load();
    } catch (e) { toast(e.message || "Could not save", "error"); } finally { setSaving(false); }
  };
  const changeJobTitle = async () => {
    const jt = window.prompt("New job title:", s.jobTitle || "");
    if (jt == null) return;
    try { await api.patch(`/api/admin/users/${id}`, { job_title: jt.trim() }); toast("Job title updated", "success"); load(); }
    catch (e) { toast(e.message || "Could not update", "error"); }
  };

  if (loading) return <div className="hr-profile"><Spinner /></div>;
  if (error) return (
    <div className="hr-profile">
      <button className="btn btn-outline btn-sm" onClick={() => navigate("/people")}>← Back to People</button>
      <div style={{ marginTop: 20 }}><EmptyState icon="🔒" title="Can't show this profile" sub={error} /></div>
    </div>
  );

  const s = data.summary || {};
  const p = data.personal || {};
  const c = data.contact || {};
  const ecs = data.emergencyContacts || [];
  const cd = data.contractDetails || {};
  const role = data.role || {};
  const hol = data.holiday;

  const SaveBar = () => (
    <div className="flex" style={{ justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
      <button className="btn btn-ghost btn-sm" onClick={() => setEditing(null)} disabled={saving}>Cancel</button>
      <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
    </div>
  );

  const homeAddress = () => {
    const lines = [c.addr_line1, c.addr_line2, [c.town, c.postcode].filter(Boolean).join(", "), c.country].filter(Boolean);
    return lines.length ? <span style={{ whiteSpace: "pre-line" }}>{lines.join("\n")}</span> : "—";
  };

  function renderTab() {
    // Disabled / unbuilt tabs
    if (SOON[tab]) return <div className="hr-cols"><div className="hr-col"><EmptyState icon="🚧" title={`${TABS.find(([k]) => k === tab)[1]} — coming soon`} sub={SOON[tab]} /></div></div>;

    if (tab === "personal") {
      if (editing === "personal") return <div className="hr-edit"><h3 className="hr-sec-title">Edit personal details</h3><EditGrid labels={PERSONAL_LABELS} draft={draft} setDraft={setDraft} /><SaveBar /></div>;
      if (editing === "contact") return <div className="hr-edit"><h3 className="hr-sec-title">Edit contact details</h3><EditGrid labels={CONTACT_LABELS} draft={draft} setDraft={setDraft} /><SaveBar /></div>;
      const ec = ecs[0];
      return (
        <div className="hr-cols">
          <div className="hr-col">
            <h3 className="hr-sec-title">Personal details</h3>
            <DL rows={[["Sex", p.sex], ["Date of birth", p.dob ? fmtDate(p.dob) : null]]} />
            <h3 className="hr-sec-title" style={{ marginTop: 26 }}>Contact details</h3>
            <DL rows={[["Name", s.name], ["Title", p.title], ["Work email", c.work_email || s.email],
              ["Work telephone", c.work_phone], ["Personal email", c.personal_email],
              ["Personal mobile", c.personal_mobile], ["Home address", homeAddress()]]} />
          </div>
          <Section title="Emergency contact">
            {ec ? (
              <>
                <DL rows={[["Name", ec.full_name], ["Relationship", ec.relation], ["Email", ec.email],
                  ["Phone", ec.phone_primary], ["Mobile", ec.phone_secondary],
                  ["Address", ec.address ? <span style={{ whiteSpace: "pre-line" }}>{ec.address.replace(/, /g, "\n")}</span> : null]]} />
                {canEdit && ecs.length > 1 && <div className="muted small" style={{ marginTop: 8 }}>+{ecs.length - 1} more on file</div>}
                {canEdit && <a className="hr-action" style={{ marginTop: 10 }} onClick={() => removeEmergency(ec.id)}><Flower /> Remove this contact</a>}
              </>
            ) : <div className="muted small">No emergency contact on file.</div>}
          </Section>
          <Actions items={[
            canEdit && { label: "Edit personal details", onClick: () => startEdit("personal", p) },
            canEdit && { label: "Edit contact details", onClick: () => startEdit("contact", c) },
            canEdit && (ec ? { label: "Edit emergency contact", onClick: () => setEcEdit({ ...ec }) } : { label: "Add emergency contact", onClick: addEmergency }),
            canEdit && ec && { label: "Add another emergency contact", onClick: addEmergency },
            isSelf && { label: "Edit employee photo", onClick: () => navigate("/account") },
            canEdit && { label: "Edit about me", onClick: () => startEdit("personal", p) },
            (isAdmin || isManager) && { label: "View personal details history", onClick: openHistory },
          ].filter(Boolean)} />
        </div>
      );
    }

    if (tab === "role") {
      if (editing === "role") return <div className="hr-edit"><h3 className="hr-sec-title">Edit role</h3><EditGrid labels={ROLE_EDIT_LABELS} draft={draft} setDraft={setDraft} userOptions={userOptions} /><div className="muted small" style={{ marginTop: 8 }}>Job title is set on the People record.</div><SaveBar /></div>;
      return (
        <div className="hr-cols">
          <Section title="Job information">
            <DL rows={[["Job title", role.job_title || s.jobTitle], ["Department", role.department],
              ["Grade / band", role.grade], ["In role since", role.role_effective_date ? fmtDate(role.role_effective_date) : null]]} />
          </Section>
          <Section title="Management">
            <DL rows={[["Reports to", role.reports_to_name]]} />
          </Section>
          <Actions items={isAdmin ? [
            { label: "View / edit role", onClick: () => startEdit("role", role) },
            { label: "Change job title", onClick: changeJobTitle },
          ] : []} />
        </div>
      );
    }

    if (tab === "location") {
      return (
        <div className="hr-cols">
          <Section title="Work location"><DL rows={[["Location", cd.work_location], ["Working pattern", cd.working_pattern]]} /></Section>
          <Section title="Home address"><DL rows={[["Address", homeAddress()]]} /></Section>
          <Actions items={isAdmin ? [{ label: "Edit work location", onClick: () => { setTab("contract"); startEdit("contract", cd); } },
            { label: "Edit home address", onClick: () => startEdit("contact", c) }] : []} />
        </div>
      );
    }

    if (tab === "contract" || tab === "hours") {
      if (editing === "contract") return <div className="hr-edit"><h3 className="hr-sec-title">Edit contract</h3><EditGrid labels={CONTRACT_LABELS} draft={draft} setDraft={setDraft} /><SaveBar /></div>;
      if (tab === "hours") {
        return (
          <div className="hr-cols">
            <Section title="Working hours"><DL rows={[["Working pattern", cd.working_pattern], ["Weekly hours", cd.weekly_hours], ["FTE", cd.fte]]} /></Section>
            <Section title="Pattern"><DL rows={[["Contract type", cd.contract_type], ["Location", cd.work_location]]} /></Section>
            <Actions items={isAdmin ? [{ label: "Edit hours", onClick: () => startEdit("contract", cd) }] : []} />
          </div>
        );
      }
      return (
        <div className="hr-cols">
          <Section title="Contract">
            <DL rows={[["Contract type", cd.contract_type], ["Working pattern", cd.working_pattern],
              ["Notice period", cd.notice_period], ["Work location", cd.work_location]]} />
          </Section>
          <Section title="Key dates">
            <DL rows={[["Start date", cd.start_date ? fmtDate(cd.start_date) : null],
              ["Continuous service", cd.continuous_service_date ? fmtDate(cd.continuous_service_date) : null],
              ["Probation ends", cd.probation_end_date ? fmtDate(cd.probation_end_date) : null]]} />
          </Section>
          <Actions items={isAdmin ? [{ label: "View / edit contract", onClick: () => startEdit("contract", cd) }] : []} />
        </div>
      );
    }

    if (tab === "holiday") {
      if (!hol) return <div className="hr-cols"><div className="hr-col"><EmptyState icon="🏖️" title="No holiday data" /></div></div>;
      if (editing === "holiday") return (
        <div className="hr-edit"><h3 className="hr-sec-title">Edit holiday allowance</h3>
          <div className="hr-field-grid">
            <div className="hr-field"><label className="hr-field-label">Annual allowance (days)</label>
              <input className="input" type="number" step="0.5" value={draft.allowance_days ?? ""} onChange={(e) => setDraft((d) => ({ ...d, allowance_days: e.target.value }))} /></div>
            <div className="hr-field"><label className="hr-field-label">Carried over (days)</label>
              <input className="input" type="number" step="0.5" value={draft.carried_over_days ?? ""} onChange={(e) => setDraft((d) => ({ ...d, carried_over_days: e.target.value }))} /></div>
            <div className="hr-field"><label className="hr-field-label">Includes bank holidays</label>
              <label className="flex" style={{ gap: 8 }}><input type="checkbox" checked={!!draft.includes_bank_holidays} onChange={(e) => setDraft((d) => ({ ...d, includes_bank_holidays: e.target.checked }))} /> <span className="small">Allowance includes bank holidays</span></label></div>
          </div><SaveBar />
        </div>
      );
      return (
        <div className="hr-cols">
          <div className="hr-col" style={{ gridColumn: "span 2" }}>
            <h3 className="hr-sec-title">Holiday <span className="muted small" style={{ fontWeight: 400 }}>· leave year {hol.leaveYear}</span></h3>
            <div className="hr-stat-row">
              <div className="hr-stat"><div className="hr-stat-num">{hol.entitlement ?? "—"}</div><div className="hr-stat-lbl">Entitlement</div></div>
              <div className="hr-stat"><div className="hr-stat-num">{hol.takenHoliday ?? 0}</div><div className="hr-stat-lbl">Taken</div></div>
              <div className="hr-stat"><div className="hr-stat-num" style={{ color: (hol.remaining ?? 0) < 0 ? "var(--red)" : "var(--green)" }}>{hol.remaining ?? "—"}</div><div className="hr-stat-lbl">Remaining</div></div>
              <div className="hr-stat"><div className="hr-stat-num">{hol.takenSick ?? 0}</div><div className="hr-stat-lbl">Sick days</div></div>
            </div>
            <div className="muted small" style={{ margin: "12px 0 4px" }}>
              Allowance {hol.allowance_days ?? "—"} days{hol.carried_over_days ? ` + ${hol.carried_over_days} carried over` : ""}
              {hol.includes_bank_holidays != null && ` · ${hol.includes_bank_holidays ? "includes" : "excludes"} bank holidays`}
            </div>
            {(hol.records || []).length > 0 && (
              <div className="hr-leave-list" style={{ marginTop: 8 }}>
                {hol.records.map((r, i) => (
                  <span key={i} className={"hr-leave-pill " + (r.type === "Sick" ? "sick" : r.type === "Holiday" ? "hol" : "other")}>
                    {fmtDate(r.date)}{r.portion === 0.5 ? " ½" : ""}{r.type !== "Holiday" ? ` · ${r.type}` : ""}
                  </span>
                ))}
              </div>
            )}
          </div>
          <Actions items={isAdmin ? [{ label: "Edit allowance", onClick: () => startEdit("holiday", hol) }] : []} />
        </div>
      );
    }

    if (tab === "absence") {
      const recs = hol?.records || [];
      const sick = recs.filter((r) => r.type === "Sick");
      const sickDays = hol?.takenSick ?? 0;
      const otherAbs = recs.filter((r) => r.type !== "Holiday" && r.type !== "Sick");
      const name = s.knownAs || (s.name || "This person").split(" ")[0];
      const absList = recs.filter((r) => r.type !== "Holiday");
      return (
        <div className="hr-cols">
          <Section title="Absence">
            <p style={{ marginTop: 0 }}>{name} has {otherAbs.length ? `${otherAbs.reduce((a, r) => a + (r.portion || 1), 0)} day(s) of other leave` : "no non-holiday absence"} this leave year.</p>
            <p className="muted small">Holiday taken: {hol?.takenHoliday ?? 0} day(s).</p>
            {absList.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <div className="hr-field-label" style={{ marginBottom: 6 }}>Records this year</div>
                {absList.map((r) => (
                  <div key={r.id} className="flex small" style={{ justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                    <span>{fmtDate(r.date)}{r.portion === 0.5 ? " ½" : ""} · <b>{r.type}</b>{r.notes ? <span className="muted"> — {r.notes}</span> : ""}</span>
                    {canRecordAbsence && r.source !== "tracker" && <a className="hr-action" style={{ padding: 0 }} onClick={() => removeLeave(r.id)}>Remove</a>}
                  </div>
                ))}
              </div>
            )}
          </Section>
          <Section title="Sickness">
            <p style={{ marginTop: 0 }}>{name} has been off sick {sick.length} time{sick.length === 1 ? "" : "s"} for a total of {sickDays} day{sickDays === 1 ? "" : "s"} this leave year.</p>
          </Section>
          <Actions items={[
            canRecordAbsence && { label: "Record sickness / absence", onClick: () => setAbsForm({ leave_date: "", leave_type: "Sick", portion: 1.0, notes: "" }) },
            !canRecordAbsence && { label: "Record sickness / absence", disabled: true },
          ]} />
        </div>
      );
    }

    if (tab === "pay") {
      const canSeePay = isAdmin || (me?.scopes || []).includes("financial");
      return <div className="hr-cols"><div className="hr-col">
        <EmptyState icon="💷" title="Pay & financial"
          sub={canSeePay ? "Salary, pay history and bank details land in the financial Pay phase (encrypted, admin-only)." : "Pay information is restricted."} />
      </div></div>;
    }

    return <div className="hr-cols"><div className="hr-col"><EmptyState icon="🚧" title="Coming soon" /></div></div>;
  }

  return (
    <div className="hr-profile">
      <button className="btn btn-ghost btn-sm" style={{ marginBottom: 12 }} onClick={() => navigate("/people")}>← People</button>
      <div className="hr-card">
        <div className="hr-head"><Flower size={20} /> Personal information for {s.name || s.knownAs}</div>
        <div className="hr-subhead">
          {[s.jobTitle, s.teamId ? null : null, s.status].filter(Boolean).join(" · ")}
          {s.knownAs && s.knownAs !== s.name ? ` · known as ${s.knownAs}` : ""}
        </div>
        <div className="hr-tabgrid">
          {TABS.map(([k, label, disabled]) => (
            <button key={k} disabled={disabled}
              className={"hr-tab" + (tab === k ? " active" : "") + (disabled ? " disabled" : "")}
              onClick={() => { if (!disabled) { setTab(k); setEditing(null); } }}>
              {label}
            </button>
          ))}
        </div>
        <div className="hr-body">{renderTab()}</div>
      </div>

      {absForm && (
        <Modal title="Record sickness / absence" onClose={() => setAbsForm(null)}
          footer={<>
            <button className="btn btn-ghost btn-sm" onClick={() => setAbsForm(null)} disabled={saving}>Cancel</button>
            <button className="btn btn-primary btn-sm" onClick={saveAbsence} disabled={saving}>{saving ? "Saving…" : "Record"}</button>
          </>}>
          <label className="field"><span>Date</span>
            <input className="input" type="date" value={absForm.leave_date} onChange={(e) => setAbsForm((f) => ({ ...f, leave_date: e.target.value }))} /></label>
          <label className="field"><span>Type</span>
            <select className="input" value={absForm.leave_type} onChange={(e) => setAbsForm((f) => ({ ...f, leave_type: e.target.value }))}>
              {["Sick", "Holiday", "Compassionate", "Unpaid", "Appointment", "Custom", "Other"].map((t) => <option key={t} value={t}>{t}</option>)}
            </select></label>
          <label className="flex" style={{ gap: 8, margin: "8px 0" }}>
            <input type="checkbox" checked={absForm.portion === 0.5} onChange={(e) => setAbsForm((f) => ({ ...f, portion: e.target.checked ? 0.5 : 1.0 }))} />
            <span className="small">Half day</span></label>
          <label className="field"><span>Notes (optional)</span>
            <input className="input" value={absForm.notes} onChange={(e) => setAbsForm((f) => ({ ...f, notes: e.target.value }))} /></label>
        </Modal>
      )}

      {ecEdit && (
        <Modal title="Edit emergency contact" onClose={() => setEcEdit(null)}
          footer={<>
            <button className="btn btn-ghost btn-sm" onClick={() => setEcEdit(null)} disabled={saving}>Cancel</button>
            <button className="btn btn-primary btn-sm" onClick={saveEcEdit} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
          </>}>
          {[["full_name", "Name"], ["relation", "Relationship"], ["phone_primary", "Phone"], ["phone_secondary", "Mobile"], ["email", "Email"], ["address", "Address"]].map(([k, lbl]) => (
            <label key={k} className="field"><span>{lbl}</span>
              <input className="input" value={ecEdit[k] || ""} onChange={(e) => setEcEdit((x) => ({ ...x, [k]: e.target.value }))} /></label>
          ))}
        </Modal>
      )}

      {histRows && (
        <Modal title="Change history" wide onClose={() => setHistRows(null)}>
          {histRows.length === 0 ? <div className="muted small">No changes recorded yet.</div> : (
            <div style={{ maxHeight: 420, overflowY: "auto" }}>
              {histRows.map((h, i) => (
                <div key={i} className="small" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <div><b>{h.action}</b> {h.field ? <span className="muted">· {h.field}</span> : ""} {h.new ? <>→ {h.new}</> : ""}</div>
                  <div className="muted" style={{ fontSize: 11 }}>{new Date(h.ts).toLocaleString("en-GB")}{h.actor ? ` · ${h.actor}` : ""}</div>
                </div>
              ))}
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
