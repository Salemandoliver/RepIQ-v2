import React, { useState } from "react";
import { useOutletContext } from "react-router-dom";
import api, { setAuth, getToken } from "../api";
import { useToast } from "../components/Toast.jsx";

/* Self-service account page — currently: change your own password. */
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
      setAuth(data.access_token || getToken(), data.user);   // keep the session alive
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
