import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Award, Boxes, CheckCircle2, FileSearch, Fingerprint, QrCode, ScanSearch, ShieldAlert, XCircle } from "lucide-react";
import { api, download, sha256File } from "../api";
import { useAuth, useToast } from "../context";
import QrScanner from "../components/QrScanner";
import Verdict from "../components/Verdict";
import { Dropzone, Hash, PageHead, RiskBadge, Spinner, StatusBadge, Tabs, fmtBytes, fmtDate, short } from "../components/ui";

const EVENT_LABEL = {
  RecordRegistered: "Registered", VersionAdded: "Version added", DecisionRecorded: "Reviewer decision", RecordRevoked: "Revoked",
};

function FileCheck({ fc, name }) {
  const ok = fc.matches;
  return (
    <div className="card" style={{ borderColor: ok ? "color-mix(in srgb, var(--good) 40%, transparent)" : "color-mix(in srgb, var(--bad) 45%, transparent)" }}>
      <div className="card-title">{ok ? <CheckCircle2 size={18} color="var(--good)" /> : <XCircle size={18} color="var(--bad)" />} File integrity check</div>
      <div className="col">
        <div className="small muted">{name ? <>Fingerprint of <b>{name}</b> was computed locally in your browser; the file was not uploaded.</> : "Fingerprint supplied by the verifier."}</div>
        <Hash label="Your file (SHA-256)" value={fc.sha256} />
        <Hash label={ok ? `Registered fingerprint (version ${fc.matched_version})` : "Registered fingerprint (latest version)"} value={ok ? fc.sha256 : fc.expected_latest} />
        {!ok && <div className="err">The two fingerprints differ, so the file is not the registered document.</div>}
      </div>
    </div>
  );
}

