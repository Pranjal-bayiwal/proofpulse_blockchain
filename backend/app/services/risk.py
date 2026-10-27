"""Explainable risk analysis.

Every signal states what was found, why it matters and how much it contributes. The overall
score is a noisy-OR of the signal weights:  score = 1 - Π(1 - wᵢ). That makes it monotonic,
bounded to 0-100 and easy to explain in a viva: independent weak signals add up, one strong
signal dominates.
"""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Record, RecordVersion
from ..utils import iso, utcnow
from . import similarity as sim
from .analysis import EXT_FAMILY, IMAGE_EXT, MACRO_EXT, RISKY_EXT, TEXT_EXT, Inspection

settings = get_settings()

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3}


def _sev(w: float) -> str:
    if w >= 0.55:
        return "high"
    if w >= 0.25:
        return "medium"
    if w >= 0.08:
        return "low"
    return "info"


def _signal(sid: str, title: str, weight: float, detail: str, why: str, evidence=None) -> dict:
    weight = round(max(0.0, min(0.95, weight)), 3)
    return {"id": sid, "title": title, "severity": _sev(weight), "weight": weight, "detail": detail, "why": why, "evidence": evidence or {}}


def analyse(
    db: Session,
    *,
    filename: str,
    data: bytes,
    sha256: str,
    ins: Inspection,
    user_id: int,
    text_hash: str | None,
    minhash: list[int] | None,
    dhash: str | None,
    exclude_record_id: int | None = None,
) -> dict:
    signals: list[dict] = []
    matches: list[dict] = []

    # ── 1. duplicate / near-duplicate detection against the registry ──
    rows = db.execute(
        select(RecordVersion, Record).join(Record, Record.id == RecordVersion.record_id)
    ).all()
    for ver, rec in rows:
        own = rec.owner_id == user_id
        same_record = exclude_record_id is not None and rec.id == exclude_record_id
        kind, similarity = None, 0.0
        if ver.sha256 == sha256:
            kind, similarity = "exact", 1.0
        elif text_hash and ver.text_hash == text_hash:
            kind, similarity = "same_text", 1.0
        else:
            s = sim.jaccard(minhash, ver.minhash)
            if dhash and ver.dhash:
                s = max(s, sim.dhash_similarity(dhash, ver.dhash))
            if s >= settings.partial_overlap_threshold:
                kind, similarity = ("near" if s >= settings.near_duplicate_threshold else "partial"), s
        if kind:
            matches.append(
                {
                    "kind": kind,
                    "similarity": round(similarity, 3),
                    "public_id": rec.public_id,
                    "version_no": ver.version_no,
                    "registered_at": iso(ver.created_at),
                    "own": own,
                    "same_record": same_record,
                    "revoked": rec.status == "REVOKED",
                }
            )
    matches.sort(key=lambda m: (-m["similarity"], m["registered_at"] or ""))

    def pick(kinds, own: bool | None):
        return [m for m in matches if m["kind"] in kinds and not m["same_record"] and (own is None or m["own"] == own)]

    exact_other = pick({"exact"}, False)
    if exact_other:
        first = min(exact_other, key=lambda m: m["registered_at"] or "")
        signals.append(_signal(
            "exact_duplicate_other", "Identical file already registered by another account", 0.70,
            f"A byte-identical file is already registered as {first['public_id']} on {first['registered_at']}.",
            "Only the earliest registrant can claim priority. This submission may be a copy.",
            {"matches": exact_other[:5]},
        ))
    same_text_other = pick({"same_text"}, False)
    if same_text_other:
        first = same_text_other[0]
        signals.append(_signal(
            "same_text_other", "Same textual content as another account's record", 0.55,
            f"The extracted text is identical to {first['public_id']} even though the file bytes differ (re-saved or re-formatted copy).",
            "Re-saving a document in another format changes its hash but not its words.",
            {"matches": same_text_other[:5]},
        ))
    near_other = pick({"near"}, False)
    if near_other:
        top = near_other[0]
        w = 0.35 + 0.4 * (top["similarity"] - settings.near_duplicate_threshold) / max(1e-6, 1 - settings.near_duplicate_threshold)
        signals.append(_signal(
            "near_duplicate_other", f"{round(top['similarity'] * 100)}% similar to another account's record", w,
            f"Content closely resembles {top['public_id']} (registered {top['registered_at']}).",
            "High similarity with someone else's earlier work is a common sign of copying with minor edits.",
            {"matches": near_other[:5]},
        ))
    partial_other = pick({"partial"}, False)
    if partial_other and not near_other:
        top = partial_other[0]
        signals.append(_signal(
            "partial_overlap_other", f"{round(top['similarity'] * 100)}% overlap with another account's record", 0.15,
            f"Substantial shared content with {top['public_id']}.",
            "Partial overlap can be legitimate (shared template, citations) but deserves a look.",
            {"matches": partial_other[:5]},
        ))
    exact_self = pick({"exact", "same_text"}, True)
    if exact_self:
        signals.append(_signal(
            "duplicate_self", "You already registered this content", 0.08,
            f"Identical content exists in your record {exact_self[0]['public_id']}.",
            "Consider adding a new version to the existing record instead of creating a new one.",
            {"matches": exact_self[:5]},
        ))
    near_self = pick({"near", "partial"}, True)
    if near_self and not exact_self:
        signals.append(_signal(
            "near_duplicate_self", f"{round(near_self[0]['similarity'] * 100)}% similar to your own record", 0.05,
            f"Looks like an edited copy of your record {near_self[0]['public_id']}.",
            "Probably a revision - a new version keeps the history in one place.",
            {"matches": near_self[:5]},
        ))

    # ── 2. file-type integrity ──
    fam = EXT_FAMILY.get(ins.ext)
    if fam and ins.sniffed and ins.sniffed not in fam:
        signals.append(_signal(
            "type_mismatch", "File extension does not match its real format", 0.30,
            f"Named '{ins.ext}' but the content looks like a '{ins.sniffed}' file.",
            "Disguised file types are used to smuggle executables or hide forged documents.",
            {"extension": ins.ext, "detected": ins.sniffed},
        ))
    elif fam and not ins.sniffed and ins.ext in {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".docx", ".xlsx", ".pptx"}:
        signals.append(_signal(
            "type_mismatch", "File extension does not match its real format", 0.30,
            f"Named '{ins.ext}' but no matching file signature was found.",
            "Corrupted or fabricated files often lack the structure their extension promises.",
            {"extension": ins.ext},
        ))
    if ins.ext in RISKY_EXT or ins.sniffed in {"exe", "elf"}:
        signals.append(_signal(
            "executable", "Executable or script content", 0.25,
            "The file can run code on a recipient's machine.",
            "Registering executables is allowed, but certificates for them should be treated with care.",
        ))
    if ins.has_macros or ins.ext in MACRO_EXT:
        signals.append(_signal(
            "macros", "Document contains macros", 0.30,
            "A VBA macro project was found inside the file.",
            "Macros can alter content after it is opened, so the visible text may not be what was registered.",
        ))

    # ── 3. content anomalies ──
    if ins.hidden_chars:
        signals.append(_signal(
            "hidden_characters", "Invisible Unicode characters", 0.10 + 0.02 * min(ins.hidden_chars, 12),
            f"{ins.hidden_chars} zero-width / bidirectional control characters found in the text.",
            "These characters can hide edits or make text look identical while hashing differently.",
            {"count": ins.hidden_chars},
        ))
    if ins.ext in TEXT_EXT and ins.entropy > 7.2 and len(data) > 512:
        signals.append(_signal(
            "high_entropy_text", "Text file looks encrypted or compressed", 0.25,
            f"Byte entropy is {ins.entropy:.2f} bits/byte; ordinary text is usually below 5.5.",
            "A text-named file with random-looking bytes may be hiding a payload.",
            {"entropy": round(ins.entropy, 2)},
        ))
    if len(data) < 16:
        signals.append(_signal(
            "tiny_file", "Almost empty file", 0.20,
            f"Only {len(data)} bytes.",
            "Trivial files give no meaningful proof of authorship and collide easily.",
        ))
    if ins.encrypted_pdf:
        signals.append(_signal(
            "encrypted_pdf", "Password-protected PDF", 0.10,
            "Text could not be inspected, so similarity checking was limited to the file hash.",
            "Duplicate detection is weaker for content that cannot be read.",
        ))
    for label, dt in ins.meta_dates:
        naive = dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt
        if naive > utcnow().replace(tzinfo=None) + timedelta(days=1) + timedelta(hours=14):
            signals.append(_signal(
                "future_metadata", "Embedded date is in the future", 0.30,
                f"{label} timestamp is {naive.date()}, which has not happened yet.",
                "Forged or manipulated metadata often carries impossible dates.",
                {"label": label, "date": naive.isoformat()},
            ))
            break

    # ── 4. behaviour ──
    recent = db.scalar(
        select(func.count(RecordVersion.id)).where(
            RecordVersion.created_by == user_id, RecordVersion.created_at > utcnow() - timedelta(minutes=10)
        )
    ) or 0
    if recent >= 8:
        signals.append(_signal(
            "velocity", "Unusually fast registration rate", 0.20,
            f"{recent} versions were registered by this account in the last 10 minutes.",
            "Bulk registration can be used to squat on content before its real author registers it.",
            {"count": recent},
        ))

    # ── score ──
    remaining = 1.0
    for s in signals:
        remaining *= 1 - s["weight"]
    score = round((1 - remaining) * 100)
    level = "LOW" if score < 25 else "MEDIUM" if score < 55 else "HIGH"
    signals.sort(key=lambda s: -s["weight"])

    if not signals:
        summary = "No risk signals detected. The file is unique in the registry and structurally consistent."
        recommendation = "Safe to register."
    else:
        top = signals[0]
        summary = f"{level.title()} risk ({score}/100). Main factor: {top['title'].lower()}."
        recommendation = {
            "LOW": "Safe to register. Minor notes are shown for transparency.",
            "MEDIUM": "Review the flagged signals before relying on this record as proof of originality.",
            "HIGH": "Do not treat this as proof of authorship until the flagged signals are resolved.",
        }[level]

    return {
        "score": score,
        "level": level,
        "summary": summary,
        "recommendation": recommendation,
        "signals": signals,
        "matches": matches[:10],
        "method": "noisy-OR over independent signals: score = 1 - Π(1 - weight)",
        "inspected": {
            "extension": ins.ext,
            "detected_type": ins.sniffed,
            "entropy": round(ins.entropy, 2),
            "text_extracted": ins.text_extracted,
            "text_characters": len(ins.text),
            "similarity_fingerprint": bool(minhash),
            "image_fingerprint": bool(dhash),
        },
    }
