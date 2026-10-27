import { useState } from "react";
import { KeyRound, Moon, Sun, UserRound } from "lucide-react";
import { api } from "../api";
import { useAuth, useTheme, useToast } from "../context";
import { PageHead, Spinner, fmtDate } from "../components/ui";

export default function Settings() {
  const { user } = useAuth();
  const { theme, toggle } = useTheme();
  const toast = useToast();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const change = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try { await api.changePassword({ current_password: cur, new_password: next }); setCur(""); setNext(""); toast({ title: "Password changed", kind: "success" }); } catch (ex) { setErr(ex.message); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHead title="Settings" subtitle="Your account and appearance." />
      <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card col">
          <div className="card-title"><UserRound size={18} /> Account</div>
          <div className="grid g2" style={{ gap: 12 }}>
            <div><div className="small muted">Name</div><b>{user.full_name}</b></div>
            <div><div className="small muted">Username</div><b>@{user.username}</b></div>
            <div><div className="small muted">Email</div><b>{user.email}</b></div>
            <div><div className="small muted">Role</div><b>{user.role}</b></div>
            <div><div className="small muted">Organisation</div><b>{user.organization || "-"}</b></div>
            <div><div className="small muted">Member since</div><b>{fmtDate(user.created_at, false)}</b></div>
          </div>
          <div className="divider" />
          <div className="row between">
            <div><b>Appearance</b><div className="small muted">Currently {theme} mode</div></div>
            <button className="btn" onClick={toggle}>{theme === "dark" ? <Sun size={16} /> : <Moon size={16} />} Switch to {theme === "dark" ? "light" : "dark"}</button>
          </div>
        </div>
        <form className="card col" onSubmit={change}>
          <div className="card-title"><KeyRound size={18} /> Change password</div>
          <label className="field">Current password<input className="input" type="password" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" required /></label>
          <label className="field">New password <span className="hint">10+ characters with upper, lower, digit and symbol</span><input className="input" type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required /></label>
          {err && <div className="err" role="alert">{err}</div>}
          <button className="btn primary" disabled={busy}>{busy ? <Spinner /> : "Update password"}</button>
        </form>
      </div>
    </>
  );
}
