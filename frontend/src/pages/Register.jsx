import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Award, Check, Lock, PartyPopper, ShieldCheck } from "lucide-react";
import { api, download } from "../api";
import { useToast } from "../context";
import { RiskReport } from "../components/Analysis";
import ReviewerPicker from "../components/ReviewerPicker";
import { Dropzone, Hash, PageHead, RiskBadge, Spinner, StatusBadge, fmtBytes } from "../components/ui";

const CATEGORIES = [["document", "Document"], ["research", "Research paper"], ["dataset", "Dataset"], ["project", "Project submission"], ["code", "Source code"], ["media", "Media"], ["other", "Other"]];

export default function Register() {
  const nav = useNavigate();
  const toast = useToast();
  const [step, setStep] = useState(1);
  const [file, setFile] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [analysing, setAnalysing] = useState(false);
  const [err, setErr] = useState("");
  const [f, setF] = useState({ title: "", description: "", category: "document", tags: "", visibility: "private", store: true });
  const [reviewers, setReviewers] = useState([]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const seq = useRef(0);

  useEffect(() => {
    if (!file) return;
    const my = ++seq.current;
    setAnalysis(null); setErr(""); setAnalysing(true);
    setF((s) => ({ ...s, title: s.title || file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ") }));
    api.analyze(file).then((a) => { if (my === seq.current) setAnalysis(a); }).catch((e) => { if (my === seq.current) setErr(e.message); }).finally(() => { if (my === seq.current) setAnalysing(false); });
  }, [file]);

  const submit = async () => {
    setBusy(true); setErr("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("title", f.title); form.append("description", f.description); form.append("category", f.category);
      form.append("tags", f.tags); form.append("visibility", f.visibility); form.append("store_file", f.store ? "true" : "false");
      let rec = await api.createRecord(form);
      let reviewError = "";
      if (reviewers.length) {
        try { rec = (await api.requestApprovals(rec.public_id, reviewers.map((r) => r.username))).record; } catch (e) { reviewError = e.message; }
      }
      setDone({ rec, reviewError });
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  if (done) {
    const r = done.rec;
    return (
      <motion.div className="card" style={{ maxWidth: 760, margin: "0 auto" }} initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }}>
        <div className="row" style={{ gap: 14 }}>
          <div className="vicon" style={{ width: 60, height: 60, borderRadius: 20, display: "grid", placeItems: "center", background: "color-mix(in srgb, var(--good) 15%, transparent)", color: "var(--good)" }}><PartyPopper size={30} /></div>
          <div><h2>Anchored on the blockchain</h2><div className="muted small">Block #{r.block_number} · {r.title}</div></div>
        </div>
        <div className="grid g2" style={{ marginTop: 20, alignItems: "start" }}>
          <div className="col">
            <Hash label="Record ID (share this)" value={r.public_id} />
            <Hash label="File fingerprint (SHA-256)" value={r.sha256} compact />
            <Hash label="Transaction hash" value={r.tx_hash} compact />
            <div className="row"><StatusBadge status={r.status} /><RiskBadge level={r.risk_level} score={r.risk_score} /></div>
            {done.reviewError && <div className="err">Registered, but reviewers could not be requested: {done.reviewError}</div>}
          </div>
          <div style={{ textAlign: "center" }}>
            <div className="qr-box" style={{ margin: "0 auto" }}><img src={api.qrUrl(r.public_id)} alt={`QR code for ${r.public_id}`} /></div>
            <div className="small muted" style={{ marginTop: 8 }}>Anyone can scan this to verify the record.</div>
          </div>
        </div>
        <div className="row" style={{ marginTop: 22 }}>
          <Link className="btn primary" to={`/records/${r.public_id}`}>Open record</Link>
          <button className="btn" onClick={() => download(`/api/records/${r.public_id}/certificate`, `ProofPulse-${r.public_id}.pdf`).catch((e) => toast({ title: "Download failed", body: e.message, kind: "danger" }))}><Award size={16} /> Download certificate</button>
          <Link className="btn ghost" to={`/verify/${r.public_id}`}><ShieldCheck size={16} /> Public verification page</Link>
          <button className="btn ghost" onClick={() => { setDone(null); setFile(null); setAnalysis(null); setStep(1); setReviewers([]); setF({ title: "", description: "", category: "document", tags: "", visibility: "private", store: true }); }}>Register another</button>
        </div>
      </motion.div>
    );
  }

  const steps = ["Choose file", "Describe", "Reviewers & confirm"];
  const canNext1 = file && analysis && !analysing;
  const canNext2 = f.title.trim().length >= 2;

  return (
    <>
      <PageHead title="Register a file" subtitle="The fingerprint is anchored on chain. The file itself never touches the blockchain." />
      <div className="steps">
        {steps.map((s, i) => <div key={s} className={`step ${step === i + 1 ? "cur" : step > i + 1 ? "done" : ""}`}><i>{step > i + 1 ? <Check size={14} /> : i + 1}</i>{s}</div>)}
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={step} initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -18 }} transition={{ duration: 0.2 }}>
          {step === 1 && (
            <div className="grid g-main" style={{ alignItems: "start" }}>
              <div className="col">
                <Dropzone file={file} onFile={setFile} />
                {analysing && <div className="card row"><Spinner /> Fingerprinting and running the risk engine…</div>}
                {err && <div className="card err">{err}</div>}
                {analysis && <div className="card"><Hash label={`SHA-256 · ${fmtBytes(analysis.size)}`} value={analysis.sha256} /></div>}
              </div>
              <div className="card">
                <div className="card-title">Pre-registration risk check</div>
                {analysis ? <RiskReport report={analysis.risk} compact /> : <div className="small muted">Select a file to see duplicate, similarity and integrity warnings before anything is written to the chain.</div>}
              </div>
            </div>
          )}
          {step === 2 && (
            <div className="card col" style={{ maxWidth: 760 }}>
              <label className="field">Title<input className="input" value={f.title} maxLength={200} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
              <label className="field">Description <span className="hint">(optional)</span><textarea className="input" rows={3} maxLength={2000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
              <div className="grid g2">
                <label className="field">Category<select className="input" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
                <label className="field">Tags <span className="hint">(comma separated)</span><input className="input" value={f.tags} onChange={(e) => setF({ ...f, tags: e.target.value })} placeholder="thesis, iot, 2026" /></label>
              </div>
              <label className="field">Visibility
                <select className="input" value={f.visibility} onChange={(e) => setF({ ...f, visibility: e.target.value })}>
                  <option value="private">Private: verification shows status only, no title or owner</option>
                  <option value="public">Public: verification also shows title, owner and description</option>
                </select>
              </label>
              <label className="check"><input type="checkbox" checked={f.store} onChange={(e) => setF({ ...f, store: e.target.checked })} />
                <span><b><Lock size={13} style={{ verticalAlign: -1 }} /> Keep an encrypted copy on the server</b><div className="hint">Enables server-side integrity scans and tamper forensics. The copy is AES-encrypted at rest. Untick to store the fingerprint only; you then keep the only copy.</div></span>
              </label>
            </div>
          )}
          {step === 3 && (
            <div className="grid g2" style={{ alignItems: "start" }}>
              <div className="card col">
                <div className="card-title">Request approvals <span className="muted small">(optional)</span></div>
                <div className="small muted">Reviewers are notified, approve or reject on chain, and their decisions raise (or lower) the trust score.</div>
                <ReviewerPicker value={reviewers} onChange={setReviewers} />
              </div>
              <div className="card col">
                <div className="card-title">Summary</div>
                <div className="small"><b>{f.title}</b><div className="muted">{file?.name} · {fmtBytes(file?.size)} · {f.category} · {f.visibility}</div></div>
                {analysis && <div className="row"><RiskBadge level={analysis.risk.level} score={analysis.risk.score} />{analysis.risk.signals.length > 0 && <span className="small muted">{analysis.risk.signals.length} signal(s) flagged</span>}</div>}
                <div className="small muted">{f.store ? "An encrypted copy will be kept." : "Fingerprint only; no copy kept."} {reviewers.length ? `${reviewers.length} reviewer(s) will be asked.` : "No reviewers requested."}</div>
                {err && <div className="err" role="alert">{err}</div>}
                <button className="btn primary block" onClick={submit} disabled={busy}>{busy ? <><Spinner /> Waiting for block confirmation…</> : <><ShieldCheck size={17} /> Register on blockchain</>}</button>
              </div>
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      <div className="row between" style={{ marginTop: 20 }}>
        <button className="btn" onClick={() => { setErr(""); setStep((s) => s - 1); }} disabled={step === 1 || busy}><ArrowLeft size={16} /> Back</button>
        {step < 3 && <button className="btn primary" onClick={() => setStep((s) => s + 1)} disabled={step === 1 ? !canNext1 : !canNext2}>Continue <ArrowRight size={16} /></button>}
      </div>
    </>
  );
}
