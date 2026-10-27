import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { BrainCircuit, Fingerprint, Link2, QrCode, ScanSearch, ScrollText, ShieldCheck, Users, FileKey2 } from "lucide-react";
import { api } from "../api";
import QrScanner from "../components/QrScanner";
import { CountUp } from "../components/ui";

const FEATURES = [
  { icon: Fingerprint, title: "Cryptographic fingerprints", text: "Every file is hashed with SHA-256. Only the hash is written to the chain; your document never is." },
  { icon: Link2, title: "Immutable provenance", text: "Ownership, timestamps, version history and approvals are anchored in a Solidity smart contract that anyone can read." },
  { icon: ShieldCheck, title: "Tamper detection", text: "Change one byte and verification fails. Older versions are recognised and flagged as outdated, not forged." },
  { icon: BrainCircuit, title: "Explainable risk engine", text: "Duplicates, near-copies, spoofed file types and suspicious metadata are scored, and every signal tells you why." },
  { icon: Users, title: "Multi-user approvals", text: "Request reviews from supervisors or peers. Each decision is recorded on chain and feeds the trust score." },
  { icon: ScrollText, title: "Tamper-evident audit trail", text: "A hash-chained, searchable log of every action, exportable to CSV, with a one-click integrity check." },
];

export default function Landing() {
  const nav = useNavigate();
  const [id, setId] = useState("");
  const [scan, setScan] = useState(false);
  const [stats, setStats] = useState(null);
  useEffect(() => { api.publicStats().then(setStats).catch(() => {}); }, []);

  const go = (e) => { e.preventDefault(); if (id.trim()) nav(`/verify/${encodeURIComponent(id.trim().toUpperCase())}`); };

  return (
    <>
      <section className="hero">
        <motion.span className="eyebrow" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
          <FileKey2 size={15} /> Blockchain authenticity &amp; provenance
        </motion.span>
        <motion.h1 initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08, duration: 0.6 }}>
          Prove it is <span className="grad">original</span>.<br />Prove it is <span className="grad">unchanged</span>.
        </motion.h1>
        <motion.p className="lead" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.25 }}>
          ProofPulse registers the fingerprint of any document, dataset or project submission on a smart contract, scores its risk with an explainable engine,
          and lets anyone verify it with an ID, a QR code or the file itself.
        </motion.p>

        <motion.form className="card verify-box" onSubmit={go} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}>
          <div style={{ fontWeight: 600, marginBottom: 10 }}>Verify a record, no account needed</div>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input className="input" style={{ flex: 1, minWidth: 0 }} placeholder="PP-XXXXXXXXXX" value={id} onChange={(e) => setId(e.target.value)} aria-label="Record ID" spellCheck={false} />
            <button className="btn primary"><ScanSearch size={17} /> Verify</button>
            <button type="button" className="btn icon" onClick={() => setScan(true)} aria-label="Scan QR code" title="Scan QR code"><QrCode size={19} /></button>
          </div>
          <div className="small muted" style={{ marginTop: 10 }}>Have only the file? <Link to="/verify?tab=file">Look it up by fingerprint</Link>.</div>
        </motion.form>

        {stats && (
          <div className="row" style={{ justifyContent: "center", gap: 36, marginTop: 34 }}>
            {[["Records anchored", stats.records], ["Versions", stats.versions], ["Verifications", stats.verifications], ["Block height", stats.chain?.block_number ?? 0]].map(([l, v]) => (
              <div key={l} style={{ textAlign: "center" }}>
                <div style={{ fontFamily: "var(--font-display)", fontSize: "1.9rem", fontWeight: 700 }}><CountUp value={v} /></div>
                <div className="small muted">{l}</div>
              </div>
            ))}
          </div>
        )}
        <div className="row" style={{ justifyContent: "center", marginTop: 30 }}>
          <Link to="/signup" className="btn primary">Create a free account</Link>
          <Link to="/login" className="btn">Sign in</Link>
        </div>
      </section>

      <section className="feature-grid">
        <div className="grid g3">
          {FEATURES.map((f, i) => (
            <motion.div key={f.title} className="card hover feature" initial={{ opacity: 0, y: 22 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-40px" }} transition={{ delay: (i % 3) * 0.08 }}>
              <div className="fi"><f.icon size={20} /></div>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </motion.div>
          ))}
        </div>
      </section>
      <QrScanner open={scan} onClose={() => setScan(false)} onResult={(pid) => { setScan(false); nav(`/verify/${pid}`); }} />
    </>
  );
}
