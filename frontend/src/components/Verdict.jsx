import { motion } from "framer-motion";
import { AlertOctagon, BadgeCheck, Ban, Database, FileClock, HelpCircle, ShieldAlert, ShieldCheck } from "lucide-react";

export const VERDICTS = {
  AUTHENTIC: { cls: "good", icon: BadgeCheck },
  REGISTERED: { cls: "info", icon: ShieldCheck },
  ON_CHAIN_ONLY: { cls: "info", icon: Database },
  OUTDATED_VERSION: { cls: "warn", icon: FileClock },
  TAMPERED: { cls: "bad", icon: AlertOctagon },
  ANCHOR_MISMATCH: { cls: "bad", icon: ShieldAlert },
  REVOKED: { cls: "bad", icon: Ban },
  NOT_FOUND: { cls: "warn", icon: HelpCircle },
};

export default function Verdict({ result, fileName }) {
  const v = VERDICTS[result.verdict] || VERDICTS.NOT_FOUND;
  const Icon = v.icon;
  return (
    <motion.div className={`verdict ${v.cls}`} initial={{ opacity: 0, scale: 0.97, y: 12 }} animate={{ opacity: 1, scale: 1, y: 0 }} transition={{ type: "spring", stiffness: 160, damping: 18 }} role="status">
      <div className="vicon">
        <span className="pulse-ring" />
        <motion.div initial={{ scale: 0.4, rotate: -20, opacity: 0 }} animate={{ scale: 1, rotate: 0, opacity: 1 }} transition={{ delay: 0.15, type: "spring", stiffness: 220, damping: 14 }}>
          <Icon size={44} strokeWidth={1.8} />
        </motion.div>
      </div>
      <div className="vbody">
        <div className="small muted" style={{ textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600 }}>{result.public_id}{fileName ? ` · ${fileName}` : ""}</div>
        <h2>{result.headline}</h2>
        <p style={{ marginTop: 6, maxWidth: 640 }}>{result.message}</p>
        {result.warning && <p style={{ marginTop: 6, color: "var(--warn)", fontWeight: 600 }}>{result.warning}</p>}
      </div>
    </motion.div>
  );
}
