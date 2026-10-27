import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Bell, CheckCheck, ClipboardCheck, FilePlus2, FolderLock, LayoutDashboard, LogOut, Menu, Moon, ScanSearch, ScrollText, Search, ShieldCheck, Sun, UserCog } from "lucide-react";
import { api } from "../api";
import { useAuth, useLive, useTheme } from "../context";
import { Logo, timeAgo } from "./ui";

export function Backdrop() {
  return (
    <div className="backdrop" aria-hidden="true"><div className="orb a" /><div className="orb b" /><div className="orb c" /></div>
  );
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button className="btn icon ghost" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`} title="Toggle theme">
      <AnimatePresence mode="wait" initial={false}>
        <motion.span key={theme} initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }} transition={{ duration: 0.18 }} style={{ display: "inline-flex" }}>
          {theme === "dark" ? <Sun size={19} /> : <Moon size={19} />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}

function Notifications() {
  const { unread, setUnread } = useAuth();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const ref = useRef(null);
  const nav = useNavigate();

  const load = useCallback(() => api.notifications().then((r) => { setItems(r.items); setUnread(r.unread); }).catch(() => {}), [setUnread]);
  useEffect(() => { if (open) load(); }, [open, load]);
  useLive(["notification"], () => open && load());
  useEffect(() => {
    const h = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const go = async (n) => {
    if (!n.read) { await api.readOne(n.id).catch(() => {}); setUnread((u) => Math.max(0, u - 1)); }
    setOpen(false);
    if (n.record) nav(`/records/${n.record}`);
  };
  const markAll = async () => { await api.readAll(); setUnread(0); setItems((s) => s.map((n) => ({ ...n, read: true }))); };

  return (
    <div style={{ position: "relative" }} ref={ref}>
      <button className="btn icon ghost" style={{ position: "relative" }} onClick={() => setOpen((o) => !o)} aria-label={`Notifications (${unread} unread)`}>
        <Bell size={19} />{unread > 0 && <span className="bell-dot">{unread > 9 ? "9+" : unread}</span>}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div className="dropdown" initial={{ opacity: 0, y: -8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.18 }}>
            <div className="row between" style={{ padding: "8px 10px" }}>
              <b>Notifications</b>
              <button className="btn sm ghost" onClick={markAll} disabled={!unread}><CheckCheck size={15} /> Mark all read</button>
            </div>
            {items.length === 0 && <div className="empty small">You're all caught up.</div>}
            {items.map((n) => (
              <div key={n.id} className={`notif ${n.kind} ${n.read ? "" : "unread"}`} onClick={() => go(n)} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && go(n)}>
                <div className="tdot" />
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>{n.title}</div>
                  {n.body && <div className="small muted">{n.body}</div>}
                  <div className="small muted" style={{ marginTop: 2 }}>{timeAgo(n.created_at)}</div>
                </div>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function Layout() {
  const { user, live, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [pending, setPending] = useState(0);

  useEffect(() => setOpen(false), [loc.pathname]);
  const loadPending = useCallback(() => api.dashboard().then((d) => setPending(d.totals.pending_reviews)).catch(() => {}), []);
  useEffect(() => { loadPending(); }, [loadPending, loc.pathname]);
  useLive(["approvals", "notification"], loadPending);

  const links = [
    { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
    { to: "/records", icon: FolderLock, label: "My records" },
    { to: "/register", icon: FilePlus2, label: "Register file" },
    { to: "/approvals", icon: ClipboardCheck, label: "Approvals", pill: pending },
    { to: "/verify", icon: ScanSearch, label: "Verify" },
    { to: "/audit", icon: ScrollText, label: "Audit trail" },
  ];
  if (user?.role === "admin") links.push({ to: "/admin", icon: UserCog, label: "Admin" });

  const submit = (e) => { e.preventDefault(); nav(`/records?q=${encodeURIComponent(q.trim())}`); };

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <NavLink to="/dashboard" className="brand"><Logo /><div>ProofPulse<small>Provenance on chain</small></div></NavLink>
        <div className="nav-label">Workspace</div>
        {links.map((l) => (
          <NavLink key={l.to} to={l.to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <l.icon size={19} />{l.label}{l.pill > 0 && <span className="pill">{l.pill}</span>}
          </NavLink>
        ))}
        <div className="sidebar-foot">
          <div className="row" style={{ gap: 10, flexWrap: "nowrap" }}>
            <div style={{ width: 36, height: 36, borderRadius: 12, display: "grid", placeItems: "center", background: "linear-gradient(135deg,var(--accent),var(--accent-2))", color: "#fff", fontWeight: 700 }}>
              {user?.full_name?.[0]?.toUpperCase()}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ color: "var(--text)", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{user?.full_name}</div>
              <div>@{user?.username} · {user?.role}</div>
            </div>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <NavLink to="/settings" className="btn sm ghost" style={{ flex: 1 }}>Settings</NavLink>
            <button className="btn sm ghost" onClick={() => { logout(); nav("/"); }}><LogOut size={15} /> Sign out</button>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="btn icon ghost menu-btn" onClick={() => setOpen(true)} aria-label="Open menu"><Menu size={20} /></button>
          <form className="search" onSubmit={submit} role="search">
            <Search size={17} />
            <input className="input" placeholder="Search your records by title or ID (PP-…)" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search records" />
          </form>
          <div className="spacer" />
          <span className={`live ${live ? "" : "off"}`} title={live ? "Live updates connected" : "Reconnecting…"}><i />{live ? "Live" : "Offline"}</span>
          <ThemeToggle />
          <Notifications />
        </header>
        <main className="content">
          <AnimatePresence mode="wait">
            <motion.div key={loc.pathname} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      <nav className="bottom-nav" aria-label="Primary">
        {[links[0], links[1], links[2], links[3], links[4]].map((l) => (
          <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? "active" : "")}><l.icon size={20} />{l.label.split(" ")[0]}</NavLink>
        ))}
      </nav>
      {open && <div style={{ position: "fixed", inset: 0, zIndex: 80 }} onClick={() => setOpen(false)} />}
    </div>
  );
}

export function PublicNav() {
  const { user } = useAuth();
  return (
    <nav className="landing-nav">
      <NavLink to="/" className="brand" style={{ padding: 0 }}><Logo /><div>ProofPulse</div></NavLink>
      <div style={{ flex: 1 }} />
      <NavLink to="/verify" className="btn ghost sm hide-sm"><ShieldCheck size={16} /> Verify</NavLink>
      <ThemeToggle />
      {user ? <NavLink to="/dashboard" className="btn primary sm">Open dashboard</NavLink> : (<><NavLink to="/login" className="btn sm">Sign in</NavLink><NavLink to="/signup" className="btn primary sm hide-sm">Get started</NavLink></>)}
    </nav>
  );
}
