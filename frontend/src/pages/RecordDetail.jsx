import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Award, Ban, CheckCircle2, ClipboardCheck, Download, FilePlus2, FileSearch, GitCommit, History, Link2, ScanSearch, ShieldAlert, ShieldCheck, Users, XCircle } from "lucide-react";
import { api, download, sha256File } from "../api";
import { useAuth, useLive, useToast } from "../context";
import { RiskReport, TrustPanel } from "../components/Analysis";
import ReviewerPicker from "../components/ReviewerPicker";
import { Dropzone, Empty, Hash, Modal, RiskBadge, Ring, Skeleton, Spinner, StatusBadge, Tabs, Visibility, fmtBytes, fmtDate, short, timeAgo } from "../components/ui";

function AddVersionModal({ rec, open, onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [note, setNote] = useState("");
  const [store, setStore] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async () => {
    setBusy(true); setErr("");
    try {
      const f = new FormData();
      f.append("file", file); f.append("note", note); f.append("store_file", store ? "true" : "false");
      await api.addVersion(rec.public_id, f);
      setFile(null); setNote(""); onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title={`Add version ${rec.current_version + 1}`}>
      <div className="col">
        <div className="small muted">The new fingerprint is appended to the on-chain history; earlier versions stay verifiable. Existing approvals reset for the new version.</div>
        <Dropzone file={file} onFile={setFile} />
        <label className="field">What changed?<input className="input" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Fixed results table, added references" /></label>
        <label className="check"><input type="checkbox" checked={store} onChange={(e) => setStore(e.target.checked)} /><span>Keep an encrypted copy on the server</span></label>
        {err && <div className="err">{err}</div>}
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!file || busy} onClick={submit}>{busy ? <Spinner /> : <FilePlus2 size={16} />} Anchor new version</button>
        </div>
      </div>
    </Modal>
  );
}

function RequestModal({ rec, open, onClose, onDone }) {
  const [list, setList] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async () => {
    setBusy(true); setErr("");
    try { await api.requestApprovals(rec.public_id, list.map((u) => u.username)); setList([]); onDone(); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Request approvals">
      <div className="col">
        <div className="small muted">Reviewers will be notified to approve or reject version {rec.current_version}. Their decisions are recorded on chain.</div>
        <ReviewerPicker value={list} onChange={setList} />
        {err && <div className="err">{err}</div>}
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!list.length || busy} onClick={submit}>{busy ? <Spinner /> : <Users size={16} />} Send requests</button>
        </div>
      </div>
    </Modal>
  );
}

function RevokeModal({ rec, open, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async () => {
    setBusy(true); setErr("");
    try { await api.revoke(rec.public_id, reason); onDone(); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Revoke this record">
      <div className="col">
        <div className="small" style={{ color: "var(--bad)" }}>Revocation is permanent and public. Verifiers will see this record as revoked and it can no longer receive versions or approvals.</div>
        <label className="field">Reason (recorded in the audit trail; only its hash goes on chain)<textarea className="input" rows={3} value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} /></label>
        {err && <div className="err">{err}</div>}
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn danger" disabled={reason.trim().length < 3 || busy} onClick={submit}>{busy ? <Spinner /> : <Ban size={16} />} Revoke permanently</button>
        </div>
      </div>
    </Modal>
  );
}

function ProofTab({ rec }) {
  const [proof, setProof] = useState(null);
  const [fileRes, setFileRes] = useState(null);
  const [integrity, setIntegrity] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const toast = useToast();
  useEffect(() => { api.verify(rec.public_id).then(setProof).catch((e) => setErr(e.message)); }, [rec.public_id, rec.current_version, rec.status]);

  const checkFile = async (f) => {
    setBusy("file"); setFileRes(null);
    try { const sha = await sha256File(f); setFileRes({ name: f.name, r: await api.verifyHash(rec.public_id, sha) }); } catch (e) { toast({ title: "Check failed", body: e.message, kind: "danger" }); } finally { setBusy(""); }
  };
  const runIntegrity = async () => {
    setBusy("integrity");
    try { setIntegrity(await api.integrity(rec.public_id)); } catch (e) { toast({ title: "Integrity check failed", body: e.message, kind: "danger" }); } finally { setBusy(""); }
  };
  if (err) return <div className="card err">{err}</div>;
  if (!proof) return <Skeleton h={200} />;
  const ch = proof.chain;
  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="card">
        <div className="card-title"><Link2 size={18} /> Chain evidence</div>
        <div className="grid g2" style={{ gap: 12 }}>
          <div><div className="small muted">Network</div><b className="mono">{ch.network}</b></div>
          <div><div className="small muted">Contract</div><b className="mono">{short(ch.contract_address, 10, 8)}</b></div>
          <div><div className="small muted">Database ↔ chain consistency</div>{proof.consistency.ok ? <span className="badge b-good">Consistent</span> : <span className="badge b-bad">Mismatch</span>}</div>
          <div><div className="small muted">On-chain state</div>{ch.revoked ? <span className="badge b-bad">Revoked</span> : <span className="badge b-good">Active</span>}</div>
        </div>
        {!proof.consistency.ok && <ul style={{ paddingLeft: 18, marginTop: 10 }}>{proof.consistency.issues.map((i) => <li key={i} className="err small">{i}</li>)}</ul>}
        <div className="divider" />
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Ver.</th><th>Fingerprint on chain</th><th>Block time</th><th>Tx / block</th></tr></thead>
          <tbody>{ch.versions.map((v) => (
            <tr key={v.version_no}><td>v{v.version_no}</td><td className="mono">{short(v.content_hash, 16, 10)}</td><td>{fmtDate(v.timestamp)}</td><td className="mono">{v.tx_hash ? `${short(v.tx_hash, 8, 6)} · #${v.block_number}` : "-"}</td></tr>))}</tbody>
        </table></div>
      </div>

      <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card col">
          <div className="card-title"><FileSearch size={18} /> Check a file against the chain</div>
          <div className="small muted">Detect tampering: drop the copy you hold. It is hashed in your browser and compared with the on-chain fingerprints.</div>
          <Dropzone file={null} onFile={checkFile} hint="Hashed locally; not uploaded" />
          {busy === "file" && <Spinner />}
          {fileRes && (
            <div className={`signal ${fileRes.r.verdict === "AUTHENTIC" ? "info" : fileRes.r.verdict === "OUTDATED_VERSION" ? "medium" : "high"}`}>
              <h4>{fileRes.r.verdict === "AUTHENTIC" ? <CheckCircle2 size={16} color="var(--good)" /> : <XCircle size={16} color="var(--bad)" />} {fileRes.r.headline}</h4>
              <div className="why">{fileRes.name}: {fileRes.r.message}</div>
            </div>
          )}
        </div>
        {rec.can_manage && (
          <div className="card col">
            <div className="card-title"><ShieldCheck size={18} /> Server integrity check</div>
            <div className="small muted">Re-hashes every stored encrypted copy and compares it with both the database and the blockchain.</div>
            <button className="btn" onClick={runIntegrity} disabled={busy === "integrity"}>{busy === "integrity" ? <Spinner /> : <ScanSearch size={16} />} Run integrity check</button>
            {integrity && (
              <div className={`signal ${integrity.ok ? "info" : "high"}`}>
                <h4>{integrity.ok ? "All checks passed" : `${integrity.failures} version(s) failed`}</h4>
                {integrity.versions.map((v) => (
                  <div key={v.version_no} className="why">v{v.version_no}: chain {v.chain_matches == null ? "n/a" : v.chain_matches ? "✓ match" : "✗ MISMATCH"} · stored copy {v.stored ? (v.stored_matches ? "✓ intact" : "✗ ALTERED") : "not kept"}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ActivityTab({ id }) {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.audit({ record: id, page_size: 50 }).then((r) => setRows(r.items)).catch(() => setRows([])); }, [id]);
  if (!rows) return <Skeleton h={160} />;
  if (!rows.length) return <Empty icon={History} title="No activity yet" />;
  return (
    <div className="timeline">
      {rows.map((e) => (
        <div key={e.seq} className={`tl-item ${/REVOKED|REJECTED|TAMPER|FAIL/.test(e.action) ? "bad" : /APPROVED|REGISTERED|VERSION/.test(e.action) ? "good" : ""}`}>
          <div className="row between"><b className="small">{e.action.replaceAll("_", " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}</b><span className="small muted">{fmtDate(e.ts)}</span></div>
          <div className="small muted">by {e.actor}{e.tx_hash ? <> · tx <span className="mono">{short(e.tx_hash, 8, 6)}</span></> : null}</div>
        </div>
      ))}
    </div>
  );
}

export default function RecordDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const toast = useToast();
  const [rec, setRec] = useState(null);
  const [versions, setVersions] = useState(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState("overview");
  const [modal, setModal] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(() => {
    api.record(id).then((r) => { setRec(r); setErr(""); }).catch((e) => setErr(e.message));
    api.versions(id).then(setVersions).catch(() => setVersions(null));
  }, [id]);
  useEffect(() => { setRec(null); load(); }, [load]);
  useLive(["approvals", "stats"], (m) => { if (!m.data?.record || m.data.record === id) load(); });

  if (err) return <div className="card" style={{ maxWidth: 560, margin: "40px auto", textAlign: "center" }}><ShieldAlert size={34} color="var(--warn)" /><h3 style={{ marginTop: 8 }}>{err}</h3><p className="muted small">It may be private, or the ID may be wrong.</p><Link className="btn" to={`/verify/${id}`} style={{ marginTop: 12 }}>Try public verification</Link></div>;
  if (!rec) return <div className="col"><Skeleton h={120} /><Skeleton h={300} /></div>;

  const manage = rec.can_manage;
  const isOwner = rec.is_owner;
  const isAdmin = user.role === "admin";
  const revoked = rec.status === "REVOKED";
  const cur = rec.versions?.find((v) => v.version_no === rec.current_version);
  const curRisk = versions?.find((v) => v.version_no === rec.current_version)?.risk_report || cur?.risk_report;
  const done = (msg) => { setModal(""); toast({ title: msg, kind: "success" }); load(); };
  const getCert = async () => {
    setBusy("cert");
    try { await download(`/api/records/${rec.public_id}/certificate`, `ProofPulse-${rec.public_id}.pdf`); } catch (e) { toast({ title: "Could not create certificate", body: e.message, kind: "danger" }); } finally { setBusy(""); }
  };
  const getFile = async (v) => {
    try {
      const status = await download(`/api/records/${rec.public_id}/versions/${v}/file`, versions.find((x) => x.version_no === v).filename);
      toast({ title: status === "ok" ? "Downloaded. Integrity verified" : "Downloaded, but the stored copy FAILED its integrity check", kind: status === "ok" ? "success" : "danger" });
    } catch (e) { toast({ title: "Download failed", body: e.message, kind: "danger" }); }
  };

  const tabs = [{ id: "overview", label: "Overview" }];
  if (manage) tabs.push({ id: "versions", label: `Versions (${rec.version_count})` }, { id: "approvals", label: `Approvals (${rec.approvals?.length || 0})` }, { id: "risk", label: "Risk analysis" });
  tabs.push({ id: "proof", label: "Blockchain proof" });
  if (manage) tabs.push({ id: "activity", label: "Activity" });

  return (
    <>
      <motion.div className="card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: 16 }}>
        <div className="row between" style={{ alignItems: "flex-start", gap: 20 }}>
          <div style={{ flex: 1, minWidth: 260 }}>
            <div className="row" style={{ gap: 6, marginBottom: 8 }}><StatusBadge status={rec.status} /><RiskBadge level={rec.risk_level} score={rec.risk_score} /><Visibility v={rec.visibility} /><span className="badge b-mute">v{rec.current_version}</span></div>
            <h1 style={{ fontSize: "clamp(1.4rem,3vw,1.9rem)" }}>{rec.title || "Private record"}</h1>
            {rec.description && <p className="muted" style={{ marginTop: 6, maxWidth: 680 }}>{rec.description}</p>}
            <div style={{ maxWidth: 380, marginTop: 12 }}><Hash label="Record ID" value={rec.public_id} /></div>
            {revoked && <div className="err" style={{ marginTop: 10 }}>Revoked: {rec.revoked_reason}</div>}
          </div>
          <Ring value={rec.trust_score} size={104} label="trust" />
        </div>
        <div className="row" style={{ marginTop: 18 }}>
          <button className="btn primary" onClick={getCert} disabled={busy === "cert"}>{busy === "cert" ? <Spinner /> : <Award size={16} />} Certificate (PDF)</button>
          <Link className="btn" to={`/verify/${rec.public_id}`}><ShieldCheck size={16} /> Public verification</Link>
          {isOwner && !revoked && <button className="btn" onClick={() => setModal("version")}><FilePlus2 size={16} /> Add version</button>}
          {isOwner && !revoked && <button className="btn" onClick={() => setModal("request")}><Users size={16} /> Request approvals</button>}
          {(isOwner || isAdmin) && !revoked && <button className="btn danger" onClick={() => setModal("revoke")}><Ban size={16} /> Revoke</button>}
        </div>
      </motion.div>

      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      <div style={{ marginTop: 16 }}>
        {tab === "overview" && (
          <div className="grid g-main" style={{ alignItems: "start" }}>
            <div className="card col">
              <div className="card-title"><GitCommit size={18} /> Details</div>
              <div className="grid g2" style={{ gap: 14 }}>
                <div><div className="small muted">Owner</div><b>{rec.owner?.full_name || "Hidden"}</b></div>
                <div><div className="small muted">Category</div><b>{rec.category}</b></div>
                <div><div className="small muted">Registered</div><b>{fmtDate(rec.created_at)}</b></div>
                <div><div className="small muted">Last change</div><b>{timeAgo(rec.updated_at)}</b></div>
                {rec.filename && <div><div className="small muted">File</div><b>{rec.filename}</b> <span className="small muted">({fmtBytes(rec.size)})</span></div>}
                {rec.block_number != null && <div><div className="small muted">Anchored in block</div><b>#{rec.block_number}</b></div>}
              </div>
              {rec.tags?.length > 0 && <div className="row" style={{ gap: 6 }}>{rec.tags.map((t) => <span key={t} className="badge b-mute">{t}</span>)}</div>}
              <Hash label="Current fingerprint (SHA-256)" value={rec.sha256} />
              <Hash label="Anchoring transaction" value={rec.tx_hash} />
              {!manage && <div className="small muted">This is a public record. Version history, approvals and risk details are only visible to the owner and reviewers.</div>}
            </div>
            <div className="col">
              <div className="card" style={{ textAlign: "center" }}>
                <div className="qr-box" style={{ margin: "0 auto" }}><img src={api.qrUrl(rec.public_id)} alt={`QR code for ${rec.public_id}`} /></div>
                <div className="small muted" style={{ marginTop: 8 }}>Scan to verify. Print it on the document.</div>
              </div>
              {rec.trust && <div className="card"><div className="card-title">Trust score breakdown</div><TrustPanel trust={rec.trust} /></div>}
            </div>
          </div>
        )}

        {tab === "versions" && (
          <div className="timeline">
            {(versions || rec.versions).slice().reverse().map((v) => (
              <div key={v.version_no} className={`tl-item ${v.version_no === rec.current_version ? "good" : ""}`}>
                <div className="row between">
                  <b>Version {v.version_no}{v.version_no === rec.current_version ? " · current" : ""}</b>
                  <span className="small muted">{fmtDate(v.created_at)} · by {v.author.full_name}</span>
                </div>
                <div className="small" style={{ margin: "4px 0" }}>{v.change_note} · <span className="muted">{v.filename} · {fmtBytes(v.size)}</span></div>
                <div className="row" style={{ gap: 6 }}><RiskBadge level={v.risk_level} score={v.risk_score} />{v.stored ? <span className="badge b-info">encrypted copy kept</span> : <span className="badge b-mute">fingerprint only</span>}</div>
                <div className="grid g2" style={{ marginTop: 10, gap: 10 }}><Hash label="SHA-256" value={v.sha256} compact /><Hash label={`Tx · block #${v.block_number}`} value={v.tx_hash} compact /></div>
                {v.stored && (isOwner || isAdmin) && <button className="btn sm" style={{ marginTop: 10 }} onClick={() => getFile(v.version_no)}><Download size={14} /> Download &amp; verify</button>}
              </div>
            ))}
          </div>
        )}

        {tab === "approvals" && (
          <div className="card">
            <div className="row between"><div className="card-title"><ClipboardCheck size={18} /> Review workflow</div>{isOwner && !revoked && <button className="btn sm" onClick={() => setModal("request")}><Users size={14} /> Add reviewers</button>}</div>
            {!rec.approvals?.length ? <Empty icon={Users} title="No reviewers requested">Ask a supervisor or peer to approve this version. Their signed decision is recorded on chain.</Empty> : (
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Reviewer</th><th>Version</th><th>Decision</th><th>Comment</th><th>When</th></tr></thead>
                <tbody>{rec.approvals.map((a) => (
                  <tr key={a.id}>
                    <td><b>{a.approver.full_name}</b><div className="small muted">@{a.approver.username}</div></td>
                    <td>v{a.version_no}{a.version_no !== rec.current_version ? <span className="badge b-mute" style={{ marginLeft: 6 }}>superseded</span> : null}</td>
                    <td><StatusBadge status={a.status} /></td>
                    <td className="small" style={{ maxWidth: 260 }}>{a.comment || <span className="muted">-</span>}{a.tx_hash && <div className="mono muted">tx {short(a.tx_hash, 8, 6)}</div>}</td>
                    <td className="small muted">{fmtDate(a.decided_at || a.requested_at)}</td>
                  </tr>))}</tbody>
              </table></div>
            )}
          </div>
        )}

        {tab === "risk" && <div className="card"><div className="card-title">Risk analysis of version {rec.current_version}</div><RiskReport report={curRisk} /></div>}
        {tab === "proof" && <ProofTab rec={rec} />}
        {tab === "activity" && <div className="card"><ActivityTab id={rec.public_id} /></div>}
      </div>

      <AddVersionModal rec={rec} open={modal === "version"} onClose={() => setModal("")} onDone={() => done("New version anchored on chain")} />
      <RequestModal rec={rec} open={modal === "request"} onClose={() => setModal("")} onDone={() => done("Approval requests sent")} />
      <RevokeModal rec={rec} open={modal === "revoke"} onClose={() => setModal("")} onDone={() => done("Record revoked")} />
    </>
  );
}
