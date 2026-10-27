import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Info, Copy as CopyIcon } from "lucide-react";
import { Ring, fmtDate } from "./ui";

const SEV_LABEL = { high: "High", medium: "Medium", low: "Low", info: "Note" };
const KIND_LABEL = {
  exact: "Identical file", same_text: "Same text, different file", near: "Near-duplicate", partial: "Partial overlap",
};

export function SimilarList({ matches }) {
  if (!matches?.length) return null;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr><th>Registered record</th><th>Relationship</th><th>Similarity</th><th>Registered</th></tr></thead>
        <tbody>
          {matches.map((m) => (
            <tr key={`${m.public_id}-${m.version_no}`}>
              <td><Link className="mono" to={`/verify/${m.public_id}`}>{m.public_id}</Link> v{m.version_no}{m.own ? <span className="badge b-mute" style={{ marginLeft: 8 }}>yours</span> : null}{m.revoked ? <span className="badge b-bad" style={{ marginLeft: 8 }}>revoked</span> : null}</td>
              <td>{KIND_LABEL[m.kind] || m.kind}</td>
              <td style={{ minWidth: 130 }}>
                <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
                  <div className={`bar ${m.similarity >= 0.8 ? "bad" : m.similarity >= 0.5 ? "warn" : "good"}`} style={{ flex: 1 }}><i style={{ width: `${Math.round(m.similarity * 100)}%` }} /></div>
                  <b>{Math.round(m.similarity * 100)}%</b>
                </div>
              </td>
              <td className="small muted">{fmtDate(m.registered_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Explainable risk analysis: score, every signal with its reason and weight, and similar records. */
export function RiskReport({ report, compact }) {
  if (!report || report.score == null) return <div className="muted small">No analysis stored for this version.</div>;
  const Icon = report.level === "LOW" ? CheckCircle2 : AlertTriangle;
  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="row" style={{ gap: 22, alignItems: "center" }}>
        <Ring value={report.score} invert size={compact ? 96 : 118} label="/100" />
        <div style={{ flex: 1, minWidth: 220 }}>
          <div className="row" style={{ gap: 8 }}>
            <Icon size={19} color={report.level === "LOW" ? "var(--good)" : report.level === "MEDIUM" ? "var(--warn)" : "var(--bad)"} />
            <b style={{ fontSize: "1.05rem" }}>{report.summary}</b>
          </div>
          <p className="small muted" style={{ marginTop: 6 }}>{report.recommendation}</p>
        </div>
      </div>

      {report.signals.length === 0 && (
        <div className="signal info"><h4><CheckCircle2 size={16} /> No risk signals</h4><div className="why">Checked duplicates, similarity, file-type consistency, hidden content, metadata and registration behaviour.</div></div>
      )}
      {report.signals.map((s, i) => (
        <motion.div key={s.id} className={`signal ${s.severity}`} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
          <h4>
            <span className={`badge ${s.severity === "high" ? "b-bad" : s.severity === "medium" ? "b-warn" : s.severity === "low" ? "b-info" : "b-mute"}`}>{SEV_LABEL[s.severity]}</span>
            {s.title}
            <span className="small muted" style={{ marginLeft: "auto", fontWeight: 500 }}>weight {Math.round(s.weight * 100)}%</span>
          </h4>
          <div style={{ marginTop: 6, fontSize: "0.88rem" }}>{s.detail}</div>
          <div className="why"><Info size={12} style={{ verticalAlign: -1 }} /> Why it matters: {s.why}</div>
        </motion.div>
      ))}

      {report.matches?.length > 0 && (
        <div>
          <div className="card-title"><CopyIcon size={17} /> Similar registered content</div>
          <SimilarList matches={report.matches} />
        </div>
      )}
      <div className="small muted">
        Method: {report.method}.{" "}
        {report.inspected && <>Inspected: type <b>{report.inspected.detected_type || "unknown"}</b> (extension {report.inspected.extension || "none"}), entropy {report.inspected.entropy}, {report.inspected.text_extracted ? `${report.inspected.text_characters.toLocaleString()} characters of text compared` : "no extractable text, byte-level checks only"}.</>}
      </div>
    </div>
  );
}

export function TrustPanel({ trust }) {
  if (!trust?.components) return null;
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="row" style={{ gap: 22 }}>
        <Ring value={trust.score} size={118} label={trust.label} />
        <div className="small muted" style={{ flex: 1, minWidth: 200 }}>
          The trust score is the sum of six transparent components. Nothing is hidden or learned, so it can be reproduced by hand.
          {trust.note && <div style={{ marginTop: 6 }}>{trust.note}</div>}
        </div>
      </div>
      {trust.components.map((c) => {
        const pct = (c.points / c.max) * 100;
        return (
          <div key={c.key}>
            <div className="row between" style={{ marginBottom: 5 }}><b className="small">{c.label}</b><span className="small"><b>{c.points}</b> / {c.max}</span></div>
            <div className={`bar ${pct >= 70 ? "good" : pct >= 40 ? "warn" : "bad"}`}><i style={{ width: `${pct}%` }} /></div>
            <div className="small muted" style={{ marginTop: 4 }}>{c.why}</div>
          </div>
        );
      })}
    </div>
  );
}
