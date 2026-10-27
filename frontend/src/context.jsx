import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, getToken, setToken } from "./api";

/* ───── theme ───── */
const ThemeCtx = createContext(null);
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => document.documentElement.getAttribute("data-theme") || "dark");
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("pp-theme", theme); } catch { /* ignore */ }
  }, [theme]);
  const value = useMemo(() => ({ theme, toggle: () => setTheme((t) => (t === "dark" ? "light" : "dark")) }), [theme]);
  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}
export const useTheme = () => useContext(ThemeCtx);

/* ───── toasts ───── */
const ToastCtx = createContext(null);
export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const push = useCallback((t) => {
    const id = crypto.randomUUID();
    setItems((s) => [...s.slice(-3), { id, kind: "info", ...t }]);
    setTimeout(() => setItems((s) => s.filter((x) => x.id !== id)), t.duration || 5200);
  }, []);
  const dismiss = (id) => setItems((s) => s.filter((x) => x.id !== id));
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`} onClick={() => { dismiss(t.id); t.onClick?.(); }} role="status">
            <div className="tdot" />
            <div><b>{t.title}</b>{t.body && <span>{t.body}</span>}</div>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

/* ───── auth + live socket ───── */
const AuthCtx = createContext(null);
const listeners = new Set();
export const onLive = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [live, setLive] = useState(false);
  const [unread, setUnread] = useState(0);
  const toast = useToast();
  const wsRef = useRef(null);

  const refreshUnread = useCallback(() => api.notifications().then((r) => setUnread(r.unread)).catch(() => {}), []);

  const logout = useCallback(() => { setToken(null); setUser(null); setUnread(0); }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) { setReady(true); return; }
    api.me().then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);

  useEffect(() => {
    window.addEventListener("pp-logout", logout);
    return () => window.removeEventListener("pp-logout", logout);
  }, [logout]);

  // WebSocket with auto-reconnect
  useEffect(() => {
    if (!user) return undefined;
    let closed = false;
    let timer; let ping;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const base = import.meta.env.VITE_API_URL ? import.meta.env.VITE_API_URL.replace(/^http/, "ws") : `${proto}://${location.host}`;
      const ws = new WebSocket(`${base}/ws?token=${encodeURIComponent(getToken() || "")}`);
      wsRef.current = ws;
      ws.onopen = () => { setLive(true); ping = setInterval(() => ws.readyState === 1 && ws.send("ping"), 25000); };
      ws.onmessage = (m) => {
        let msg; try { msg = JSON.parse(m.data); } catch { return; }
        if (msg.event === "notification") {
          const d = msg.data;
          setUnread((n) => n + 1);
          toast({ title: d.title, body: d.body, kind: d.kind, onClick: () => d.record && (location.href = `/records/${d.record}`) });
        }
        listeners.forEach((fn) => fn(msg));
      };
      ws.onclose = () => { setLive(false); clearInterval(ping); if (!closed) timer = setTimeout(connect, 3000); };
      ws.onerror = () => ws.close();
    };
    connect();
    refreshUnread();
    return () => { closed = true; clearTimeout(timer); clearInterval(ping); wsRef.current?.close(); };
  }, [user, toast, refreshUnread]);

  const signIn = useCallback(({ token, user: u }) => { setToken(token); setUser(u); }, []);
  const value = useMemo(() => ({ user, ready, live, unread, setUnread, refreshUnread, signIn, logout }), [user, ready, live, unread, refreshUnread, signIn, logout]);
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}
export const useAuth = () => useContext(AuthCtx);

/** Re-run `fn` whenever one of the named live events arrives. */
export function useLive(events, fn) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => onLive((msg) => { if (events.includes(msg.event)) ref.current(msg); }), [events.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
}
