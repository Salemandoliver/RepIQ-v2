import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { setAuth } from "../api";

/* Public page reached from an invite or password-reset link: /set-password/:token.
   The user sets their password (entered twice) and is signed straight in. */
export default function SetPassword() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [info, setInfo] = useState(null);      // {name, email, mode}
  const [loadErr, setLoadErr] = useState("");
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get(`/api/auth/setup/${token}`)
      .then(setInfo)
      .catch((e) => setLoadErr(e.message || "This link is invalid or has expired."));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (pw.length < 8) { setError("Password must be at least 8 characters."); return; }
    if (pw !== confirm) { setError("Passwords don't match."); return; }
    setSaving(true);
    try {
      const data = await api.post(`/api/auth/setup/${token}`, { new_password: pw, confirm_password: confirm });
      setAuth(data.access_token, data.user);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message || "Couldn't set your password.");
    } finally {
      setSaving(false);
    }
  };

  const isInvite = info?.mode === "invite";

  return (
    <div className="login-wrap">
      <div className="card login-card">
        <div className="login-logo">IQ</div>
        <h1 style={{ textAlign: "center", margin: "0 0 4px", fontSize: 24 }}>
          {loadErr ? "Link unavailable" : isInvite ? "Welcome to RepIQ" : "Set a new password"}
        </h1>

        {loadErr ? (
          <>
            <p className="muted" style={{ textAlign: "center", margin: "6px 0 18px" }}>{loadErr}</p>
            <button className="btn btn-outline" style={{ width: "100%", justifyContent: "center" }}
              onClick={() => navigate("/login")}>Back to sign in</button>
          </>
        ) : !info ? (
          <p className="muted" style={{ textAlign: "center", margin: "10px 0" }}>Checking your link…</p>
        ) : (
          <>
            <p className="muted" style={{ textAlign: "center", margin: "0 0 20px" }}>
              {isInvite ? "Create a password to activate your account" : "Choose a new password"} for <strong>{info.email}</strong>
            </p>
            <form onSubmit={submit}>
              <label className="field">
                <span>New password</span>
                <input className="input" type="password" value={pw} autoFocus
                  onChange={(e) => setPw(e.target.value)} placeholder="At least 8 characters" required />
              </label>
              <label className="field">
                <span>Confirm password</span>
                <input className="input" type="password" value={confirm}
                  onChange={(e) => setConfirm(e.target.value)} placeholder="Re-enter your password" required />
              </label>
              {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 10 }}>{error}</div>}
              <button className="btn btn-primary" style={{ width: "100%", justifyContent: "center", padding: 11 }} disabled={saving}>
                {saving ? "Saving…" : isInvite ? "Activate account" : "Save password"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
