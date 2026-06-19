import React, { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import api, { setAuth, getToken } from "../api";
import { useToast } from "../components/Toast.jsx";
import { Avatar } from "../components/ui.jsx";

/* Self-service account page: your profile (photo + "known as" + bio) and your password. */

function ProfileCard({ user }) {
  const toast = useToast();
  const [p, setP] = useState(null);          // {preferred_name, profile_photo, about, first_name,...}
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/api/v1/hr/me/personal")
      .then((d) => setP({ preferred_name: d.preferred_name || "", profile_photo: d.profile_photo || null,
                          about: d.about || "" }))
      .catch(() => setP({ preferred_name: "", profile_photo: null, about: "" }));
  }, []);

  const onPhoto = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.type.startsWith("image/")) { toast("Please choose an image file.", "error"); return; }
    if (f.size > 2 * 1024 * 1024) { toast("Photo must be under 2MB.", "error"); return; }
    const r = new FileReader();
    r.onload = () => setP((s) => ({ ...s, profile_photo: r.result }));
    r.readAsDataURL(f);
  };

  const save = async () => {
    setSaving(true);
    try {
      const d = await api.put("/api/v1/hr/me/personal", {
        preferred_name: p.preferred_name.trim() || null,
        profile_photo: p.profile_photo || null,
        about: p.about.trim() || null,
      });
      setP((s) => ({ ...s, preferred_name: d.preferred_name || "", profile_photo: d.profile_photo || null, about: d.about || "" }));
      toast("Profile saved.", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  if (!p) return null;
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 14 }}>Your profile</div>
      <div className="flex" style={{ gap: 16, alignItems: "center", marginBottom: 14 }}>
        <div style={{ width: 72, height: 72, borderRadius: "50%", overflow: "hidden", flexShrink: 0,
          border: "1px solid var(--border)", background: "#fff", display: "flex", alignItems: "center", justifyContent: "center" }}>
          {p.profile_photo
            ? <img src={p.profile_photo} alt="Profile" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            : <Avatar name={p.preferred_name || user?.name} color={user?.avatar_color} size={72} />}
        </div>
        <div className="flex" style={{ gap: 8 }}>
          <label className="btn btn-outline btn-sm" style={{ cursor: "pointer" }}>
            {p.profile_photo ? "Change photo" : "Upload photo"}
            <input type="file" accept="image/*" onChange={onPhoto} style={{ display: "none" }} />
          </label>
          {p.profile_photo && <button className="btn btn-ghost btn-sm" onClick={() => setP((s) => ({ ...s, profile_photo: null }))}>Remove</button>}
        </div>
      </div>
      <label className="field"><span>Known as <span className="muted">(the name you'd like to be called)</span></span>
        <input className="input" value={p.preferred_name} placeholder={user?.name ? `e.g. ${user.name.split(" ")[0]}` : "Preferred name"}
          onChange={(e) => setP((s) => ({ ...s, preferred_name: e.target.value }))} /></label>
      <label className="field"><span>About <span className="muted">(optional)</span></span>
        <textarea className="input" rows={2} value={p.about}
          onChange={(e) => setP((s) => ({ ...s, about: e.target.value }))} placeholder="A short bio for your team" /></label>
      <button className="btn btn-primary" style={{ justifyContent: "center", padding: "10px 18px" }}
        onClick={save} disabled={saving}>{saving ? "Saving…" : "Save profile"}</button>
    </div>
  );
}

export default function Account() {
  const { user } = useOutletContext() || {};
  const toast = useToast();
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (pw.length < 8) { toast("New password must be at least 8 characters.", "error"); return; }
    if (pw !== confirm) { toast("New passwords don't match.", "error"); return; }
    setSaving(true);
    try {
      const data = await api.post("/api/auth/change-password", {
        current_password: cur, new_password: pw, confirm_password: confirm,
      });
      setAuth(data.access_token || getToken(), data.user);
      setCur(""); setPw(""); setConfirm("");
      toast("Password updated.", "success");
    } catch (err) {
      toast(err.message || "Couldn't update your password.", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page" style={{ maxWidth: 520, margin: "0 auto", padding: "28px 22px" }}>
      <h1 style={{ margin: "0 0 4px", fontSize: 24 }}>Account</h1>
      <div className="muted" style={{ marginBottom: 22 }}>{user?.name} · {user?.email}</div>

      <ProfileCard user={user} />

      <div className="card">
        <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 14 }}>Change password</div>
        <form onSubmit={submit}>
          <label className="field">
            <span>Current password</span>
            <input className="input" type="password" value={cur}
              onChange={(e) => setCur(e.target.value)} required />
          </label>
          <label className="field">
            <span>New password</span>
            <input className="input" type="password" value={pw}
              onChange={(e) => setPw(e.target.value)} placeholder="At least 8 characters" required />
          </label>
          <label className="field">
            <span>Confirm new password</span>
            <input className="input" type="password" value={confirm}
              onChange={(e) => setConfirm(e.target.value)} required />
          </label>
          <button className="btn btn-primary" style={{ justifyContent: "center", padding: "10px 18px" }} disabled={saving}>
            {saving ? "Saving…" : "Update password"}
          </button>
        </form>
      </div>
    </div>
  );
}
