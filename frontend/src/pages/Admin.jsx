import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Activity, AlertOctagon, Boxes, ClipboardList, Cpu, Eye, Files, RefreshCw, ScanSearch, ShieldCheck, Users } from "lucide-react";
import { api } from "../api";
import { useAuth, useLive, useToast } from "../context";
import { Donut, RiskBars, TrendChart, VerdictDonut } from "../components/Charts";
import { Hash, PageHead, RiskBadge, Skeleton, Spinner, Stat, StatusBadge, Tabs, fmtDate, short, timeAgo } from "../components/ui";

function Overview({ d }) {
  const c = d.chain;
  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="grid g4">
        <Stat icon={Users} label="Users" value={d.totals.users} />
        <Stat icon={Files} label="Records" value={d.totals.records} hint={`${d.totals.versions} versions`} />
        <Stat icon={Eye} label="Verifications" value={d.totals.verifications} />
        <Stat icon={AlertOctagon} label="Tamper detections" value={d.totals.tamper_detections} hint={`${d.totals.approvals_pending} approvals pending`} />
      </div>
      <div className="grid g2">
        <div className="card"><div className="card-title"><Activity size={18} /> Registrations per day</div><TrendChart data={d.registrations_per_day} name="Registrations" height={200} /></div>
        <div className="card"><div className="card-title"><ScanSearch size={18} /> Verifications per day</div><TrendChart data={d.verifications_per_day} name="Verifications" height={200} /></div>
      </div>
      <div className="grid g3">
        <div className="card"><div className="card-title">Record status</div><Donut data={d.status_distribution} height={150} /></div>
        <div className="card"><div className="card-title">Verification outcomes</div><VerdictDonut data={d.verdict_distribution} /></div>
        <div className="card"><div className="card-title">Risk levels</div><RiskBars data={d.risk_distribution} height={150} /></div>
      </div>
      <div className="grid g-main">
        <div className="card">
          <div className="card-title"><AlertOctagon size={18} /> Highest-risk records</div>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Record</th><th>Owner</th><th>Risk</th></tr></thead>
            <tbody>{d.top_risk.map((r) => (
              <tr key={r.public_id}><td><Link to={`/records/${r.public_id}`} style={{ fontWeight: 600 }}>{r.title}</Link><div className="small muted mono">{r.public_id}</div></td><td>@{r.owner}</td><td><RiskBadge level={r.risk_level} score={r.risk_score} /></td></tr>))}</tbody>
          </table></div>
        </div>
        <div className="card">
          <div className="card-title"><Boxes size={18} /> Blockchain node</div>
          {c.connected ? (
            <div className="col" style={{ gap: 10 }}>
              <div className="row"><span className="badge b-good">Connected</span><span className="badge b-mute">{c.mode}</span>{c.persistent ? <span className="badge b-info">persistent</span> : <span className="badge b-warn">ephemeral</span>}</div>
              <div className="grid g2" style={{ gap: 10 }}>
                <div><div className="small muted">Network ID</div><b>{c.network_id}</b></div>
                <div><div className="small muted">Block height</div><b>{c.block_number}</b></div>
                <div><div className="small muted">Records on chain</div><b>{c.total_records}</b></div>
                <div><div className="small muted">Approvals on chain</div><b>{c.total_approvals}</b></div>
              </div>
              <Hash label="Contract" value={c.contract_address} compact />
              <Hash label="Registrar account" value={c.registrar} compact />
            </div>
          ) : <div className="err">Blockchain not connected{c.error ? `: ${c.error}` : ""}</div>}
        </div>
      </div>
    </div>
  );
}

