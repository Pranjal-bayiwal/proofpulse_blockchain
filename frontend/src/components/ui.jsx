import { useEffect, useRef, useState } from "react";
import { animate, AnimatePresence, motion } from "framer-motion";
import { Check, Copy, Inbox, UploadCloud } from "lucide-react";

/* ───── formatters ───── */
export const fmtDate = (iso, withTime = true) => {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString(undefined, withTime
    ? { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }
    : { year: "numeric", month: "short", day: "numeric" });
};
export const timeAgo = (iso) => {
  if (!iso) return "";
  const s = Math.max(1, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};
export const fmtBytes = (n) => {
  if (n == null) return "-";
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
};
export const short = (h, a = 10, b = 6) => (h && h.length > a + b + 3 ? `${h.slice(0, a)}…${h.slice(-b)}` : h || "-");

/* ───── logo ───── */
export function Logo({ size = 34 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#22d3ee" /><stop offset="1" stopColor="#8b5cf6" /></linearGradient>
      </defs>
      <path d="M32 7 52 15v16c0 12.5-8 21.5-20 26C20 52.500 12 43.500 12 31V15z" fill="none" stroke="url(#lg)" strokeWidth="4.5" strokeLinejoin="round" />
      <path d="M19 33h8l5-11 6 19 4-8h6" fill="none" stroke="#a5f3fc" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ───── badges ───── */
const STATUS = {
  REGISTERED: ["b-info", "Registered"], PENDING_APPROVAL: ["b-warn", "Pending approval"], APPROVED: ["b-good", "Approved"],
  REJECTED: ["b-bad", "Rejected"], REVOKED: ["b-bad", "Revoked"], PENDING: ["b-warn", "Pending"],
};
export const StatusBadge = ({ status }) => {
  const [cls, label] = STATUS[status] || ["b-mute", status];
  return <span className={`badge ${cls}`}>{label}</span>;
};
export const RiskBadge = ({ level, score }) => {
  const cls = level === "HIGH" ? "b-bad" : level === "MEDIUM" ? "b-warn" : "b-good";
  return <span className={`badge ${cls}`}>{level ? level[0] + level.slice(1).toLowerCase() : "-"} risk{score != null ? ` · ${score}` : ""}</span>;
};
export const Visibility = ({ v }) => <span className={`badge ${v === "public" ? "b-info" : "b-mute"}`}>{v === "public" ? "Public" : "Private"}</span>;

/* ───── hash with copy ───── */
export function Hash({ value, label, compact }) {
  const [done, setDone] = useState(false);
  if (!value) return null;
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); setDone(true); setTimeout(() => setDone(false), 1400); } catch { /* clipboard blocked */ }
  };
  return (
    <div>
      {label && <div className="small muted" style={{ marginBottom: 4 }}>{label}</div>}
      <div className="hash">
        <span>{compact ? short(value, 14, 8) : value}</span>
        <button className="copy" onClick={copy} aria-label="Copy" title="Copy">{done ? <Check size={15} color="var(--good)" /> : <Copy size={15} />}</button>
      </div>
    </div>
  );
}

/* ───── animated number ───── */
export function CountUp({ value, duration = 0.9 }) {
  const ref = useRef(null);
  const prev = useRef(0);
  useEffect(() => {
    const controls = animate(prev.current, Number(value) || 0, {
      duration, ease: "easeOut",
      onUpdate: (v) => { if (ref.current) ref.current.textContent = Math.round(v).toLocaleString(); },
    });
    prev.current = Number(value) || 0;
    return () => controls.stop();
  }, [value, duration]);
  return <span ref={ref}>0</span>;
}

export function Stat({ icon: Icon, label, value, suffix, hint }) {
  return (
    <motion.div className="card hover stat" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }}>
      <div className="label"><span className="icon"><Icon size={17} /></span>{label}</div>
      <div className="value"><CountUp value={value} />{suffix}</div>
      {hint && <div className="small muted">{hint}</div>}
    </motion.div>
  );
}

/* ───── score ring ───── */
export function Ring({ value = 0, size = 120, stroke = 10, label, color, invert }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, value));
  const good = invert ? 100 - v : v;
  const col = color || (good >= 70 ? "var(--good)" : good >= 45 ? "var(--warn)" : "var(--bad)");
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-2)" strokeWidth={stroke} />
        <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={col} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - v / 100) }}
          transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }} style={{ filter: `drop-shadow(0 0 6px ${col})` }} />
      </svg>
      <div className="num" style={{ fontSize: size * 0.27 }}>
        <CountUp value={v} />
        {label && <small>{label}</small>}
      </div>
    </div>
  );
}

export const Spinner = () => <span className="spinner" role="progressbar" aria-label="Loading" />;
export const Skeleton = ({ h = 20, w = "100%", style }) => <div className="skeleton" style={{ height: h, width: w, ...style }} />;
export const Empty = ({ icon: Icon = Inbox, title, children }) => (
  <div className="empty"><Icon size={34} /><div style={{ fontWeight: 600, color: "var(--text)" }}>{title}</div>{children && <div className="small" style={{ marginTop: 4 }}>{children}</div>}</div>
);

export function Modal({ open, onClose, title, children, wide }) {
  useEffect(() => {
    if (!open) return undefined;
    const h = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
          <motion.div className="modal" role="dialog" aria-modal="true" aria-label={title} style={wide ? { maxWidth: 680 } : undefined}
            initial={{ opacity: 0, y: 24, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 16 }} transition={{ duration: 0.25 }}>
            <h3>{title}</h3>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Dropzone({ file, onFile, hint = "Any document, dataset, image or archive up to 25 MB" }) {
  const [drag, setDrag] = useState(false);
  const input = useRef(null);
  return (
    <div className={`dropzone ${drag ? "drag" : ""} ${file ? "has" : ""}`} role="button" tabIndex={0}
      onClick={() => input.current?.click()} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); e.dataTransfer.files[0] && onFile(e.dataTransfer.files[0]); }}>
      <UploadCloud size={34} />
      {file ? (<><b>{file.name}</b><span className="small muted">{fmtBytes(file.size)} · click to replace</span></>) : (<><b>Drop a file here or click to browse</b><span className="small muted">{hint}</span></>)}
      <input ref={input} type="file" hidden onChange={(e) => e.target.files[0] && onFile(e.target.files[0])} />
    </div>
  );
}

export const Tabs = ({ tabs, value, onChange }) => (
  <div className="tabs" role="tablist">
    {tabs.map((t) => (
      <button key={t.id} role="tab" aria-selected={value === t.id} className={`tab ${value === t.id ? "active" : ""}`} onClick={() => onChange(t.id)}>{t.label}</button>
    ))}
  </div>
);

export const PageHead = ({ title, subtitle, children }) => (
  <div className="page-head"><div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div><div className="row">{children}</div></div>
);

export const ChartTip = ({ active, payload, label, unit = "" }) =>
  active && payload?.length ? (
    <div className="chart-tip"><b>{label ?? payload[0].name}</b>{payload.map((p) => <div key={p.dataKey || p.name} style={{ color: p.color || p.payload?.fill }}>{p.name}: {p.value}{unit}</div>)}</div>
  ) : null;
