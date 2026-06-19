import React, { useEffect, useState } from "react";
import { useOutletContext, useNavigate } from "react-router-dom";
import api from "../api";
import { useToast } from "../components/Toast.jsx";
import { Avatar } from "../components/ui.jsx";

/* People management for managers & admins: invite/add users, send password-reset links,
   edit details, and offboard leavers. Invite & reset links are shown for copying (email
   delivery can be wired on later). */

function copyText(t) {
  try { navigator.clipboard.writeText(t); return true; } catch { return false; }
}

const PLAT_COLORS = { manager: "#2563eb", operations: "#7c3aed", admin: "#e11d48", employee: "#6b7280" };

function status_of(u) {
  if (u.left_on || (!u.active && !u.must_set_password)) return { label: "Leaver", color: "var(--red)" };
  if (u.must_set_password) return { label: "Invited", color: "var(--amber)" };
  return { label: "Active", color: "var(--green)" };
}

function Modal({ title, onClose, children, width = 460 }) {
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50, padding: 16 }}>
      <div className="card" onClick={(e) => e.stopPropagation()} style={{ width, maxWidth: "100%", maxHeight: "90vh", overflowY: "auto" }}>
        <div className="flex" style={{ marginBottom: 14 }}>
          <span style={{ fontWeight: 700, fontSize: 16 }}>{title}</span>
          <button className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={onClose}>✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

function LinkBox({ link, expires }) {
  const toast = useToast();
  return (
    <div>
      <p className="muted small" style={{ marginTop: 0 }}>
        Copy this link and send it to the person. They'll set their own password and be signed in.
        {expires && <> Link valid until {new Date(expires).toLocaleString("en-GB")}.</>}
      </p>
      <div className="flex" style={{ gap: 8 }}>
        <input className="input" readOnly value={link} style={{ flex: 1 }} onFocus={(e) => e.target.select()} />
        <button className="btn btn-primary btn-sm" onClick={() => { copyText(link) && toast("Link copied.", "success"); }}>Copy</button>
      </div>
    </div>
  );
}

