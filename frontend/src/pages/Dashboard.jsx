import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Activity, BadgeCheck, ClipboardCheck, Eye, FilePlus2, Files, GitBranch } from "lucide-react";
import { api } from "../api";
import { useAuth, useLive } from "../context";
import { Donut, RiskBars, TrendChart } from "../components/Charts";
import { Empty, PageHead, RiskBadge, Ring, Skeleton, Stat, StatusBadge, short, timeAgo } from "../components/ui";

const ACTION_LABEL = {
  RECORD_REGISTERED: "Registered a record", VERSION_ADDED: "Added a version", APPROVAL_REQUESTED: "Requested a review", APPROVAL_APPROVED: "Approved a record",
  APPROVAL_REJECTED: "Rejected a record", RECORD_REVOKED: "Revoked a record", LOGIN: "Signed in", INTEGRITY_CHECK: "Ran an integrity check",
  CERTIFICATE_ISSUED: "Issued a certificate", FILE_DOWNLOADED: "Downloaded a stored file", USER_REGISTERED: "Created the account",
};

export default function Dashboard() {
  const { user } = useAuth();
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.dashboard().then(setD).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useLive(["stats", "approvals", "verification", "notification"], load);

  if (err) return <div className="card err">{err}</div>;
  if (!d) return <div className="col"><Skeleton h={90} /><div className="grid g4"><Skeleton h={110} /><Skeleton h={110} /><Skeleton h={110} /><Skeleton h={110} /></div><Skeleton h={260} /></div>;
  const t = d.totals;

  return (
    <>
      <PageHead title={`Hello, ${user.full_name.split(" ")[0]}`} subtitle="Your provenance activity, updated live from the chain.">
        <Link to="/register" className="btn primary"><FilePlus2 size={17} /> Register a file</Link>
      </PageHead>

      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Stat icon={Files} label="Registered records" value={t.records} hint={`${t.versions} versions on chain`} />
        <Stat icon={BadgeCheck} label="Average trust score" value={t.avg_trust} suffix="/100" />
        <Stat icon={ClipboardCheck} label="Reviews waiting for you" value={t.pending_reviews} hint={t.pending_reviews ? "Open the Approvals page" : "Nothing pending"} />
        <Stat icon={Eye} label="Verifications of your records" value={t.verifications_of_mine} />
      </div>

      <div className="grid g-main" style={{ marginBottom: 16 }}>
        <motion.div className="card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <div className="card-title"><Activity size={18} /> Registrations, last 14 days</div>
          <TrendChart data={d.registrations_per_day} name="Records" />
        </motion.div>
        <motion.div className="card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }}>
          <div className="card-title">Workflow status</div>
          <Donut data={d.status_distribution} height={170} />
        </motion.div>
      </div>

      <div className="grid g-main">
        <motion.div className="card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.22 }}>
          <div className="row between"><div className="card-title"><GitBranch size={18} /> Recent records</div><Link to="/records" className="small">View all</Link></div>
          {d.recent_records.length === 0 ? (
            <Empty title="No records yet">Register your first file to anchor its fingerprint on the blockchain.</Empty>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Record</th><th>Status</th><th>Risk</th><th>Trust</th></tr></thead>
                <tbody>
                  {d.recent_records.map((r) => (
                    <tr key={r.public_id} className="click">
                      <td><Link to={`/records/${r.public_id}`} style={{ fontWeight: 600 }}>{r.title}</Link><div className="small muted mono">{r.public_id}</div></td>
                      <td><StatusBadge status={r.status} /></td>
                      <td><RiskBadge level={r.risk_level} /></td>
                      <td><b>{r.trust_score}</b></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </motion.div>
        <div className="col">
          <motion.div className="card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.26 }}>
            <div className="card-title">Risk profile</div>
            <RiskBars data={d.risk_distribution} height={150} />
          </motion.div>
          <motion.div className="card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
            <div className="row between"><div className="card-title">Your activity</div><Link to="/audit" className="small">Audit trail</Link></div>
            <div className="stack-sm">
              {d.recent_activity.length === 0 && <div className="small muted">No activity yet.</div>}
              {d.recent_activity.map((a) => (
                <div key={a.seq} className="row between small" style={{ flexWrap: "nowrap", gap: 12 }}>
                  <span>{ACTION_LABEL[a.action] || a.action.replaceAll("_", " ").toLowerCase()}{a.record ? <> · <span className="mono">{short(a.record, 7, 4)}</span></> : null}</span>
                  <span className="muted" style={{ whiteSpace: "nowrap" }}>{timeAgo(a.ts)}</span>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </>
  );
}
