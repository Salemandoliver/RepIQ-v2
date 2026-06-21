const BASE = import.meta.env.VITE_API_URL || "";

export function getToken() {
  return localStorage.getItem("calliq_token");
}

export function getStoredUser() {
  try {
    const raw = localStorage.getItem("calliq_user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setAuth(token, user) {
  localStorage.setItem("calliq_token", token);
  localStorage.setItem("calliq_user", JSON.stringify(user));
}

export function clearAuth() {
  localStorage.removeItem("calliq_token");
  localStorage.removeItem("calliq_user");
}

async function request(method, path, body) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Network error — could not reach the server");
  }
  if (res.status === 401) {
    // On the login page a 401 means bad credentials — show the real reason. Elsewhere it
    // means the saved token is no longer valid, so treat it as an expired session.
    let detail = "";
    try {
      const d = await res.json();
      detail = d && d.detail ? (typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail)) : "";
    } catch { /* ignore */ }
    if (window.location.pathname.startsWith("/login")) {
      throw new Error(detail || "Invalid email or password");
    }
    clearAuth();
    window.location.href = "/login";
    throw new Error("Session expired — please sign in again");
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data && data.detail) {
        msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      /* ignore */
    }
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res;
}

// Multipart upload (FormData) — never set Content-Type so the browser adds the boundary.
async function upload(path, formData) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(BASE + path, { method: "POST", headers, body: formData });
  if (!res.ok) {
    let msg = `Upload failed (${res.status})`;
    try { const d = await res.json(); if (d && d.detail) msg = typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail); } catch { /* ignore */ }
    const err = new Error(msg); err.status = res.status; throw err;
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  patch: (path, body) => request("PATCH", path, body),
  put: (path, body) => request("PUT", path, body),
  del: (path) => request("DELETE", path),
  delete: (path) => request("DELETE", path),
  upload,
  base: BASE,
};

// Fetch a binary resource (e.g. audio) with auth, returns an object URL or null.
export async function fetchBlobUrl(path) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(BASE + path, { headers });
  if (!res.ok) {
    const err = new Error(`Failed to load (${res.status})`);
    err.status = res.status;
    throw err;
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export default api;