function PersonForm({ teams, canSetAdmin, initial, onSubmit, submitting }) {
  const editing = !!initial;
  const [name, setName] = useState(initial?.name || "");
  const [email, setEmail] = useState(initial?.email || "");
  const [role, setRole] = useState(initial?.role || "recorder");
  const [jobTitle, setJobTitle] = useState(initial?.job_title || "Sales Rep");
  const [preferredName, setPreferredName] = useState(initial?.preferred_name || initial?.short_name || "");
  const [teamId, setTeamId] = useState(initial?.team_id || "");
  const [method, setMethod] = useState("invite");   // invite | password (new users only)
  const [password, setPassword] = useState("");
  const [platformRole, setPlatformRole] = useState(initial?.platform_role || "employee");
  const [financial, setFinancial] = useState(!!(initial?.scopes || []).includes("financial"));

  const submit = (e) => {
    e.preventDefault();
    onSubmit({
      name: name.trim(), email: email.trim().toLowerCase(), role, job_title: jobTitle.trim(),
      preferred_name: preferredName.trim() || null, team_id: teamId ? Number(teamId) : null,
      method, password,
      platform_role: platformRole, scopes: financial ? ["financial"] : [],
    });
  };

  return (
    <form onSubmit={submit}>
      <label className="field"><span>Full name</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></label>
      <label className="field"><span>Email</span>
        <input className="input" type="email" value={email} disabled={editing}
          onChange={(e) => setEmail(e.target.value)} required /></label>
      <div className="flex" style={{ gap: 10 }}>
        <label className="field" style={{ flex: 1 }}><span>Job title</span>
          <input className="input" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)}
            placeholder="Sales Rep / Business Creator / Sales Manager" /></label>
        <label className="field" style={{ flex: "0 0 130px" }}><span>System role</span>
          <select className="input" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="recorder">Recorder</option>
            <option value="analyst">Analyst</option>
            {canSetAdmin && <option value="admin">Admin</option>}
          </select></label>
      </div>
      <div className="flex" style={{ gap: 10 }}>
        <label className="field" style={{ flex: 1 }}><span>Team</span>
          <select className="input" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
            <option value="">— none —</option>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select></label>
        <label className="field" style={{ flex: 1 }}><span>Preferred name <span className="muted">(known as)</span></span>
          <input className="input" value={preferredName} onChange={(e) => setPreferredName(e.target.value)}
            placeholder="e.g. Pat, Kune" /></label>
      </div>

      {!editing && (
        <div className="field">
          <span>Onboarding</span>
          <div className="flex" style={{ gap: 14, marginTop: 4 }}>
            <label className="flex" style={{ gap: 6, cursor: "pointer" }}>
              <input type="radio" checked={method === "invite"} onChange={() => setMethod("invite")} />
              <span className="small">Send invite — they set their own password</span>
            </label>
            <label className="flex" style={{ gap: 6, cursor: "pointer" }}>
              <input type="radio" checked={method === "password"} onChange={() => setMethod("password")} />
              <span className="small">Set an initial password</span>
            </label>
          </div>
          {method === "password" && (
            <input className="input" type="text" value={password} style={{ marginTop: 8 }}
              onChange={(e) => setPassword(e.target.value)} placeholder="Initial password (min 8 chars)" />
          )}
        </div>
      )}

      {editing && canSetAdmin && (
        <div className="field" style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 4 }}>
          <span>Platform access <span className="muted">(admin only)</span></span>
          <div className="flex" style={{ gap: 12, marginTop: 4, alignItems: "flex-end" }}>
            <label className="field" style={{ flex: 1, margin: 0 }}><span className="small muted">Role</span>
              <select className="input" value={platformRole} onChange={(e) => setPlatformRole(e.target.value)}>
                <option value="employee">Employee</option>
                <option value="manager">Manager</option>
                <option value="operations">Operations</option>
                <option value="admin">Admin</option>
              </select></label>
            <label className="flex" style={{ gap: 6, cursor: "pointer", paddingBottom: 9 }}>
              <input type="checkbox" checked={financial} onChange={(e) => setFinancial(e.target.checked)} />
              <span className="small">Financial data access</span>
            </label>
          </div>
          <div className="muted small" style={{ marginTop: 4 }}>
            Controls HR &amp; Order Entry access. “Financial” reveals pay/bank data — grant sparingly.
          </div>
        </div>
      )}

      <button className="btn btn-primary" style={{ justifyContent: "center", padding: "10px 18px", marginTop: 6 }} disabled={submitting}>
        {submitting ? "Saving…" : editing ? "Save changes" : method === "invite" ? "Create & generate invite link" : "Create user"}
      </button>
    </form>
  );
}

