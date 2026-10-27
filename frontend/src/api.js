const BASE = import.meta.env.VITE_API_URL || "";
const TOKEN_KEY = "pp-token";

export const getToken = () => {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
};
export const setToken = (t) => {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ }
};

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

function formatDetail(detail) {
  if (!detail) return "Something went wrong";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (d.msg || "").replace(/^Value error, /, "")).filter(Boolean).join(". ") || "Invalid input";
  }
  return "Something went wrong";
}

async function request(path, { method = "GET", body, form, auth = true, raw = false } = {}) {
  const headers = {};
  const token = getToken();
  if (auth && token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res;
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, body: payload });
  } catch {
    throw new ApiError("Cannot reach the ProofPulse server. Is the backend running?", 0);
  }
  if (res.status === 401 && auth && token) {
    setToken(null);
    window.dispatchEvent(new Event("pp-logout"));
  }
  if (!res.ok) {
    let detail;
    try { detail = (await res.json()).detail; } catch { /* non-json */ }
    throw new ApiError(formatDetail(detail), res.status);
  }
  if (raw) return res;
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res;
}

const qs = (o) => {
  const p = new URLSearchParams();
  Object.entries(o || {}).forEach(([k, v]) => { if (v !== "" && v != null) p.set(k, v); });
  const s = p.toString();
  return s ? `?${s}` : "";
};

export async function download(path, filename) {
  const res = await request(path, { raw: true });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  return res.headers.get("X-Integrity");
}

export async function sha256File(file) {
  const buf = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export const api = {
  // auth
  register: (b) => request("/api/auth/register", { method: "POST", body: b, auth: false }),
  login: (b) => request("/api/auth/login", { method: "POST", body: b, auth: false }),
  me: () => request("/api/auth/me"),
  changePassword: (b) => request("/api/auth/password", { method: "PUT", body: b }),
  searchUsers: (q) => request(`/api/users/search${qs({ q })}`),
  // records
  analyze: (file) => { const f = new FormData(); f.append("file", file); return request("/api/analyze", { method: "POST", form: f }); },
  createRecord: (form) => request("/api/records", { method: "POST", form }),
  records: (params) => request(`/api/records${qs(params)}`),
  record: (id) => request(`/api/records/${id}`),
  addVersion: (id, form) => request(`/api/records/${id}/versions`, { method: "POST", form }),
  revoke: (id, reason) => request(`/api/records/${id}/revoke`, { method: "POST", body: { reason } }),
  versions: (id) => request(`/api/records/${id}/versions`),
  integrity: (id) => request(`/api/records/${id}/integrity`, { method: "POST" }),
  // approvals
  requestApprovals: (id, approvers) => request(`/api/records/${id}/approvals`, { method: "POST", body: { approvers } }),
  inbox: (status) => request(`/api/approvals/inbox${qs({ status })}`),
  sent: () => request("/api/approvals/sent"),
  decide: (id, approve, comment) => request(`/api/approvals/${id}/decision`, { method: "POST", body: { approve, comment } }),
  // verify (public)
  verify: (id) => request(`/api/verify/${id}`, { auth: false }),
  verifyHash: (id, sha256) => request(`/api/verify/${id}/hash`, { method: "POST", body: { sha256 }, auth: false }),
  verifyFile: (id, file) => { const f = new FormData(); f.append("file", file); return request(`/api/verify/${id}/file`, { method: "POST", form: f, auth: false }); },
  lookupHash: (sha256) => request("/api/verify-lookup/hash", { method: "POST", body: { sha256 }, auth: false }),
  publicStats: () => request("/api/public/stats", { auth: false }),
  // dashboards, audit, notifications, admin
  dashboard: () => request("/api/dashboard"),
  audit: (params) => request(`/api/audit${qs(params)}`),
  auditActions: () => request("/api/audit/actions"),
  auditChain: () => request("/api/audit/verify-chain"),
  notifications: () => request("/api/notifications"),
  readAll: () => request("/api/notifications/read-all", { method: "POST" }),
  readOne: (id) => request(`/api/notifications/${id}/read`, { method: "POST" }),
  adminOverview: () => request("/api/admin/overview"),
  adminUsers: () => request("/api/admin/users"),
  adminPatchUser: (id, b) => request(`/api/admin/users/${id}`, { method: "PATCH", body: b }),
  adminRecords: () => request("/api/admin/records"),
  adminScan: () => request("/api/admin/integrity-scan", { method: "POST" }),
  adminReanchor: () => request("/api/admin/reanchor", { method: "POST" }),
  health: () => request("/api/health", { auth: false }),
  auditCsvUrl: (params) => `${BASE}/api/audit/export.csv${qs(params)}`,
  qrUrl: (id) => `${BASE}/api/records/${id}/qr.png`,
};