function UsersTab() {
  const { user: me } = useAuth();
  const toast = useToast();
  const [rows, setRows] = useState(null);
  const load = useCallback(() => api.adminUsers().then(setRows).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  const patch = async (u, body) => {
    try { await api.adminPatchUser(u.id, body); toast({ title: `Updated @${u.username}`, kind: "success" }); load(); } catch (e) { toast({ title: "Update failed", body: e.message, kind: "danger" }); }
  };
  if (!rows) return <Skeleton h={260} />;
  return (
    <div className="card" style={{ padding: 8 }}>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>User</th><th>Email</th><th>Role</th><th>Records</th><th>Last sign-in</th><th>Status</th><th /></tr></thead>
        <tbody>{rows.map((u) => (
          <tr key={u.id}>
            <td><b>{u.full_name}</b><div className="small muted">@{u.username}{u.organization ? ` · ${u.organization}` : ""}</div></td>
            <td className="small">{u.email}</td>
            <td><span className={`badge ${u.role === "admin" ? "b-info" : "b-mute"}`}>{u.role}</span></td>
            <td>{u.records}</td>
            <td className="small muted">{u.last_login ? timeAgo(u.last_login) : "never"}</td>
            <td>{u.is_active ? <span className="badge b-good">Active</span> : <span className="badge b-bad">Disabled</span>}</td>
            <td><div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
              <button className="btn sm" disabled={u.id === me.id} onClick={() => patch(u, { role: u.role === "admin" ? "user" : "admin" })}>{u.role === "admin" ? "Make user" : "Make admin"}</button>
              <button className="btn sm" disabled={u.id === me.id} onClick={() => patch(u, { is_active: !u.is_active })}>{u.is_active ? "Disable" : "Enable"}</button>
            </div></td>
          </tr>))}</tbody>
      </table></div>
    </div>
  );
}

function RecordsTab() {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.adminRecords().then(setRows).catch(() => setRows([])); }, []);
  if (!rows) return <Skeleton h={260} />;
  return (
    <div className="card" style={{ padding: 8 }}>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Record</th><th>Owner</th><th>Status</th><th>Risk</th><th>Trust</th><th>Created</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.public_id}>
            <td><Link to={`/records/${r.public_id}`} style={{ fontWeight: 600 }}>{r.title}</Link><div className="small muted mono">{r.public_id}</div></td>
            <td className="small">{r.owner?.full_name}</td><td><StatusBadge status={r.status} /></td><td><RiskBadge level={r.risk_level} score={r.risk_score} /></td>
            <td><b>{r.trust_score}</b></td><td className="small muted">{fmtDate(r.created_at)}</td>
          </tr>))}</tbody>
      </table></div>
    </div>
  );
}

function IntegrityTab({ chainInfo, onChange }) {
  const toast = useToast();
  const [scan, setScan] = useState(null);
  const [busy, setBusy] = useState("");
  const run = async (kind) => {
    setBusy(kind);
    try {
      if (kind === "scan") setScan(await api.adminScan());
      else { const r = await api.adminReanchor(); toast({ title: "Re-anchored", body: `${r.records} records, ${r.versions} versions, ${r.decisions} decisions`, kind: "success" }); onChange(); }
    } catch (e) { toast({ title: kind === "scan" ? "Scan failed" : "Re-anchor refused", body: e.message, kind: "danger" }); } finally { setBusy(""); }
  };
  return (
    <div className="grid g2" style={{ alignItems: "start" }}>
      <div className="card col">
        <div className="card-title"><ShieldCheck size={18} /> Global integrity scan</div>
        <div className="small muted">Compares every database record with the blockchain and re-hashes every stored encrypted file. Any mismatch lowers that record's trust score and notifies its owner.</div>
        <button className="btn primary" onClick={() => run("scan")} disabled={busy === "scan"}>{busy === "scan" ? <Spinner /> : <ScanSearch size={16} />} Scan all records now</button>
        {scan && (
          <div className={`signal ${scan.ok ? "info" : "high"}`}>
            <h4>{scan.ok ? `All ${scan.scanned} records verified` : `${scan.issues.length} problem(s) in ${scan.scanned} records`}</h4>
            {scan.issues.map((i, k) => <div key={k} className="why"><Link to={`/records/${i.record}`} className="mono">{i.record}</Link>{i.version ? ` v${i.version}` : ""}: {i.problem}</div>)}
          </div>
        )}
      </div>
      <div className="card col">
        <div className="card-title"><RefreshCw size={18} /> Recovery: re-anchor</div>
        <div className="small muted">If a local development chain was reset, this replays every database record onto the empty chain. It refuses to run when the chain already holds records, and the new timestamps are the replay time, not the original registration time. Production deployments on a public network should never need it.</div>
        <button className="btn" onClick={() => run("reanchor")} disabled={busy === "reanchor" || (chainInfo?.total_records ?? 0) > 0}>{busy === "reanchor" ? <Spinner /> : <Cpu size={16} />} Re-anchor to chain</button>
        {(chainInfo?.total_records ?? 0) > 0 && <div className="small muted">Disabled: the chain already holds {chainInfo.total_records} record(s).</div>}
      </div>
    </div>
  );
}

export default function Admin() {
  const [tab, setTab] = useState("overview");
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.adminOverview().then((r) => { setD(r); setErr(""); }).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useLive(["stats", "verification", "approvals"], load);

  return (
    <>
      <PageHead title="Admin dashboard" subtitle="Platform health, users, risk and chain integrity at a glance." />
      <Tabs tabs={[{ id: "overview", label: "Overview" }, { id: "users", label: "Users" }, { id: "records", label: "All records" }, { id: "integrity", label: "Integrity" }]} value={tab} onChange={setTab} />
      <motion.div style={{ marginTop: 16 }} key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        {err && <div className="card err">{err}</div>}
        {tab === "overview" && (d ? <Overview d={d} /> : <Skeleton h={400} />)}
        {tab === "users" && <UsersTab />}
        {tab === "records" && <RecordsTab />}
        {tab === "integrity" && <IntegrityTab chainInfo={d?.chain} onChange={load} />}
      </motion.div>
    </>
  );
}
