import { Fragment, useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Hash as HashIcon, Link2, ScrollText, Search, ShieldCheck, ShieldX } from "lucide-react";
import { api, download } from "../api";
import { useAuth, useLive, useToast } from "../context";
import { Empty, PageHead, Skeleton, Spinner, fmtDate, short } from "../components/ui";

const tone = (a) => (/REVOKED|REJECTED|LOCKED|FAIL|TAMPER/.test(a) ? "b-bad" : /APPROVED|REGISTERED|VERSION|ANCHOR/.test(a) ? "b-good" : /REQUEST|CERTIFICATE|INTEGRITY/.test(a) ? "b-info" : "b-mute");

export default function Audit() {
  const { user } = useAuth();
  const toast = useToast();
  const [f, setF] = useState({ q: "", action: "", actor: "", record: "", date_from: "", date_to: "" });
  const [applied, setApplied] = useState(f);
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [actions, setActions] = useState([]);
  const [chain, setChain] = useState(null);
  const [busy, setBusy] = useState("");
  const [open, setOpen] = useState(null);

  const load = useCallback(() => api.audit({ ...applied, page, page_size: 20 }).then(setData).catch((e) => toast({ title: "Could not load audit trail", body: e.message, kind: "danger" })), [applied, page, toast]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.auditActions().then(setActions).catch(() => {}); }, []);
  useLive(["stats", "approvals"], load);

  const search = (e) => { e.preventDefault(); setPage(1); setApplied(f); };
  const verifyChain = async () => { setBusy("chain"); try { setChain(await api.auditChain()); } catch (e) { toast({ title: "Check failed", body: e.message, kind: "danger" }); } finally { setBusy(""); } };
  const exportCsv = async () => {
    setBusy("csv");
    const p = new URLSearchParams(Object.entries(applied).filter(([, v]) => v)).toString();
    try { await download(`/api/audit/export.csv${p ? `?${p}` : ""}`, "proofpulse-audit.csv"); } catch (e) { toast({ title: "Export failed", body: e.message, kind: "danger" }); } finally { setBusy(""); }
  };
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <PageHead title="Audit trail" subtitle={user.role === "admin" ? "Every action on the platform, hash-chained so edits or deletions are detectable." : "Actions you performed and everything that happened to your records."}>
        <button className="btn" onClick={verifyChain} disabled={busy === "chain"}>{busy === "chain" ? <Spinner /> : <ShieldCheck size={16} />} Verify log integrity</button>
        <button className="btn" onClick={exportCsv} disabled={busy === "csv"}><Download size={16} /> Export CSV</button>
      </PageHead>

      {chain && (
        <div className="card" style={{ marginBottom: 16, borderColor: chain.valid ? "color-mix(in srgb, var(--good) 45%, transparent)" : "color-mix(in srgb, var(--bad) 55%, transparent)" }}>
          <div className="row" style={{ gap: 12 }}>
            {chain.valid ? <ShieldCheck size={26} color="var(--good)" /> : <ShieldX size={26} color="var(--bad)" />}
            <div>
              <b>{chain.valid ? "Audit log is intact" : "Audit log has been tampered with"}</b>
              <div className="small muted">{chain.message}</div>
              {chain.head && <div className="small muted mono">head {short(chain.head, 14, 10)}</div>}
            </div>
          </div>
        </div>
      )}

      <form className="card flat grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", marginBottom: 16, alignItems: "end" }} onSubmit={search}>
        <label className="field" style={{ gridColumn: "span 2" }}>Search<div style={{ position: "relative" }}><Search size={16} style={{ position: "absolute", left: 12, top: 13, color: "var(--muted)" }} /><input className="input" style={{ paddingLeft: 36 }} placeholder="action, user, record, tx hash, details" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} /></div></label>
        <label className="field">Action<select className="input" value={f.action} onChange={(e) => setF({ ...f, action: e.target.value })}><option value="">All actions</option>{actions.map((a) => <option key={a} value={a}>{a.replaceAll("_", " ").toLowerCase()}</option>)}</select></label>
        <label className="field">Record ID<input className="input" placeholder="PP-…" value={f.record} onChange={(e) => setF({ ...f, record: e.target.value })} /></label>
        {user.role === "admin" && <label className="field">User<input className="input" placeholder="username" value={f.actor} onChange={(e) => setF({ ...f, actor: e.target.value })} /></label>}
        <label className="field">From<input className="input" type="date" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value })} /></label>
        <label className="field">To<input className="input" type="date" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value })} /></label>
        <div className="row"><button className="btn primary">Apply</button><button type="button" className="btn ghost" onClick={() => { const z = { q: "", action: "", actor: "", record: "", date_from: "", date_to: "" }; setF(z); setApplied(z); setPage(1); }}>Reset</button></div>
      </form>

      {!data && <Skeleton h={300} />}
      {data && data.items.length === 0 && <Empty icon={ScrollText} title="No matching entries" />}
      {data && data.items.length > 0 && (
        <div className="card" style={{ padding: 8 }}>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>#</th><th>Time</th><th>User</th><th>Action</th><th>Record</th><th>Tx</th><th /></tr></thead>
              <tbody>
                {data.items.map((e) => (
                  <Fragment key={e.seq}>
                    <tr className="click" onClick={() => setOpen(open === e.seq ? null : e.seq)}>
                      <td className="mono muted">{e.seq}</td>
                      <td className="small" style={{ whiteSpace: "nowrap" }}>{fmtDate(e.ts)}</td>
                      <td>{e.actor}</td>
                      <td><span className={`badge ${tone(e.action)}`}>{e.action.replaceAll("_", " ").toLowerCase()}</span></td>
                      <td className="mono small">{e.record || "-"}</td>
                      <td className="mono small">{e.tx_hash ? short(e.tx_hash, 8, 4) : "-"}</td>
                      <td><Link2 size={14} className="muted" /></td>
                    </tr>
                    {open === e.seq && (
                      <tr><td colSpan={7} style={{ background: "var(--surface)" }}>
                        <div className="grid g2" style={{ gap: 12 }}>
                          <div><div className="small muted">Details</div><pre className="mono small" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0 }}>{JSON.stringify(e.details, null, 2)}</pre></div>
                          <div className="stack-sm small">
                            <div><HashIcon size={12} /> entry hash <span className="mono">{short(e.entry_hash, 16, 12)}</span></div>
                            <div><HashIcon size={12} /> previous hash <span className="mono">{short(e.prev_hash, 16, 12)}</span></div>
                            {e.ip && <div>from <span className="mono">{e.ip}</span></div>}
                            {e.tx_hash && <div>tx <span className="mono">{e.tx_hash}</span></div>}
                          </div>
                        </div>
                      </td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {data && pages > 1 && (
        <div className="row" style={{ justifyContent: "center", marginTop: 18 }}>
          <button className="btn sm" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft size={16} /> Prev</button>
          <span className="small muted">Page {page} of {pages} · {data.total} entries</span>
          <button className="btn sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next <ChevronRight size={16} /></button>
        </div>
      )}
    </>
  );
}
