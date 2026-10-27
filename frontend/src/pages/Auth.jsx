import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Check, Eye, EyeOff, Sparkles, X } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../context";
import { ThemeToggle } from "../components/Layout";
import { Logo, Spinner } from "../components/ui";

const DEMO = [
  { u: "priya", p: "Demo@12345!", role: "Student (owner)" },
  { u: "meera", p: "Demo@12345!", role: "Faculty (approver)" },
  { u: "admin", p: "Admin@12345!", role: "Administrator" },
];

function Shell({ title, subtitle, children, foot }) {
  return (
    <div className="auth-wrap">
      <div style={{ position: "absolute", top: 18, right: 18 }}><ThemeToggle /></div>
      <motion.div className="auth-card card" initial={{ opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
        <Link to="/" className="row" style={{ gap: 10, marginBottom: 22, textDecoration: "none", color: "inherit" }}>
          <Logo size={36} /><b style={{ fontFamily: "var(--font-display)", fontSize: "1.25rem" }}>ProofPulse</b>
        </Link>
        <h2 style={{ fontSize: "1.55rem" }}>{title}</h2>
        <p className="muted" style={{ margin: "4px 0 20px" }}>{subtitle}</p>
        {children}
        <div className="small muted" style={{ marginTop: 18, textAlign: "center" }}>{foot}</div>
      </motion.div>
    </div>
  );
}

export function Login() {
  const { signIn } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      signIn(await api.login({ identifier, password }));
      nav(loc.state?.from || "/dashboard", { replace: true });
    } catch (ex) { setErr(ex.message); } finally { setBusy(false); }
  };

  return (
    <Shell title="Welcome back" subtitle="Sign in to register, review and verify records." foot={<>New to ProofPulse? <Link to="/signup">Create an account</Link></>}>
      <form className="col" onSubmit={submit}>
        <label className="field">Username or email
          <input className="input" value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" autoFocus required />
        </label>
        <label className="field">Password
          <div style={{ position: "relative" }}>
            <input className="input" type={show ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required style={{ paddingRight: 44 }} />
            <button type="button" className="copy" style={{ position: "absolute", right: 8, top: 8 }} onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"}>{show ? <EyeOff size={16} /> : <Eye size={16} />}</button>
          </div>
        </label>
        {err && <div className="err" role="alert">{err}</div>}
        <button className="btn primary block" disabled={busy}>{busy ? <Spinner /> : <>Sign in <ArrowRight size={17} /></>}</button>
      </form>
      {import.meta.env.VITE_SHOW_DEMO !== "false" && (
        <div style={{ marginTop: 18 }}>
          <div className="small muted" style={{ marginBottom: 8 }}><Sparkles size={13} style={{ verticalAlign: -2 }} /> Demo accounts (run <span className="kbd">python seed.py</span> first)</div>
          <div className="row">
            {DEMO.map((d) => (
              <button key={d.u} type="button" className="btn sm" onClick={() => { setIdentifier(d.u); setPassword(d.p); }} title={d.role}>{d.u}</button>
            ))}
          </div>
        </div>
      )}
    </Shell>
  );
}

const RULES = [
  ["At least 10 characters", (p) => p.length >= 10],
  ["Lowercase letter", (p) => /[a-z]/.test(p)],
  ["Uppercase letter", (p) => /[A-Z]/.test(p)],
  ["A digit", (p) => /\d/.test(p)],
  ["A symbol", (p) => /[^\w\s]/.test(p)],
];

export function Signup() {
  const { signIn } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ username: "", email: "", full_name: "", organization: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  const ok = RULES.every(([, t]) => t(f.password));

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      signIn(await api.register({ ...f, organization: f.organization || null }));
      nav("/dashboard", { replace: true });
    } catch (ex) { setErr(ex.message); } finally { setBusy(false); }
  };

  return (
    <Shell title="Create your account" subtitle="Your documents stay private; only fingerprints go on chain." foot={<>Already registered? <Link to="/login">Sign in</Link></>}>
      <form className="col" onSubmit={submit}>
        <label className="field">Full name<input className="input" value={f.full_name} onChange={set("full_name")} autoComplete="name" required minLength={2} /></label>
        <div className="grid g2" style={{ gap: 12 }}>
          <label className="field">Username<input className="input" value={f.username} onChange={set("username")} autoComplete="username" required pattern="[A-Za-z0-9_.\-]{3,32}" title="3-32 letters, digits, dot, dash or underscore" /></label>
          <label className="field">Organisation <span className="hint">(optional)</span><input className="input" value={f.organization} onChange={set("organization")} maxLength={120} /></label>
        </div>
        <label className="field">Email<input className="input" type="email" value={f.email} onChange={set("email")} autoComplete="email" required /></label>
        <label className="field">Password<input className="input" type="password" value={f.password} onChange={set("password")} autoComplete="new-password" required /></label>
        <div className="row" style={{ gap: 6 }}>
          {RULES.map(([label, t]) => {
            const pass = t(f.password);
            return <span key={label} className={`badge ${pass ? "b-good" : "b-mute"}`}>{pass ? <Check size={11} /> : <X size={11} />}{label}</span>;
          })}
        </div>
        {err && <div className="err" role="alert">{err}</div>}
        <button className="btn primary block" disabled={busy || !ok}>{busy ? <Spinner /> : <>Create account <ArrowRight size={17} /></>}</button>
      </form>
    </Shell>
  );
}
