import React, { useEffect, useMemo, useState } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import api from "../api";
import { useToast } from "../components/Toast.jsx";
import { Avatar, Spinner, EmptyState, Modal } from "../components/ui.jsx";
import { ACTIVITY_TYPES } from "../utils";
import { PlusIcon, TrashIcon, EditIcon, XIcon } from "../components/Icons.jsx";

const SECTIONS = [
  ["general", "General"],
  ["company", "Company"],
  ["users", "Users"],
  ["teams", "Teams"],
  ["topics", "Topics"],
  ["ask", "Ask RepIQ"],
  ["playbooks", "Playbooks & Frameworks"],
  ["salesiq", "SalesIQ Targets"],
  ["ingestion", "Call Ingestion"],
  ["videos", "Performance Videos"],
  ["vocabulary", "Vocabulary"],
  ["privacy", "Privacy"],
];

const ROLE_COLORS = { recorder: "#14b8a6", analyst: "#9c27b0", admin: "#e91e63" };

/* ---------------- Company ---------------- */
function CompanySection() {
  const toast = useToast();
  const [c, setC] = useState({ name: "", phone: "", address: "", logo: null });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/api/company")
      .then((d) => setC({ name: d.name || "", phone: d.phone || "", address: d.address || "", logo: d.logo || null }))
      .catch(() => {});
  }, []);

  const onLogo = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.type.startsWith("image/")) { toast("Please choose an image file.", "error"); return; }
    if (f.size > 500 * 1024) { toast("Logo must be under 500KB — please use a smaller image.", "error"); return; }
    const r = new FileReader();
    r.onload = () => setC((p) => ({ ...p, logo: r.result }));
    r.readAsDataURL(f);
  };

  const save = async () => {
    setSaving(true);
    try {
      const d = await api.put("/api/company", c);
      setC({ name: d.name || "", phone: d.phone || "", address: d.address || "", logo: d.logo || null });
      try { d.logo ? sessionStorage.setItem("repiq_company_logo", d.logo) : sessionStorage.removeItem("repiq_company_logo"); } catch { /* ignore */ }
      toast("Company details saved.", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <h2 className="card-title" style={{ marginTop: 0 }}>Company</h2>
      <p className="muted small" style={{ marginTop: -4, marginBottom: 16 }}>
        Identify your company. The logo appears in the app.
      </p>
      <div className="card" style={{ maxWidth: 560 }}>
        <label className="field"><span>Company name</span>
          <input className="input" value={c.name} onChange={(e) => setC((p) => ({ ...p, name: e.target.value }))}
            placeholder="e.g. BT Local Business Oxford & Bucks" /></label>
        <label className="field"><span>Company phone number</span>
          <input className="input" value={c.phone} onChange={(e) => setC((p) => ({ ...p, phone: e.target.value }))}
            placeholder="e.g. 01865 000000" /></label>
        <label className="field"><span>Company address</span>
          <textarea className="input" rows={3} value={c.address}
            onChange={(e) => setC((p) => ({ ...p, address: e.target.value }))} placeholder="Street, town, postcode" /></label>
        <div className="field">
          <span>Company logo</span>
          <div className="flex" style={{ gap: 14, alignItems: "center", marginTop: 4 }}>
            <div style={{ width: 56, height: 56, borderRadius: 10, border: "1px solid var(--border)", background: "#fff",
              display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden", flexShrink: 0 }}>
              {c.logo ? <img src={c.logo} alt="Company logo" style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
                : <span className="muted small">none</span>}
            </div>
            <label className="btn btn-outline btn-sm" style={{ cursor: "pointer" }}>
              {c.logo ? "Replace logo" : "Upload logo"}
              <input type="file" accept="image/*" onChange={onLogo} style={{ display: "none" }} />
            </label>
            {c.logo && <button className="btn btn-ghost btn-sm" onClick={() => setC((p) => ({ ...p, logo: null }))}>Remove</button>}
          </div>
          <div className="muted small" style={{ marginTop: 6 }}>PNG or SVG with a transparent background works best. Under 500KB.</div>
        </div>
        <button className="btn btn-primary" style={{ justifyContent: "center", padding: "10px 18px", marginTop: 6 }}
          onClick={save} disabled={saving}>{saving ? "Saving…" : "Save company details"}</button>
      </div>
    </div>
  );
}

/* ---------------- General ---------------- */
function GeneralSection() {
  const toast = useToast();
  const [settings, setSettings] = useState(null);
  const [aiContext, setAiContext] = useState("");
  const [retention, setRetention] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .get("/api/admin/settings")
      .then((d) => {
        setSettings(d || {});
        const ctx = d?.ai_context;
        setAiContext(typeof ctx === "string" ? ctx : ctx?.text || "");
        const ret = d?.retention;
        setRetention(typeof ret === "number" ? ret : ret?.days ?? "");
      })
      .catch((e) => {
        setSettings({});
        toast(e.message, "error");
      });
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/api/admin/settings/ai_context", { text: aiContext });
      if (retention !== "" && !isNaN(Number(retention))) {
        await api.put("/api/admin/settings/retention", { days: Number(retention) });
      }
      toast("Settings saved", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  if (settings === null) return <Spinner />;
  return (
    <div className="card">
      <h3 className="card-title">General</h3>
      <label className="field">
        <span>Organisation</span>
        <input className="input" value="BT Local Business Oxford & Bucks" disabled />
      </label>
      <label className="field">
        <span>AI context (used to ground summaries &amp; scoring)</span>
        <textarea
          className="input"
          rows={6}
          value={aiContext}
          onChange={(e) => setAiContext(e.target.value)}
          placeholder="Describe your products, market and what good calls look like…"
        />
      </label>
      <label className="field" style={{ maxWidth: 240 }}>
        <span>Recording retention (days)</span>
        <input
          className="input"
          type="number"
          min="1"
          value={retention}
          onChange={(e) => setRetention(e.target.value)}
        />
      </label>
      <button className="btn btn-primary" onClick={save} disabled={saving}>
        {saving ? "Saving…" : "Save changes"}
      </button>
    </div>
  );
}

/* ---------------- Users ---------------- */
function UserModal({ user, teams, onClose, onSaved }) {
  const toast = useToast();
  const isNew = !user?.id;
  const [form, setForm] = useState({
    name: user?.name || "",
    email: user?.email || "",
    role: user?.role || "recorder",
    job_title: user?.job_title || "",
    short_name: user?.short_name || "",
    team_id: user?.team_id ?? "",
    active: user?.active !== false,
    password: "",
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        name: form.name,
        role: form.role,
        job_title: form.job_title,
        short_name: form.short_name,
        team_id: form.team_id === "" ? null : Number(form.team_id),
        active: form.active,
      };
      if (form.password) payload.password = form.password;
      if (isNew) {
        await api.post("/api/admin/users", { ...payload, email: form.email });
        toast("User invited", "success");
      } else {
        await api.patch(`/api/admin/users/${user.id}`, payload);
        toast("User updated", "success");
      }
      onSaved();
      onClose();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={isNew ? "Invite user" : `Edit ${user.name}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={saving || !form.name || (isNew && !form.email)}>
            {saving ? "Saving…" : isNew ? "Invite" : "Save"}
          </button>
        </>
      }
    >
      <label className="field">
        <span>Name</span>
        <input className="input" value={form.name} onChange={(e) => set("name", e.target.value)} />
      </label>
      <label className="field">
        <span>Email</span>
        <input className="input" type="email" value={form.email} disabled={!isNew} onChange={(e) => set("email", e.target.value)} />
      </label>
      <div className="flex" style={{ gap: 12, alignItems: "flex-start" }}>
        <label className="field" style={{ flex: 1 }}>
          <span>Role</span>
          <select className="input" value={form.role} onChange={(e) => set("role", e.target.value)}>
            <option value="recorder">Recorder</option>
            <option value="analyst">Analyst</option>
            <option value="admin">Admin</option>
          </select>
        </label>
        <label className="field" style={{ flex: 1 }}>
          <span>Team</span>
          <select className="input" value={form.team_id} onChange={(e) => set("team_id", e.target.value)}>
            <option value="">No team</option>
            {teams.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex" style={{ gap: 12, alignItems: "flex-start" }}>
        <label className="field" style={{ flex: 1 }}>
          <span>Job title</span>
          <input className="input" value={form.job_title} onChange={(e) => set("job_title", e.target.value)} />
        </label>
        <label className="field" style={{ flex: 1 }}>
          <span>Tracker name <span className="muted" style={{ fontWeight: 400 }}>(short name in trackers)</span></span>
          <input className="input" value={form.short_name} placeholder="e.g. Matt E"
            onChange={(e) => set("short_name", e.target.value)} />
        </label>
      </div>
      <label className="field">
        <span>{isNew ? "Initial password" : "Reset password (leave blank to keep)"}</span>
        <input className="input" type="password" value={form.password} onChange={(e) => set("password", e.target.value)} />
      </label>
      <label className="flex" style={{ cursor: "pointer" }}>
        <input type="checkbox" checked={form.active} onChange={(e) => set("active", e.target.checked)} />
        <span>Active</span>
      </label>
    </Modal>
  );
}

function UsersSection({ teams }) {
  const toast = useToast();
  const [users, setUsers] = useState(null);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null); // null | {} (new) | user

  const load = () => {
    api
      .get("/api/admin/users")
      .then((d) => setUsers(Array.isArray(d) ? d : []))
      .catch((e) => {
        setUsers([]);
        toast(e.message, "error");
      });
  };
  useEffect(load, []);

  const resetPasswords = async () => {
    const pw = window.prompt(
      "Set this password for ALL users except the Managing Director and admin@btlocalbusiness.co.uk:",
      "SynvestmentCallIQ!"
    );
    if (!pw) return;
    try {
      const r = await api.post("/api/admin/users/reset-passwords", { password: pw });
      toast(`Reset ${r.reset} user password${r.reset === 1 ? "" : "s"}`, "success");
    } catch (e) {
      toast(e.message, "error");
    }
  };

  const filtered = useMemo(() => {
    if (!users) return [];
    const q = query.toLowerCase();
    return users.filter(
      (u) =>
        !q ||
        (u.name || "").toLowerCase().includes(q) ||
        (u.email || "").toLowerCase().includes(q) ||
        (u.job_title || "").toLowerCase().includes(q)
    );
  }, [users, query]);

  const roleCounts = useMemo(() => {
    const c = { recorder: 0, analyst: 0, admin: 0 };
    (users || []).forEach((u) => {
      if (c[u.role] != null) c[u.role]++;
    });
    return c;
  }, [users]);

  const teamName = (id) => teams.find((t) => t.id === id)?.name || "—";

  if (users === null) return <Spinner />;

  const donutData = Object.entries(roleCounts).map(([role, value]) => ({
    name: role,
    value,
    color: ROLE_COLORS[role],
  }));
  const hasUsers = donutData.some((d) => d.value > 0);

  return (
    <>
      <div className="card" style={{ marginBottom: 18 }}>
        <h3 className="card-title">Roles</h3>
        <div className="flex" style={{ gap: 26, flexWrap: "wrap" }}>
          <div style={{ width: 160, height: 150, position: "relative" }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={hasUsers ? donutData : [{ name: "None", value: 1, color: "#e5e7eb" }]}
                  dataKey="value"
                  innerRadius="60%"
                  outerRadius="85%"
                  paddingAngle={hasUsers ? 3 : 0}
                  stroke="none"
                >
                  {(hasUsers ? donutData : [{ color: "#e5e7eb" }]).map((d, i) => (
                    <Cell key={i} fill={d.color} />
                  ))}
                </Pie>
                {hasUsers && <Tooltip />}
              </PieChart>
            </ResponsiveContainer>
            <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
              <strong style={{ fontSize: 20 }}>{users.length}</strong>
            </div>
          </div>
          {Object.entries(roleCounts).map(([role, n]) => (
            <div key={role} className="flex" style={{ gap: 8 }}>
              <span className="dot" style={{ background: ROLE_COLORS[role], width: 12, height: 12 }} />
              <div>
                <div style={{ fontWeight: 700, fontSize: 18 }}>{n}</div>
                <div className="small muted" style={{ textTransform: "capitalize" }}>{role}{n === 1 ? "" : "s"}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="card">
        <div className="spread" style={{ marginBottom: 12 }}>
          <input
            className="input"
            style={{ maxWidth: 280 }}
            placeholder="Search users…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="flex" style={{ gap: 8 }}>
            <button className="btn btn-outline" onClick={resetPasswords}>Reset team passwords</button>
            <button className="btn btn-primary" onClick={() => setEditing({})}>
              <PlusIcon size={14} /> Invite User
            </button>
          </div>
        </div>
        {filtered.length === 0 ? (
          <EmptyState icon="👥" title="No users found" />
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Team</th>
                <th>Job title</th>
                <th>Role</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id}>
                  <td>
                    <span className="flex">
                      <Avatar name={u.name} color={u.avatar_color} size={28} />
                      <span style={{ fontWeight: 600 }}>{u.name}</span>
                    </span>
                  </td>
                  <td className="small muted">{u.email}</td>
                  <td className="small">{teamName(u.team_id)}</td>
                  <td className="small">{u.job_title || "—"}</td>
                  <td>
                    <span className="chip" style={{ textTransform: "capitalize", background: `${ROLE_COLORS[u.role] || "#9ca3af"}22`, color: ROLE_COLORS[u.role] || "#6b7280", fontWeight: 600 }}>
                      {u.role}
                    </span>
                  </td>
                  <td className="small">{u.active === false ? <span className="faint">Inactive</span> : <span style={{ color: "var(--green)", fontWeight: 600 }}>Active</span>}</td>
                  <td>
                    <button className="icon-btn" onClick={() => setEditing(u)} aria-label="Edit">
                      <EditIcon size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {editing !== null && (
        <UserModal user={editing.id ? editing : null} teams={teams} onClose={() => setEditing(null)} onSaved={load} />
      )}
    </>
  );
}

/* ---------------- Teams ---------------- */
function TeamsSection({ teams, reloadTeams }) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const add = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.post("/api/admin/teams", { name: name.trim() });
      setName("");
      reloadTeams();
      toast("Team created", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (t) => {
    if (!window.confirm(`Delete team "${t.name}"?`)) return;
    try {
      await api.del(`/api/admin/teams/${t.id}`);
      reloadTeams();
      toast("Team deleted", "success");
    } catch (e) {
      toast(e.message, "error");
    }
  };

  return (
    <div className="card">
      <h3 className="card-title">Teams</h3>
      <div className="flex" style={{ marginBottom: 16, maxWidth: 420 }}>
        <input className="input" placeholder="New team name…" value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} />
        <button className="btn btn-primary" onClick={add} disabled={busy || !name.trim()}>
          <PlusIcon size={14} /> Add
        </button>
      </div>
      {teams.length === 0 ? (
        <EmptyState icon="🧑‍🤝‍🧑" title="No teams yet" />
      ) : (
        <table className="data">
          <thead>
            <tr>
              <th>Name</th>
              <th style={{ width: 60 }}></th>
            </tr>
          </thead>
          <tbody>
            {teams.map((t) => (
              <tr key={t.id}>
                <td style={{ fontWeight: 600 }}>{t.name}</td>
                <td>
                  <button className="icon-btn" onClick={() => remove(t)} aria-label="Delete">
                    <TrashIcon size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ---------------- Topics ---------------- */
function TopicModal({ topic, onClose, onSaved }) {
  const toast = useToast();
  const isNew = !topic?.id;
  const [name, setName] = useState(topic?.name || "");
  const [color, setColor] = useState(topic?.color || "#e91e63");
  const [active, setActive] = useState(topic?.active !== false);
  const [keywords, setKeywords] = useState(topic?.keywords || []);
  const [kw, setKw] = useState("");
  const [saving, setSaving] = useState(false);

  const addKw = () => {
    const v = kw.trim();
    if (v && !keywords.includes(v)) setKeywords((k) => [...k, v]);
    setKw("");
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = { name, keywords, color, active };
      if (isNew) await api.post("/api/admin/topics", payload);
      else await api.patch(`/api/admin/topics/${topic.id}`, payload);
      toast(isNew ? "Topic created" : "Topic updated", "success");
      onSaved();
      onClose();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={isNew ? "New topic" : `Edit ${topic.name}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={saving || !name.trim()}>
            {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      <div className="flex" style={{ gap: 12, alignItems: "flex-start" }}>
        <label className="field" style={{ flex: 1 }}>
          <span>Name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <span>Colour</span>
          <input type="color" className="input" style={{ width: 60, height: 38, padding: 3 }} value={color} onChange={(e) => setColor(e.target.value)} />
        </label>
      </div>
      <label className="field">
        <span>Keywords (Enter to add)</span>
        <input
          className="input"
          value={kw}
          onChange={(e) => setKw(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addKw();
            }
          }}
          placeholder="e.g. fibre, broadband speed…"
        />
      </label>
      <div className="flex" style={{ flexWrap: "wrap", marginBottom: 12 }}>
        {keywords.map((k) => (
          <span className="chip" key={k}>
            {k}
            <button className="x" onClick={() => setKeywords((ks) => ks.filter((x) => x !== k))}>
              <XIcon size={11} />
            </button>
          </span>
        ))}
      </div>
      <label className="flex" style={{ cursor: "pointer" }}>
        <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
        <span>Active</span>
      </label>
    </Modal>
  );
}

function TopicsSection() {
  const toast = useToast();
  const [topics, setTopics] = useState(null);
  const [editing, setEditing] = useState(null);

  const load = () => {
    api
      .get("/api/admin/topics")
      .then((d) => setTopics(Array.isArray(d) ? d : []))
      .catch((e) => {
        setTopics([]);
        toast(e.message, "error");
      });
  };
  useEffect(load, []);

  const remove = async (t) => {
    if (!window.confirm(`Delete topic "${t.name}"?`)) return;
    try {
      await api.del(`/api/admin/topics/${t.id}`);
      load();
      toast("Topic deleted", "success");
    } catch (e) {
      toast(e.message, "error");
    }
  };

  if (topics === null) return <Spinner />;
  return (
    <div className="card">
      <div className="spread" style={{ marginBottom: 14 }}>
        <h3 className="card-title" style={{ margin: 0 }}>Topics</h3>
        <button className="btn btn-primary" onClick={() => setEditing({})}>
          <PlusIcon size={14} /> New topic
        </button>
      </div>
      {topics.length === 0 ? (
        <EmptyState icon="🏷️" title="No topics configured" />
      ) : (
        topics.map((t) => (
          <div className="leader-row" key={t.id}>
            <span className="dot" style={{ background: t.color || "#9ca3af", width: 13, height: 13 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600 }}>
                {t.name} {t.active === false && <span className="small faint">(inactive)</span>}
              </div>
              <div className="flex" style={{ flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                {(t.keywords || []).map((k) => (
                  <span key={k} className="chip" style={{ fontSize: 11 }}>{k}</span>
                ))}
              </div>
            </div>
            <button className="icon-btn" onClick={() => setEditing(t)} aria-label="Edit"><EditIcon size={15} /></button>
            <button className="icon-btn" onClick={() => remove(t)} aria-label="Delete"><TrashIcon size={15} /></button>
          </div>
        ))
      )}
      {editing !== null && (
        <TopicModal topic={editing.id ? editing : null} onClose={() => setEditing(null)} onSaved={load} />
      )}
    </div>
  );
}

/* ---------------- Ask RepIQ presets ---------------- */
function AskPresetModal({ preset, position, onClose, onSaved }) {
  const toast = useToast();
  const isNew = !preset?.id;
  const [name, setName] = useState(preset?.name || "");
  const [prompt, setPrompt] = useState(preset?.prompt || "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const payload = { name: name.trim(), prompt: prompt.trim() };
      if (isNew) await api.post("/api/admin/ask-presets", { ...payload, position });
      else await api.patch(`/api/admin/ask-presets/${preset.id}`, payload);
      toast(isNew ? "Preset created" : "Preset updated", "success");
      onSaved();
      onClose();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={isNew ? "New preset" : `Edit ${preset.name}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={saving || !name.trim() || !prompt.trim()}>
            {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      <label className="field">
        <span>Name (short label shown on the chip)</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Objections" />
      </label>
      <label className="field">
        <span>Question (the full prompt sent to the AI)</span>
        <textarea
          className="input"
          rows={4}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. What objections did the customer raise, and how were they handled?"
        />
      </label>
    </Modal>
  );
}

function AskPresetsSection() {
  const toast = useToast();
  const [presets, setPresets] = useState(null);
  const [editing, setEditing] = useState(null);

  const load = () => {
    api
      .get("/api/calls/ask-presets")
      .then((d) => setPresets(Array.isArray(d) ? d : []))
      .catch((e) => {
        setPresets([]);
        toast(e.message, "error");
      });
  };
  useEffect(load, []);

  const remove = async (p) => {
    if (!window.confirm(`Delete preset "${p.name}"?`)) return;
    try {
      await api.del(`/api/admin/ask-presets/${p.id}`);
      load();
      toast("Preset deleted", "success");
    } catch (e) {
      toast(e.message, "error");
    }
  };

  if (presets === null) return <Spinner />;
  return (
    <div className="card">
      <div className="spread" style={{ marginBottom: 6 }}>
        <h3 className="card-title" style={{ margin: 0 }}>Ask RepIQ presets</h3>
        <button className="btn btn-primary" onClick={() => setEditing({})}>
          <PlusIcon size={14} /> New preset
        </button>
      </div>
      <p className="muted small" style={{ marginTop: 0 }}>
        Quick questions shown as chips under the Ask RepIQ bar on the call page.
      </p>
      {presets.length === 0 ? (
        <EmptyState icon="✨" title="No presets yet" sub="Add a preset to give reps one-click questions." />
      ) : (
        <table className="data">
          <thead>
            <tr>
              <th>Chip</th>
              <th>Question</th>
              <th style={{ width: 80 }}></th>
            </tr>
          </thead>
          <tbody>
            {presets.map((p) => (
              <tr key={p.id}>
                <td><span className="chip" style={{ fontWeight: 600 }}>{p.name}</span></td>
                <td className="small muted">{p.prompt}</td>
                <td>
                  <button className="icon-btn" onClick={() => setEditing(p)} aria-label="Edit"><EditIcon size={15} /></button>
                  <button className="icon-btn" onClick={() => remove(p)} aria-label="Delete"><TrashIcon size={15} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editing !== null && (
        <AskPresetModal
          preset={editing.id ? editing : null}
          position={presets.length}
          onClose={() => setEditing(null)}
          onSaved={load}
        />
      )}
    </div>
  );
}

/* ---------------- Playbooks ---------------- */
function PlaybookModal({ playbook, onClose, onSaved }) {
  const toast = useToast();
  const isNew = !playbook?.id;
  const [name, setName] = useState(playbook?.name || "");
  const [description, setDescription] = useState(playbook?.description || "");
  const [activityTypes, setActivityTypes] = useState(playbook?.activity_types || []);
  const [criteria, setCriteria] = useState(
    (playbook?.criteria || []).map((c) => ({ ...c })) || []
  );
  const [active, setActive] = useState(playbook?.active !== false);
  const [saving, setSaving] = useState(false);

  const toggleType = (t) =>
    setActivityTypes((a) => (a.includes(t) ? a.filter((x) => x !== t) : [...a, t]));

  const setCrit = (i, k, v) =>
    setCriteria((cs) => cs.map((c, j) => (j === i ? { ...c, [k]: v } : c)));

  const addCrit = () =>
    setCriteria((cs) => [...cs, { key: `criterion_${cs.length + 1}`, name: "", description: "", weight: 1 }]);

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        name,
        description,
        activity_types: activityTypes,
        criteria: criteria
          .filter((c) => c.name.trim())
          .map((c, i) => ({
            key: c.key || c.name.toLowerCase().replace(/[^a-z0-9]+/g, "_") || `criterion_${i + 1}`,
            name: c.name,
            description: c.description || "",
            weight: Number(c.weight) || 1,
          })),
        active,
      };
      if (isNew) await api.post("/api/admin/playbooks", payload);
      else await api.patch(`/api/admin/playbooks/${playbook.id}`, payload);
      toast(isNew ? "Playbook created" : "Playbook updated", "success");
      onSaved();
      onClose();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={isNew ? "New playbook" : `Edit ${playbook.name}`}
      onClose={onClose}
      wide
      footer={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={saving || !name.trim()}>
            {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      <label className="field">
        <span>Name</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="field">
        <span>Description</span>
        <textarea className="input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      <div className="field">
        <span style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-soft)", marginBottom: 6 }}>
          Applies to activity types
        </span>
        <div className="flex" style={{ flexWrap: "wrap" }}>
          {ACTIVITY_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              className="chip"
              onClick={() => toggleType(t)}
              style={{
                cursor: "pointer",
                border: "1px solid",
                borderColor: activityTypes.includes(t) ? "var(--accent)" : "var(--border)",
                background: activityTypes.includes(t) ? "rgba(233,30,99,0.1)" : "#fff",
                color: activityTypes.includes(t) ? "var(--accent)" : "var(--text-soft)",
                fontWeight: 600,
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <div className="field">
        <span style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-soft)", marginBottom: 6 }}>
          Criteria
        </span>
        {criteria.map((c, i) => (
          <div className="criteria-row" key={i}>
            <input className="input" style={{ flex: 1 }} placeholder="Name" value={c.name} onChange={(e) => setCrit(i, "name", e.target.value)} />
            <input className="input" style={{ flex: 2 }} placeholder="Description" value={c.description || ""} onChange={(e) => setCrit(i, "description", e.target.value)} />
            <input className="input" style={{ width: 70 }} type="number" min="0" step="0.5" title="Weight" value={c.weight} onChange={(e) => setCrit(i, "weight", e.target.value)} />
            <button className="icon-btn" onClick={() => setCriteria((cs) => cs.filter((_, j) => j !== i))} aria-label="Remove">
              <TrashIcon size={15} />
            </button>
          </div>
        ))}
        <button className="btn btn-outline btn-sm" onClick={addCrit}>
          <PlusIcon size={13} /> Add criterion
        </button>
      </div>
      <label className="flex" style={{ cursor: "pointer" }}>
        <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
        <span>Active</span>
      </label>
    </Modal>
  );
}

function PlaybooksSection() {
  const toast = useToast();
  const [playbooks, setPlaybooks] = useState(null);
  const [editing, setEditing] = useState(null);

  const load = () => {
    api
      .get("/api/admin/playbooks")
      .then((d) => setPlaybooks(Array.isArray(d) ? d : []))
      .catch((e) => {
        setPlaybooks([]);
        toast(e.message, "error");
      });
  };
  useEffect(load, []);

  const remove = async (p) => {
    if (!window.confirm(`Delete playbook "${p.name}"?`)) return;
    try {
      await api.del(`/api/admin/playbooks/${p.id}`);
      load();
      toast("Playbook deleted", "success");
    } catch (e) {
      toast(e.message, "error");
    }
  };

  if (playbooks === null) return <Spinner />;
  return (
    <>
      <div className="spread" style={{ marginBottom: 14 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>Playbooks &amp; Frameworks</h3>
        <button className="btn btn-primary" onClick={() => setEditing({})}>
          <PlusIcon size={14} /> New playbook
        </button>
      </div>
      {playbooks.length === 0 ? (
        <div className="card"><EmptyState icon="📘" title="No playbooks yet" /></div>
      ) : (
        <div style={{ display: "grid", gap: 16 }}>
          {playbooks.map((p) => (
            <div className="card" key={p.id}>
              <div className="spread">
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15 }}>
                    {p.name} {p.active === false && <span className="small faint">(inactive)</span>}
                  </div>
                  <div className="muted small">{p.description}</div>
                </div>
                <div className="flex">
                  <button className="icon-btn" onClick={() => setEditing(p)} aria-label="Edit"><EditIcon size={15} /></button>
                  <button className="icon-btn" onClick={() => remove(p)} aria-label="Delete"><TrashIcon size={15} /></button>
                </div>
              </div>
              <div className="flex" style={{ flexWrap: "wrap", margin: "10px 0" }}>
                {(p.activity_types || []).map((t) => (
                  <span key={t} className="chip" style={{ fontSize: 11 }}>{t}</span>
                ))}
              </div>
              <table className="data">
                <thead>
                  <tr>
                    <th>Criterion</th>
                    <th>Description</th>
                    <th style={{ width: 80 }}>Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {(p.criteria || []).map((c) => (
                    <tr key={c.key}>
                      <td style={{ fontWeight: 600 }}>{c.name}</td>
                      <td className="small muted">{c.description}</td>
                      <td>{c.weight}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
      {editing !== null && (
        <PlaybookModal playbook={editing.id ? editing : null} onClose={() => setEditing(null)} onSaved={load} />
      )}
    </>
  );
}

/* ---------------- Vocabulary ---------------- */
function VocabularySection() {
  const toast = useToast();
  const [terms, setTerms] = useState(null);
  const [term, setTerm] = useState("");

  const load = () => {
    api
      .get("/api/admin/vocabulary")
      .then((d) => setTerms(Array.isArray(d) ? d : []))
      .catch((e) => {
        setTerms([]);
        toast(e.message, "error");
      });
  };
  useEffect(load, []);

  const add = async () => {
    if (!term.trim()) return;
    try {
      await api.post("/api/admin/vocabulary", { term: term.trim() });
      setTerm("");
      load();
    } catch (e) {
      toast(e.message, "error");
    }
  };

  const remove = async (t) => {
    try {
      await api.del(`/api/admin/vocabulary/${t.id}`);
      load();
    } catch (e) {
      toast(e.message, "error");
    }
  };

  if (terms === null) return <Spinner />;
  return (
    <div className="card">
      <h3 className="card-title">Vocabulary</h3>
      <p className="muted small" style={{ marginTop: 0 }}>
        Custom terms that improve transcription accuracy (product names, jargon, acronyms).
      </p>
      <div className="flex" style={{ marginBottom: 16, maxWidth: 420 }}>
        <input
          className="input"
          placeholder="Add a term, e.g. EE Broadband…"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
        />
        <button className="btn btn-primary" onClick={add} disabled={!term.trim()}>
          <PlusIcon size={14} /> Add
        </button>
      </div>
      {terms.length === 0 ? (
        <EmptyState icon="🗣️" title="No vocabulary terms" />
      ) : (
        <div className="flex" style={{ flexWrap: "wrap", gap: 8 }}>
          {terms.map((t) => (
            <span className="tag" key={t.id ?? t.term}>
              {t.term ?? String(t)}
              <button className="x" style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-soft)", display: "flex", padding: 0 }} onClick={() => remove(t)} aria-label="Delete">
                <XIcon size={12} />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- Privacy ---------------- */
function PrivacySection() {
  const toast = useToast();
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);

  const erase = async () => {
    if (!phone.trim()) return;
    if (!window.confirm(`Permanently erase all data for ${phone}? This cannot be undone.`)) return;
    setBusy(true);
    try {
      await api.del(`/api/admin/gdpr/erase?phone=${encodeURIComponent(phone.trim())}`);
      toast("Erasure complete", "success");
      setPhone("");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h3 className="card-title">Privacy — GDPR erasure</h3>
      <p className="muted small" style={{ marginTop: 0 }}>
        Erase all recordings, transcripts and analytics associated with a phone number. This action is permanent.
      </p>
      <div className="flex" style={{ maxWidth: 420 }}>
        <input className="input" placeholder="+44 1865 000000" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <button className="btn btn-danger" onClick={erase} disabled={busy || !phone.trim()}>
          {busy ? "Erasing…" : "Erase"}
        </button>
      </div>
    </div>
  );
}

/* ---------------- SalesIQ Targets ---------------- */
const TITLE_FIELDS = [
  ["connectivity", "Connectivity £/mo"],
  ["cloud", "Cloud £/mo"],
  ["mobile", "Mobile £/mo"],
  ["leads", "Leads/mo"],
];
const titleCase = (s) => s.replace(/\b\w/g, (c) => c.toUpperCase());

function SalesTargetsSection() {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [byTitle, setByTitle] = useState({});
  const [saving, setSaving] = useState(false);

  const load = () => {
    api.get("/api/salesiq/targets")
      .then((d) => { setData(d); setByTitle(d.targets?.byTitle || {}); })
      .catch((e) => toast(e.message, "error"));
  };
  useEffect(load, []);

  const setCell = (title, field, value) =>
    setByTitle((b) => ({ ...b, [title]: { ...(b[title] || {}), [field]: value === "" ? undefined : Number(value) } }));

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/api/salesiq/targets", { byTitle });
      toast("Targets saved", "success");
      load();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  if (!data) return <Spinner />;
  const titles = Object.keys(byTitle).sort();
  const act = data.targets?.activity || {};

  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 className="card-title">SalesIQ Targets — by job title</h3>
        <p className="small muted" style={{ marginTop: -4 }}>
          Monthly SOV targets per pillar, from the pay plans. A rep's target is set by their <strong>Job title</strong>{" "}
          (set under Users). Quarterly = ×3, annual = ×12. All reps also have an activity target of{" "}
          {act.talkMinsPerDay || 90} mins talk / {act.dialsPerDay || 80} dials per day.
        </p>
        <div style={{ overflowX: "auto" }}>
          <table className="data">
            <thead>
              <tr><th>Job title</th>{TITLE_FIELDS.map(([f, l]) => <th key={f} className="num">{l}</th>)}</tr>
            </thead>
            <tbody>
              {titles.map((t) => (
                <tr key={t}>
                  <td>{titleCase(t)}</td>
                  {TITLE_FIELDS.map(([f]) => (
                    <td key={f}>
                      <input className="input" type="number" min="0" style={{ width: 110 }}
                        value={byTitle[t]?.[f] ?? ""}
                        onChange={(e) => setCell(t, f, e.target.value)} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button className="btn btn-primary" style={{ marginTop: 14 }} onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save targets"}
        </button>
      </div>
    </div>
  );
}

/* ---------------- Page ---------------- */
/* ---------------- Call Ingestion (RingCentral) ---------------- */
function IngestionSection() {
  const toast = useToast();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [days, setDays] = useState(1);
  const [queue, setQueue] = useState(null);
  const webhookUrl = `${window.location.origin}/api/webhooks/ringcentral`;

  const loadQueue = () => api.get("/api/admin/calls/queue-status").then(setQueue).catch(() => {});
  const load = () => {
    setLoading(true);
    loadQueue();
    api.get("/api/admin/ringcentral/status")
      .then(setStatus)
      .catch((e) => setStatus({ connected: false, error: e.message }))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const run = async (withWebhook) => {
    setBusy(true);
    try {
      const q = new URLSearchParams();
      if (withWebhook) q.set("webhook_url", webhookUrl);
      q.set("backfill_days", String(days));
      const r = await api.post(`/api/admin/ringcentral/setup?${q.toString()}`, {});
      const msgs = [];
      if (r.subscription_id) msgs.push(`webhook reconnected`);
      if (r.queued_calls != null) msgs.push(`${r.queued_calls} call(s) queued`);
      toast(msgs.join(" · ") || "Done", "success");
      load();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="card" style={{ marginBottom: 18 }}>
        <div className="spread">
          <h3 className="card-title">RingCentral connection</h3>
          <button className="btn btn-ghost" onClick={load} disabled={loading}>Refresh</button>
        </div>
        {loading ? <Spinner /> : status?.connected ? (
          <>
            <div className="flex" style={{ gap: 8, marginBottom: 10 }}>
              <span className="dot" style={{ background: "var(--green)", width: 10, height: 10 }} />
              <strong>Connected to RingCentral</strong>
            </div>
            {status.subscriptions?.length > 0 ? (
              <table className="data">
                <thead><tr><th>Subscription</th><th>Status</th><th>Delivery URL</th><th>Expires</th></tr></thead>
                <tbody>
                  {status.subscriptions.map((s) => (
                    <tr key={s.id}>
                      <td className="small muted">{s.id}</td>
                      <td><span style={{ fontWeight: 700, color: s.status === "Active" ? "var(--green)" : "var(--red)" }}>{s.status}</span></td>
                      <td className="small muted" style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.address}</td>
                      <td className="small muted">{s.expires ? new Date(s.expires).toLocaleDateString("en-GB") : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState icon="🔌" title="No active webhook subscription"
                sub="Calls won't stream in real-time until you reconnect below." />
            )}
          </>
        ) : (
          <div style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", color: "var(--red)", borderRadius: 10, padding: "10px 14px", fontWeight: 600 }}>
            ⚠ Not connected to RingCentral{status?.error ? ` — ${status.error}` : ""}
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="card-title">Reconnect &amp; backfill</h3>
        <p className="muted small" style={{ marginTop: 0 }}>
          Re-registers the real-time webhook and pulls in recently recorded calls. Use this if calls have stopped appearing (e.g. after a redeploy). Calls only appear once RingCentral has the recording ready.
        </p>
        <div className="flex" style={{ gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <label className="field" style={{ margin: 0 }}>
            <span>Backfill window</span>
            <select className="input" value={days} onChange={(e) => setDays(Number(e.target.value))} style={{ width: 130 }}>
              {[1, 2, 3, 7, 14, 30].map((d) => <option key={d} value={d}>{d} day{d > 1 ? "s" : ""}</option>)}
            </select>
          </label>
          <button className="btn btn-primary" disabled={busy} onClick={() => run(true)}>
            {busy ? "Working…" : "Reconnect & backfill"}
          </button>
          <button className="btn btn-outline" disabled={busy} onClick={() => run(false)}>
            Backfill only
          </button>
        </div>
        <p className="muted small" style={{ marginTop: 12, marginBottom: 0 }}>
          Webhook URL: <code style={{ background: "#f3f4f6", padding: "2px 6px", borderRadius: 4 }}>{webhookUrl}</code>
        </p>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <div className="spread">
          <h3 className="card-title">Processing queue</h3>
          <button className="btn btn-ghost small" onClick={loadQueue}>Refresh</button>
        </div>
        {queue ? (
          <>
            <div className="flex" style={{ gap: 14, flexWrap: "wrap", margin: "4px 0 6px" }}>
              {[["completed", "var(--green)"], ["queued", "var(--text-soft)"], ["processing", "var(--amber)"],
                ["awaiting_recording", "var(--amber)"], ["failed", "var(--red)"], ["no_recording", "var(--text-faint)"]]
                .filter(([k]) => queue.counts?.[k]).map(([k, c]) => (
                  <span key={k} className="small"><strong style={{ color: c }}>{queue.counts[k]}</strong> {k.replace("_", " ")}</span>
                ))}
              {Object.keys(queue.counts || {}).length === 0 && <span className="muted small">No calls yet.</span>}
            </div>
            {(() => {
              const hb = queue.worker?.processing ? new Date(queue.worker.processing) : null;
              const alive = hb && (Date.now() - hb.getTime() < 120000);
              return (
                <div className="small" style={{ marginBottom: 10, color: alive ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                  ● Worker {alive ? "active" : "not responding"}{hb ? ` · last tick ${hb.toLocaleTimeString("en-GB")}` : ""}
                </div>
              );
            })()}
            {(queue.pending_with_recording != null || queue.pending_no_recording != null) && (
              <div className="muted small" style={{ marginBottom: 8 }}>
                Pending: <strong>{queue.pending_with_recording ?? 0}</strong> with recording ·{" "}
                <strong>{queue.pending_no_recording ?? 0}</strong> awaiting recording from RingCentral
              </div>
            )}
            {queue.recent_errors?.length > 0 && (
              <details style={{ marginBottom: 10 }}>
                <summary className="small" style={{ cursor: "pointer", color: "var(--red)" }}>
                  {queue.recent_errors.length} recent error{queue.recent_errors.length === 1 ? "" : "s"} (click to see why)
                </summary>
                <div style={{ marginTop: 6 }}>
                  {queue.recent_errors.map((e) => (
                    <div key={e.id} className="small muted" style={{ padding: "3px 0", borderTop: "1px solid var(--border)" }}>
                      Call {e.id} · {e.duration ? `${e.duration}s` : "no duration"} · {e.attempts} attempt{e.attempts === 1 ? "" : "s"} ·{" "}
                      {e.has_recording ? "has recording" : "no recording"}<br />
                      <span style={{ color: "var(--red)" }}>{e.error}</span>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </>
        ) : <p className="muted small">Loading…</p>}
        <p className="muted small" style={{ marginTop: 0 }}>
          <strong>Reprocess stuck:</strong> re-runs calls stuck mid-processing. <strong>Retry failed:</strong> re-runs failed calls. <strong>Remove dead:</strong> deletes no-answer dials (under 5s).
        </p>
        <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
          <button className="btn btn-outline" disabled={busy} onClick={async () => {
            setBusy(true);
            try {
              const r = await api.post("/api/admin/calls/reprocess-stuck", {});
              toast(`Re-queued ${r.requeued} stuck call${r.requeued === 1 ? "" : "s"}`, "success");
              loadQueue();
            } catch (e) { toast(e.message, "error"); } finally { setBusy(false); }
          }}>
            Reprocess stuck calls
          </button>
          <button className="btn btn-outline" disabled={busy} onClick={async () => {
            setBusy(true);
            try {
              const r = await api.post("/api/admin/calls/retry-failed", {});
              toast(`Re-queued ${r.requeued} failed call${r.requeued === 1 ? "" : "s"}`, "success");
              loadQueue();
            } catch (e) { toast(e.message, "error"); } finally { setBusy(false); }
          }}>
            Retry failed calls
          </button>
          <button className="btn btn-outline" disabled={busy} onClick={async () => {
            if (!window.confirm("Permanently delete all no-answer / dead dials (calls under 5 seconds)?")) return;
            setBusy(true);
            try {
              const r = await api.post("/api/admin/calls/cleanup-dead?max_seconds=5", {});
              toast(`Removed ${r.deleted} dead call${r.deleted === 1 ? "" : "s"}`, "success");
              loadQueue();
            } catch (e) { toast(e.message, "error"); } finally { setBusy(false); }
          }}>
            Remove dead / no-answer calls
          </button>
        </div>
      </div>
    </>
  );
}

function PerformanceVideosSection() {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/api/intelligence/videos/status").then(setData).catch((e) => toast(e.message, "error"));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  const generate = async () => {
    setBusy(true);
    try {
      const r = await api.post("/api/intelligence/video/generate-all", {});
      if (r.errors && r.errors.length) toast(`${r.errors.length} failed — e.g. ${r.errors[0]}`, "error");
      else toast(`Generating ${r.generated} video${r.generated === 1 ? "" : "s"} — they'll render in the background`, "success");
      setTimeout(load, 2000);
    } catch (e) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  const c = data?.counts || {};
  const STAT = [["ready", "Ready", "var(--green)"], ["rendering", "Rendering", "var(--amber)"],
    ["scripted", "Scripted", "var(--text-soft)"], ["text_only", "Briefing only", "var(--text-soft)"],
    ["failed", "Failed", "var(--red)"]];
  return (
    <div className="card">
      <div className="spread" style={{ marginBottom: 8 }}>
        <h3 className="card-title" style={{ margin: 0 }}>Performance videos</h3>
        <button className="btn btn-ghost small" onClick={load}>Refresh</button>
      </div>
      <p className="muted small" style={{ marginTop: 0 }}>
        Weekly AI performance videos auto-generate early each Monday for enabled teams (currently the Volume team).
        Generate this week's now to render them ahead of time. They're stored and reused — running this again only fills in any missing ones.
      </p>
      <div className="flex" style={{ gap: 10, flexWrap: "wrap", margin: "10px 0 14px" }}>
        <button className="btn btn-primary" onClick={generate} disabled={busy}>{busy ? "Starting…" : "Generate this week's videos now"}</button>
      </div>
      {data && (
        <>
          <div className="flex" style={{ gap: 14, flexWrap: "wrap", marginBottom: 12 }}>
            {STAT.filter(([k]) => c[k]).map(([k, label, col]) => (
              <span key={k} className="small"><strong style={{ color: col }}>{c[k]}</strong> {label}</span>
            ))}
            {data.total === 0 && <span className="muted small">None generated for this week yet.</span>}
          </div>
          {data.items?.length > 0 && (
            <div style={{ maxHeight: 300, overflowY: "auto" }}>
              {data.items.map((it) => (
                <div key={it.userId} style={{ padding: "6px 0", borderTop: "1px solid var(--border)" }}>
                  <div className="spread small">
                    <span>{it.name}</span>
                    <span style={{ fontWeight: 600, color: it.status === "ready" ? "var(--green)" : it.status === "failed" ? "var(--red)" : it.status === "rendering" ? "var(--amber)" : "var(--text-soft)" }}>{it.status}</span>
                  </div>
                  {it.error && <div className="small" style={{ color: "var(--text-soft)", marginTop: 2 }}>{it.error}</div>}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function Settings() {
  const toast = useToast();
  const [section, setSection] = useState("general");
  const [teams, setTeams] = useState([]);

  const reloadTeams = () => {
    api
      .get("/api/admin/teams")
      .then((d) => setTeams(Array.isArray(d) ? d : []))
      .catch((e) => toast(e.message, "error"));
  };
  useEffect(reloadTeams, []);

  return (
    <div className="page">
      <div style={{ marginBottom: 18 }}>
        <h1 className="page-title">Settings</h1>
        <p className="page-sub">BT Local Business Oxford &amp; Bucks workspace configuration.</p>
      </div>
      <div className="settings-layout">
        <nav className="settings-nav card" style={{ padding: 10 }}>
          {SECTIONS.map(([k, label]) => (
            <button key={k} className={section === k ? "active" : ""} onClick={() => setSection(k)}>
              {label}
            </button>
          ))}
        </nav>
        <div className="settings-body">
          {section === "general" && <GeneralSection />}
          {section === "company" && <CompanySection />}
          {section === "users" && <UsersSection teams={teams} />}
          {section === "teams" && <TeamsSection teams={teams} reloadTeams={reloadTeams} />}
          {section === "topics" && <TopicsSection />}
          {section === "ask" && <AskPresetsSection />}
          {section === "playbooks" && <PlaybooksSection />}
          {section === "salesiq" && <SalesTargetsSection />}
          {section === "ingestion" && <IngestionSection />}
          {section === "videos" && <PerformanceVideosSection />}
          {section === "vocabulary" && <VocabularySection />}
          {section === "privacy" && <PrivacySection />}
        </div>
      </div>
    </div>
  );
}