function Result({ r, fileName }) {
  const toast = useToast();
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const cert = async () => {
    setBusy(true);
    try { await download(`/api/records/${r.public_id}/certificate`, `ProofPulse-${r.public_id}.pdf`); } catch (e) { toast({ title: "Could not download certificate", body: e.message, kind: "danger" }); } finally { setBusy(false); }
  };
  const rec = r.record;
  const ch = r.chain;
  return (
    <div className="col" style={{ gap: 16 }}>
      <Verdict result={r} fileName={fileName} />
      {r.file_check && <FileCheck fc={r.file_check} name={fileName} />}
      {!r.consistency.ok && (
        <div className="card" style={{ borderColor: "color-mix(in srgb, var(--bad) 50%, transparent)" }}>
          <div className="card-title"><ShieldAlert size={18} color="var(--bad)" /> Consistency problems</div>
          <ul style={{ paddingLeft: 18 }}>{r.consistency.issues.map((i) => <li key={i} className="small">{i}</li>)}</ul>
        </div>
      )}
      {ch.found && (
        <div className="grid g-main">
          <div className="card">
            <div className="card-title"><Fingerprint size={18} /> Record</div>
            <div className="grid g2" style={{ gap: 14 }}>
              <div><div className="small muted">Title</div><b>{rec?.title || "Private record"}</b></div>
              <div><div className="small muted">Owner</div><b>{rec?.owner || "Hidden by owner"}</b></div>
              <div><div className="small muted">Registered on chain</div><b>{fmtDate(ch.created_at)}</b></div>
              <div><div className="small muted">Versions</div><b>{ch.version_count}</b></div>
              {rec && <div><div className="small muted">Workflow status</div><StatusBadge status={rec.status} /></div>}
              {rec && <div><div className="small muted">Content risk</div><RiskBadge level={rec.risk_level} score={rec.risk_score} /></div>}
              {rec?.size != null && <div><div className="small muted">Size</div><b>{fmtBytes(rec.size)}</b></div>}
              {r.approvals && <div><div className="small muted">Reviews</div><b>{r.approvals.approved}/{r.approvals.requested} approved{r.approvals.rejected ? `, ${r.approvals.rejected} rejected` : ""}</b></div>}
            </div>
            {rec?.description && <p className="small muted" style={{ marginTop: 14 }}>{rec.description}</p>}
            <div className="row" style={{ marginTop: 16 }}>
              {r.certificate_url && <button className="btn sm primary" onClick={cert} disabled={busy}>{busy ? <Spinner /> : <Award size={16} />} Verification certificate (PDF)</button>}
              {user && rec && <Link className="btn sm" to={`/records/${r.public_id}`}>Open record</Link>}
            </div>
          </div>
          <div className="card" style={{ textAlign: "center" }}>
            <div className="card-title" style={{ justifyContent: "center" }}><QrCode size={18} /> Share</div>
            <div className="qr-box" style={{ margin: "0 auto" }}><img src={api.qrUrl(r.public_id)} alt={`QR code for ${r.public_id}`} /></div>
            <div className="small muted" style={{ marginTop: 10 }}>Scan to verify {r.public_id}</div>
            {r.trust && <div style={{ marginTop: 12 }}><span className="badge b-info">Trust score {r.trust.score}{r.trust.label ? ` · ${r.trust.label}` : ""}</span></div>}
          </div>
        </div>
      )}
      {ch.found && (
        <div className="card">
          <div className="card-title"><Boxes size={18} /> On-chain evidence</div>
          <div className="small muted" style={{ marginBottom: 12 }}>
            Read directly from contract <span className="mono">{short(ch.contract_address, 8, 6)}</span> on network <span className="mono">{ch.network}</span>. These values do not come from the platform database.
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Ver.</th><th>SHA-256 fingerprint</th><th>Block time (UTC)</th><th>Reviews</th><th>Tx</th></tr></thead>
              <tbody>
                {ch.versions.map((v) => (
                  <tr key={v.version_no}>
                    <td>v{v.version_no}</td>
                    <td className="mono">{short(v.content_hash, 14, 10)}</td>
                    <td>{fmtDate(v.timestamp)}</td>
                    <td>{v.approvals} ✓ {v.rejections > 0 && <span style={{ color: "var(--bad)" }}>{v.rejections} ✗</span>}</td>
                    <td className="mono">{v.tx_hash ? `${short(v.tx_hash, 8, 6)} · #${v.block_number}` : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {ch.history.length > 0 && (
            <>
              <div className="divider" />
              <div className="small muted" style={{ marginBottom: 10 }}>Event log (from blockchain events)</div>
              <div className="timeline">
                {ch.history.map((e) => (
                  <div key={`${e.tx_hash}-${e.log_index}`} className={`tl-item ${e.event === "RecordRevoked" ? "bad" : e.event === "DecisionRecorded" ? (e.approved ? "good" : "warn") : ""}`}>
                    <div className="row between">
                      <b>{EVENT_LABEL[e.event] || e.event}{e.version_no ? ` · v${e.version_no}` : ""}{e.event === "DecisionRecorded" ? (e.approved ? " · approved" : " · rejected") : ""}</b>
                      <span className="small muted">{fmtDate(e.timestamp)}</span>
                    </div>
                    <div className="small muted mono">block #{e.block_number} · {short(e.tx_hash, 12, 8)}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function LookupResult({ r, fileName }) {
  return (
    <div className="col" style={{ gap: 14 }}>
      <motion.div className={`verdict ${r.registered ? "info" : "warn"}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="vicon"><span className="pulse-ring" /><FileSearch size={42} strokeWidth={1.8} /></div>
        <div className="vbody">
          <div className="small muted" style={{ textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600 }}>{fileName}</div>
          <h2>{r.registered ? "This exact file is registered" : "Never registered"}</h2>
          <p style={{ marginTop: 6 }}>{r.message}</p>
        </div>
      </motion.div>
      <Hash label="SHA-256 fingerprint" value={r.sha256} />
      {r.matches.length > 0 && (
        <div className="card">
          <div className="card-title">Registrations of this fingerprint (earliest first)</div>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Record</th><th>Version</th><th>Registered</th><th>Status</th><th /></tr></thead>
            <tbody>{r.matches.map((m) => (
              <tr key={`${m.public_id}-${m.version_no}`}>
                <td className="mono">{m.public_id}</td><td>v{m.version_no}{m.is_latest ? " (latest)" : ""}</td><td>{fmtDate(m.registered_at)}</td>
                <td><StatusBadge status={m.status} /></td>
                <td><Link className="btn sm" to={`/verify/${m.public_id}`}>Verify</Link></td>
              </tr>))}</tbody>
          </table></div>
        </div>
      )}
    </div>
  );
}

export default function Verify() {
  const { id: routeId } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [tab, setTab] = useState(params.get("tab") === "file" ? "file" : "id");
  const [id, setId] = useState(routeId || "");
  const [file, setFile] = useState(null);
  const [res, setRes] = useState(null);
  const [lookup, setLookup] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [scan, setScan] = useState(false);
  const fileRef = useRef(null);
  fileRef.current = file;

  const run = useCallback(async (pid, f) => {
    setErr(""); setBusy(true); setRes(null);
    try {
      const r = f ? await api.verifyHash(pid, await sha256File(f)) : await api.verify(pid);
      setRes(r);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }, []);

  useEffect(() => { if (routeId) { setId(routeId); setTab("id"); run(routeId, fileRef.current); } }, [routeId, run]);

  const submit = (e) => {
    e.preventDefault();
    const pid = id.trim().toUpperCase();
    if (!pid) return;
    if (pid !== routeId) nav(`/verify/${pid}`); // the route effect runs the check
    else run(pid, file);
  };
  const runFileOnly = async (f) => {
    setFile(f); setLookup(null); setErr(""); setBusy(true);
    try { setLookup(await api.lookupHash(await sha256File(f))); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: "24px 20px 90px", position: "relative", zIndex: 1 }}>
      <PageHead title="Verify authenticity" subtitle="Anyone can check a record. Files are fingerprinted locally in your browser and are never uploaded." />
      <Tabs tabs={[{ id: "id", label: "I have an ID or QR code" }, { id: "file", label: "I only have the file" }]} value={tab} onChange={(t) => { setTab(t); setErr(""); setFile(null); setLookup(null); }} />
      <div className="card" style={{ margin: "16px 0" }}>
        {tab === "id" ? (
          <form className="col" onSubmit={submit}>
            <div className="row" style={{ flexWrap: "nowrap" }}>
              <input className="input" style={{ flex: 1, minWidth: 0 }} placeholder="PP-XXXXXXXXXX" value={id} onChange={(e) => setId(e.target.value)} aria-label="Record ID" spellCheck={false} />
              <button type="button" className="btn icon" onClick={() => setScan(true)} aria-label="Scan QR" title="Scan QR code"><QrCode size={19} /></button>
              <button className="btn primary" disabled={busy}>{busy ? <Spinner /> : <ScanSearch size={17} />} Verify</button>
            </div>
            <div className="small muted">Optionally add the file you received to confirm it is byte-for-byte identical to the registered version:</div>
            <Dropzone file={file} onFile={setFile} hint="Optional. Hashed locally; nothing is uploaded." />
            {file && <button type="button" className="btn sm ghost" style={{ alignSelf: "flex-start" }} onClick={() => setFile(null)}>Remove file</button>}
          </form>
        ) : (
          <div className="col">
            <div className="small muted">Drop any file to find out whether, when and by which record it was first registered.</div>
            <Dropzone file={file} onFile={runFileOnly} hint="Hashed locally; only the fingerprint is sent." />
          </div>
        )}
      </div>
      {err && <div className="card err" role="alert">{err}</div>}
      {busy && !res && <div style={{ display: "grid", placeItems: "center", padding: 40 }}><Spinner /></div>}
      {tab === "id" && res && <Result r={res} fileName={file?.name} />}
      {tab === "file" && lookup && <LookupResult r={lookup} fileName={file?.name} />}
      <QrScanner open={scan} onClose={() => setScan(false)} onResult={(pid) => { setScan(false); setId(pid); nav(`/verify/${pid}`); }} />
    </div>
  );
}
