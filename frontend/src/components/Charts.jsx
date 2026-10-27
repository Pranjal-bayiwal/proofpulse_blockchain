import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTip } from "./ui";

const tick = { fill: "var(--muted)", fontSize: 11 };

export function TrendChart({ data, name = "Count", height = 220, color = "var(--accent)" }) {
  const rows = data.map((d) => ({ ...d, label: new Date(d.date + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }) }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={rows} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
        <defs>
          <linearGradient id={`g-${name}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.55} />
            <stop offset="100%" stopColor="var(--accent-2)" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 5" vertical={false} />
        <XAxis dataKey="label" tick={tick} tickLine={false} axisLine={false} interval="preserveStartEnd" />
        <YAxis tick={tick} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip content={<ChartTip />} cursor={{ stroke: "var(--border-strong)" }} />
        <Area type="monotone" dataKey="count" name={name} stroke={color} strokeWidth={2.4} fill={`url(#g-${name})`} animationDuration={900} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

const STATUS_COLORS = { REGISTERED: "#60a5fa", PENDING_APPROVAL: "#fbbf24", APPROVED: "#34d399", REJECTED: "#fb7185", REVOKED: "#94a3b8" };
const label = (k) => k.replace("_", " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());

export function Donut({ data, colors = STATUS_COLORS, height = 200 }) {
  const rows = Object.entries(data).filter(([, v]) => v > 0).map(([k, v]) => ({ name: label(k), value: v, key: k }));
  const total = rows.reduce((s, r) => s + r.value, 0);
  if (!total) return <div className="empty small" style={{ padding: 30 }}>No data yet</div>;
  return (
    <div className="row" style={{ gap: 18, flexWrap: "wrap" }}>
      <div style={{ width: height, height, flexShrink: 0, position: "relative" }}>
        <ResponsiveContainer>
          <PieChart>
            <Pie data={rows} dataKey="value" innerRadius="64%" outerRadius="92%" paddingAngle={3} stroke="none" animationDuration={900}>
              {rows.map((r) => <Cell key={r.key} fill={colors[r.key] || "#64748b"} />)}
            </Pie>
            <Tooltip content={<ChartTip />} />
          </PieChart>
        </ResponsiveContainer>
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", pointerEvents: "none", textAlign: "center" }}>
          <div><div style={{ fontFamily: "var(--font-display)", fontSize: "1.7rem", fontWeight: 700 }}>{total}</div><div className="small muted">total</div></div>
        </div>
      </div>
      <div className="stack-sm" style={{ minWidth: 150, flex: 1 }}>
        {rows.map((r) => (
          <div key={r.key} className="row small" style={{ gap: 8, flexWrap: "nowrap" }}>
            <i style={{ width: 10, height: 10, borderRadius: 3, background: colors[r.key] || "#64748b", flexShrink: 0 }} />
            <span style={{ whiteSpace: "nowrap" }}>{r.name}</span><b style={{ marginLeft: "auto" }}>{r.value}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

const RISK_COLORS = { LOW: "#34d399", MEDIUM: "#fbbf24", HIGH: "#fb7185" };
export function RiskBars({ data, height = 200 }) {
  const rows = ["LOW", "MEDIUM", "HIGH"].map((k) => ({ name: label(k), value: data[k] || 0, key: k }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 5" vertical={false} />
        <XAxis dataKey="name" tick={tick} tickLine={false} axisLine={false} />
        <YAxis tick={tick} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip content={<ChartTip />} cursor={{ fill: "var(--surface)" }} />
        <Bar dataKey="value" name="Records" radius={[8, 8, 0, 0]} animationDuration={900}>
          {rows.map((r) => <Cell key={r.key} fill={RISK_COLORS[r.key]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

const VERDICT_COLORS = { AUTHENTIC: "#34d399", REGISTERED: "#60a5fa", OUTDATED_VERSION: "#fbbf24", TAMPERED: "#fb7185", REVOKED: "#94a3b8", NOT_FOUND: "#a78bfa", ANCHOR_MISMATCH: "#f43f5e", ON_CHAIN_ONLY: "#22d3ee" };
export const VerdictDonut = ({ data }) => <Donut data={data} colors={VERDICT_COLORS} />;
