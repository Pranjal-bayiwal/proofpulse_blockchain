import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Check, ClipboardCheck, Send, X } from "lucide-react";
import { api } from "../api";
import { useLive, useToast } from "../context";
import { Empty, Hash, Modal, PageHead, RiskBadge, Skeleton, Spinner, StatusBadge, Tabs, fmtBytes, timeAgo } from "../components/ui";

function DecideModal({ item, approve, onClose, onDone }) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async () => {
    setBusy(true); setErr("");
    try { await api.decide(item.id, approve, comment); setComment(""); onDone(approve); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <Modal open={!!item} onClose={onClose} title={approve ? "Approve this version" : "Reject this version"}>
      {item && (
        <div className="col">
          <div className="small muted"><b>{item.record_title}</b> · version {item.version_no}. Your decision is written to the blockchain and cannot be changed.</div>
          <label className="field">{approve ? "Comment (optional)" : "Reason for rejection (required)"}
            <textarea className="input" rows={3} maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} autoFocus />
          </label>
          {err && <div className="err">{err}</div>}
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button className="btn ghost" onClick={onClose}>Cancel</button>
            <button className={`btn ${approve ? "good" : "danger"}`} disabled={busy || (!approve && comment.trim().length < 3)} onClick={submit}>
              {busy ? <Spinner /> : approve ? <Check size={16} /> : <X size={16} />} {approve ? "Approve on chain" : "Reject on chain"}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

export default function Approvals() {
  const toast = useToast();
  const [tab, setTab] = useState("PENDING");
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState("");
  const [dlg, setDlg] = useState(null); // { item, approve }

  const load = useCallback(() => {
    const p = tab === "SENT" ? api.sent() : api.inbox(tab === "DECIDED" ? "ALL" : "PENDING");
    p.then((r) => setRows(tab === "DECIDED" ? r.filter((x) => x.status !== "PENDING") : r)).catch((e) => setErr(e.message));
  }, [tab]);
  useEffect(() => { setRows(null); load(); }, [load]);
  useLive(["approvals", "notification"], load);

  return (
    <>
      <PageHead title="Approvals" subtitle="Review requests addressed to you, and track the ones you sent." />
      <Tabs tabs={[{ id: "PENDING", label: "Waiting for me" }, { id: "DECIDED", label: "Decided" }, { id: "SENT", label: "Sent by me" }]} value={tab} onChange={setTab} />
      <div style={{ marginTop: 16 }}>
        {err && <div className="card err">{err}</div>}
        {!rows && !err && <div className="col"><Skeleton h={130} /><Skeleton h={130} /></div>}
        {rows && rows.length === 0 && <Empty icon={tab === "SENT" ? Send : ClipboardCheck} title={tab === "PENDING" ? "Nothing to review" : "Nothing here yet"}>{tab === "PENDING" ? "When someone asks you to approve a record, it appears here." : ""}</Empty>}
        <div className="col">
          {rows?.map((a, i) => (
            <motion.div key={a.id} className="card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 6) * 0.05 }}>
              <div className="row between" style={{ alignItems: "flex-start", gap: 14 }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <Link to={`/records/${a.record_public_id}`} style={{ fontWeight: 600, fontSize: "1.05rem" }}>{a.record_title}</Link>
                  <div className="small muted mono">{a.record_public_id} · v{a.version_no}</div>
                  <div className="small" style={{ marginTop: 6 }}>
                    {tab === "SENT" ? <>Asked <b>{a.approver.full_name}</b></> : <>Requested by <b>{a.requested_by.full_name}</b></>} · <span className="muted">{timeAgo(a.requested_at)}</span>
                  </div>
                </div>
                <StatusBadge status={a.status} />
              </div>
              {a.version && (
                <div className="row" style={{ marginTop: 12, gap: 8 }}>
                  <RiskBadge level={a.version.risk_level} score={a.version.risk_score} />
                  <span className="badge b-mute">{a.version.filename} · {fmtBytes(a.version.size)}</span>
                  {a.version.note && <span className="small muted">“{a.version.note}”</span>}
                </div>
              )}
              {a.version && <div style={{ marginTop: 10, maxWidth: 520 }}><Hash label="Fingerprint you are approving" value={a.version.sha256} compact /></div>}
              {a.comment && <div className="small" style={{ marginTop: 10 }}>Comment: “{a.comment}”</div>}
              {tab === "PENDING" && a.status === "PENDING" && (
                a.superseded ? <div className="small muted" style={{ marginTop: 12 }}>This version was superseded by a newer one; wait for a new request.</div> : (
                  <div className="row" style={{ marginTop: 14 }}>
                    <button className="btn good" onClick={() => setDlg({ item: a, approve: true })}><Check size={16} /> Approve</button>
                    <button className="btn danger" onClick={() => setDlg({ item: a, approve: false })}><X size={16} /> Reject</button>
                    <Link className="btn ghost" to={`/records/${a.record_public_id}`}>Inspect record</Link>
                  </div>
                )
              )}
            </motion.div>
          ))}
        </div>
      </div>
      <DecideModal item={dlg?.item} approve={!!dlg?.approve} onClose={() => setDlg(null)} onDone={(ok) => { setDlg(null); toast({ title: ok ? "Approved and recorded on chain" : "Rejection recorded on chain", kind: ok ? "success" : "warning" }); load(); }} />
    </>
  );
}
