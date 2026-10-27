import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, FilePlus2, FolderOpen, Search, SlidersHorizontal } from "lucide-react";
import { api } from "../api";
import { useAuth, useLive } from "../context";
import { Empty, PageHead, RiskBadge, Ring, Skeleton, StatusBadge, Tabs, Visibility, timeAgo } from "../components/ui";

const CATEGORIES = ["document", "dataset", "research", "project", "code", "media", "other"];
const STATUSES = ["REGISTERED", "PENDING_APPROVAL", "APPROVED", "REJECTED", "REVOKED"];

export default function Records() {
  const { user } = useAuth();
  const [sp, setSp] = useSearchParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState(sp.get("q") || "");
  const f = { scope: sp.get("scope") || "mine", q: sp.get("q") || "", status: sp.get("status") || "", category: sp.get("category") || "", risk: sp.get("risk") || "", sort: sp.get("sort") || "new", page: Number(sp.get("page") || 1) };

  const set = (patch) => {
    const next = { ...f, page: 1, ...patch };
    const p = {};
    Object.entries(next).forEach(([k, v]) => { if (v && !(k === "scope" && v === "mine") && !(k === "sort" && v === "new") && !(k === "page" && v === 1)) p[k] = v; });
    setSp(p);
  };
  useEffect(() => setQ(sp.get("q") || ""), [sp]);

  const load = useCallback(() => {
    api.records({ ...f, page_size: 12 }).then((r) => { setData(r); setErr(""); }).catch((e) => setErr(e.message));
  }, [f.scope, f.q, f.status, f.category, f.risk, f.sort, f.page]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setData(null); load(); }, [load]);
  useLive(["stats", "approvals"], load);

  const tabs = [{ id: "mine", label: "My records" }, { id: "reviewing", label: "Reviewing" }, { id: "public", label: "Public" }];
  if (user.role === "admin") tabs.push({ id: "all", label: "All (admin)" });
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <PageHead title="Records" subtitle="Everything registered on ProofPulse that you own, review or can see publicly.">
        <Link to="/register" className="btn primary"><FilePlus2 size={17} /> Register a file</Link>
      </PageHead>
      <Tabs tabs={tabs} value={f.scope} onChange={(scope) => set({ scope })} />

      <form className="card flat row" style={{ margin: "16px 0", gap: 10 }} onSubmit={(e) => { e.preventDefault(); set({ q: q.trim() }); }}>
        <div style={{ position: "relative", flex: "1 1 240px" }}>
          <Search size={16} style={{ position: "absolute", left: 12, top: 13, color: "var(--muted)" }} />
          <input className="input" style={{ paddingLeft: 36 }} placeholder="Search title, description or ID" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" />
        </div>
        <SlidersHorizontal size={17} className="muted hide-sm" />
        <select className="input" style={{ width: "auto" }} value={f.status} onChange={(e) => set({ status: e.target.value })} aria-label="Status">
          <option value="">Any status</option>{STATUSES.map((s) => <option key={s} value={s}>{s.replace("_", " ").toLowerCase()}</option>)}
        </select>
        <select className="input" style={{ width: "auto" }} value={f.category} onChange={(e) => set({ category: e.target.value })} aria-label="Category">
          <option value="">Any category</option>{CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className="input" style={{ width: "auto" }} value={f.risk} onChange={(e) => set({ risk: e.target.value })} aria-label="Risk">
          <option value="">Any risk</option><option value="LOW">Low risk</option><option value="MEDIUM">Medium risk</option><option value="HIGH">High risk</option>
        </select>
        <select className="input" style={{ width: "auto" }} value={f.sort} onChange={(e) => set({ sort: e.target.value })} aria-label="Sort">
          <option value="new">Newest first</option><option value="old">Oldest first</option><option value="trust">Highest trust</option><option value="risk">Lowest trust</option>
        </select>
        <button className="btn">Search</button>
      </form>

      {err && <div className="card err">{err}</div>}
      {!data && !err && <div className="grid g3"><Skeleton h={170} /><Skeleton h={170} /><Skeleton h={170} /></div>}
      {data && data.items.length === 0 && <Empty icon={FolderOpen} title="No records match">Try clearing the filters, or register a new file.</Empty>}
      {data && data.items.length > 0 && (
        <div className="grid g3">
          {data.items.map((r, i) => (
            <motion.div key={r.public_id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.04 }}>
              <Link to={`/records/${r.public_id}`} className="card hover" style={{ display: "block", textDecoration: "none", color: "inherit", height: "100%" }}>
                <div className="row between" style={{ alignItems: "flex-start", flexWrap: "nowrap", gap: 12 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: "1.02rem", overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>{r.title || "Private record"}</div>
                    <div className="small muted mono" style={{ marginTop: 3 }}>{r.public_id}</div>
                  </div>
                  <Ring value={r.trust_score} size={54} stroke={6} />
                </div>
                <div className="row" style={{ marginTop: 12, gap: 6 }}>
                  <StatusBadge status={r.status} /><RiskBadge level={r.risk_level} /><Visibility v={r.visibility} />
                </div>
                <div className="small muted" style={{ marginTop: 12 }}>
                  {r.category} · v{r.current_version} · {timeAgo(r.created_at)}{r.owner && !r.is_owner ? ` · by ${r.owner.full_name}` : ""}
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      )}
      {data && pages > 1 && (
        <div className="row" style={{ justifyContent: "center", marginTop: 20 }}>
          <button className="btn sm" disabled={f.page <= 1} onClick={() => setSp({ ...Object.fromEntries(sp), page: String(f.page - 1) })}><ChevronLeft size={16} /> Prev</button>
          <span className="small muted">Page {f.page} of {pages} · {data.total} records</span>
          <button className="btn sm" disabled={f.page >= pages} onClick={() => setSp({ ...Object.fromEntries(sp), page: String(f.page + 1) })}>Next <ChevronRight size={16} /></button>
        </div>
      )}
    </>
  );
}
