import React, { useState } from "react";
import { useNavigate, useLocation, Navigate } from "react-router-dom";
import api, { setAuth, getToken } from "../api";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const location = useLocation();

  if (getToken()) {
    return <Navigate to="/" replace />;
  }

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await api.post("/api/auth/login", { email, password });
      setAuth(data.access_token, data.user);
      navigate(location.state?.from || "/", { replace: true });
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="card login-card">
        <div className="login-logo">IQ</div>
        <h1 style={{ textAlign: "center", margin: "0 0 4px", fontSize: 24 }}>RepIQ</h1>
        <p className="muted" style={{ textAlign: "center", margin: "0 0 22px" }}>
          Call analytics for BT Local Business Oxford &amp; Bucks
        </p>
        <form onSubmit={submit}>
          <label className="field">
            <span>Email</span>
            <input
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@btlocalbusiness.co.uk"
              autoFocus
              required
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </label>
          {error && (
            <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 10 }}>{error}</div>
          )}
          <button className="btn btn-primary" style={{ width: "100%", justifyContent: "center", padding: "11px" }} disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="muted small" style={{ textAlign: "center", margin: "14px 0 0" }}>
          Forgot your password? Ask your manager or an admin to send you a reset link.
        </p>
        <div className="login-hint">
          <strong>Demo login:</strong> admin@btlocalbusiness.co.uk / demo1234
        </div>
      </div>
    </div>
  );
}
