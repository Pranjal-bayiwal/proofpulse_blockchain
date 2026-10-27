import { useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { api } from "../api";

/** Search users by name/username and pick reviewers. `value` is a list of {username, full_name}. */
export default function ReviewerPicker({ value, onChange, max = 10 }) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState([]);
  useEffect(() => {
    if (q.trim().length < 2) { setFound([]); return undefined; }
    const t = setTimeout(() => api.searchUsers(q.trim()).then(setFound).catch(() => setFound([])), 220);
    return () => clearTimeout(t);
  }, [q]);
  const picked = new Set(value.map((v) => v.username));
  const add = (u) => { if (!picked.has(u.username) && value.length < max) onChange([...value, u]); setQ(""); setFound([]); };

  return (
    <div className="col" style={{ gap: 8 }}>
      <div style={{ position: "relative" }}>
        <Search size={16} style={{ position: "absolute", left: 12, top: 13, color: "var(--muted)" }} />
        <input className="input" style={{ paddingLeft: 36 }} placeholder="Search people by name or username" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search reviewers" />
        {found.length > 0 && (
          <div className="dropdown" style={{ left: 0, right: 0, width: "auto", top: "calc(100% + 6px)" }}>
            {found.filter((u) => !picked.has(u.username)).map((u) => (
              <div key={u.id} className="notif" role="button" tabIndex={0} onClick={() => add(u)} onKeyDown={(e) => e.key === "Enter" && add(u)}>
                <div><b className="small">{u.full_name}</b> <span className="small muted">@{u.username}</span></div>
              </div>
            ))}
          </div>
        )}
      </div>
      {value.length > 0 && (
        <div className="row" style={{ gap: 6 }}>
          {value.map((u) => (
            <span key={u.username} className="badge b-info" style={{ paddingRight: 6 }}>
              {u.full_name}
              <button type="button" className="copy" style={{ padding: 2 }} onClick={() => onChange(value.filter((v) => v.username !== u.username))} aria-label={`Remove ${u.full_name}`}><X size={12} /></button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