export default function People() {
  const { user: me } = useOutletContext() || {};
  const navigate = useNavigate();
  const toast = useToast();
  const [users, setUsers] = useState(null);
  const [teams, setTeams] = useState([]);
  const [q, setQ] = useState("");
  const [showLeavers, setShowLeavers] = useState(false);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const [linkResult, setLinkResult] = useState(null);   // {title, link, expires}
  const [busy, setBusy] = useState(false);

  const isAdmin = me?.role === "admin" || me?.platform_role === "admin";

  const load = () => {
    api.get("/api/admin/users").then(setUsers).catch((e) => toast(e.message, "error"));
    api.get("/api/admin/teams").then(setTeams).catch(() => {});
  };
  useEffect(load, []);   // eslint-disable-line

  const create = async (f) => {
    setBusy(true);
    try {
      if (f.method === "invite") {
        const r = await api.post("/api/admin/users/invite", {
          name: f.name, email: f.email, role: f.role, job_title: f.job_title,
          short_name: f.preferred_name, team_id: f.team_id,
        });
        setAdding(false);
        setLinkResult({ title: `Invite link for ${f.name}`, link: r.link, expires: r.expires });
      } else {
        if ((f.password || "").length < 8) { toast("Initial password must be at least 8 characters.", "error"); setBusy(false); return; }
        await api.post("/api/admin/users", {
          name: f.name, email: f.email, password: f.password, role: f.role,
          job_title: f.job_title, short_name: f.preferred_name, team_id: f.team_id,
        });
        setAdding(false);
        toast(`${f.name} added.`, "success");
      }
      load();
    } catch (e) { toast(e.message, "error"); } finally { setBusy(false); }
  };

  const saveEdit = async (f) => {
    setBusy(true);
    try {
      const payload = { name: f.name, role: f.role, job_title: f.job_title,
        preferred_name: f.preferred_name, team_id: f.team_id };
      if (isAdmin) { payload.platform_role = f.platform_role; payload.scopes = f.scopes; }
      await api.patch(`/api/admin/users/${editing.id}`, payload);
      setEditing(null);
      toast("Saved.", "success");
      load();
    } catch (e) { toast(e.message, "error"); } finally { setBusy(false); }
  };

  const sendResetLink = async (u) => {
    try {
      const r = await api.post(`/api/admin/users/${u.id}/reset-link`);
      setLinkResult({ title: `Password reset link for ${u.name}`, link: r.link, expires: r.expires });
    } catch (e) { toast(e.message, "error"); }
  };

  const makeLeaver = async (u) => {
    if (!window.confirm(`Mark ${u.name} as a leaver? They'll no longer be able to sign in.`)) return;
    try { await api.post(`/api/admin/users/${u.id}/leaver`); toast(`${u.name} marked as a leaver.`, "success"); load(); }
    catch (e) { toast(e.message, "error"); }
  };

  const reactivate = async (u) => {
    try { await api.post(`/api/admin/users/${u.id}/reactivate`); toast(`${u.name} reactivated.`, "success"); load(); }
    catch (e) { toast(e.message, "error"); }
  };

  const resetTeamPasswords = async () => {
    const pw = window.prompt(
      "Set this password for ALL users except the Managing Director and admin@btlocalbusiness.co.uk:",
      "RepIQ-Reset-2026!");
    if (!pw) return;
    try {
      const r = await api.post("/api/admin/users/reset-passwords", { password: pw });
      toast(`Reset ${r.reset} password${r.reset === 1 ? "" : "s"}.`, "success");
    } catch (e) { toast(e.message, "error"); }
  };

  const filtered = (users || []).filter((u) => {
    const isLeaver = u.left_on || (!u.active && !u.must_set_password);
    if (isLeaver && !showLeavers) return false;
    if (!q) return true;
    const s = q.toLowerCase();
    return (u.name || "").toLowerCase().includes(s) || (u.email || "").toLowerCase().includes(s) || (u.job_title || "").toLowerCase().includes(s);
  });

  return (
    <div className="page" style={{ maxWidth: 920, margin: "0 auto", padding: "28px 22px 60px" }}>
      <div className="spread" style={{ marginBottom: 18 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24 }}>People</h1>
          <div className="muted">Add team members, set roles &amp; access, send sign-in links, and manage leavers.</div>
        </div>
        <div className="flex" style={{ gap: 8 }}>
          {isAdmin && <button className="btn btn-outline" onClick={resetTeamPasswords}>Reset team passwords</button>}
          <button className="btn btn-primary" onClick={() => setAdding(true)}>+ Add person</button>
        </div>
      </div>

      <div className="flex" style={{ gap: 10, marginBottom: 14 }}>
        <input className="input" style={{ flex: 1 }} placeholder="Search by name, email or job title…"
          value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="flex small" style={{ gap: 6, cursor: "pointer", whiteSpace: "nowrap" }}>
          <input type="checkbox" checked={showLeavers} onChange={(e) => setShowLeavers(e.target.checked)} /> Show leavers
        </label>
      </div>

      {users === null ? (
        <div className="muted">Loading…</div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          {filtered.map((u, i) => {
            const st = status_of(u);
            const isLeaver = st.label === "Leaver";
            const canEditAdmin = u.role !== "admin" || isAdmin;
            return (
              <div key={u.id} className="flex" style={{ gap: 12, alignItems: "center", padding: "12px 16px", borderTop: i ? "1px solid var(--border)" : "none" }}>
                <div className="flex" role="button" title={`Open ${u.name}'s profile`}
                  onClick={() => navigate(`/people/${u.id}`)}
                  style={{ gap: 12, alignItems: "center", flex: 1, minWidth: 0, cursor: "pointer" }}>
                <Avatar name={u.name} color={u.avatar_color} size={34} photo={u.photo} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="flex" style={{ gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 600 }}>{u.preferred_name || u.name}</span>
                    {u.platform_role && u.platform_role !== "employee" && (
                      <span className="chip" style={{ fontSize: 10.5, fontWeight: 700, textTransform: "capitalize",
                        background: (PLAT_COLORS[u.platform_role] || "#6b7280") + "22", color: PLAT_COLORS[u.platform_role] || "#6b7280" }}>
                        {u.platform_role}</span>
                    )}
                    {(u.scopes || []).includes("financial") && (
                      <span className="chip" style={{ fontSize: 10.5, fontWeight: 700, background: "rgba(34,197,94,0.15)", color: "var(--green)" }}>finance</span>
                    )}
                    {u.sales_role && <span className="muted small" style={{ textTransform: "capitalize" }}>· {u.sales_role}</span>}
                  </div>
                  <div className="muted small">{u.preferred_name && u.preferred_name !== u.name ? `${u.name} · ` : ""}{u.email}{u.job_title ? ` · ${u.job_title}` : ""}</div>
                </div>
                </div>
                <span className="small" style={{ color: st.color, fontWeight: 600, flexShrink: 0, minWidth: 56 }}>{st.label}</span>
                <div className="flex" style={{ gap: 6, flexShrink: 0 }}>
                  <button className="btn btn-outline btn-sm" onClick={() => navigate(`/people/${u.id}`)}>Profile</button>
                  {!isLeaver && canEditAdmin && <button className="btn btn-ghost btn-sm" onClick={() => setEditing(u)}>Edit</button>}
                  {!isLeaver && canEditAdmin && <button className="btn btn-outline btn-sm" onClick={() => sendResetLink(u)}>{u.must_set_password ? "Resend link" : "Send login link"}</button>}
                  {!isLeaver && canEditAdmin && u.id !== me?.id && <button className="btn btn-ghost btn-sm" style={{ color: "var(--red)" }} onClick={() => makeLeaver(u)}>Leaver</button>}
                  {isLeaver && <button className="btn btn-outline btn-sm" onClick={() => reactivate(u)}>Reactivate</button>}
                </div>
              </div>
            );
          })}
          {filtered.length === 0 && <div className="muted" style={{ padding: 16 }}>No people match.</div>}
        </div>
      )}

      {adding && (
        <Modal title="Add person" onClose={() => setAdding(false)}>
          <PersonForm teams={teams} canSetAdmin={isAdmin} onSubmit={create} submitting={busy} />
        </Modal>
      )}
      {editing && (
        <Modal title={`Edit ${editing.name}`} onClose={() => setEditing(null)}>
          <PersonForm teams={teams} canSetAdmin={isAdmin} initial={editing} onSubmit={saveEdit} submitting={busy} />
        </Modal>
      )}
      {linkResult && (
        <Modal title={linkResult.title} onClose={() => setLinkResult(null)}>
          <LinkBox link={linkResult.link} expires={linkResult.expires} />
        </Modal>
      )}
    </div>
  );
}
