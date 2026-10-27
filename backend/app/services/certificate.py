"""Verification certificate (PDF) and QR code generation."""
import hashlib
import hmac
import io
from datetime import datetime

import qrcode
from qrcode.constants import ERROR_CORRECT_M
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from ..config import get_settings
from ..models import Record, RecordVersion
from ..utils import iso, utcnow
from .blockchain import chain

settings = get_settings()

NAVY = colors.HexColor("#0B1020")
CYAN = colors.HexColor("#06B6D4")
VIOLET = colors.HexColor("#7C3AED")
GREY = colors.HexColor("#64748B")


def verify_url(public_id: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/verify/{public_id}"


def seal(public_id: str, content_hash: str, tx_hash: str | None) -> str:
    """HMAC seal binding id + hash + tx. Lets ProofPulse confirm a certificate is one it issued."""
    msg = f"{public_id}|{content_hash}|{tx_hash or ''}".encode()
    return hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).hexdigest()[:24].upper()


def qr_png(public_id: str, box: int = 8) -> bytes:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=box, border=2)
    qr.add_data(verify_url(public_id))
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0B1020", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _wrap(c: canvas.Canvas, text: str, x: float, y: float, width: float, font: str, size: int, leading: float) -> float:
    c.setFont(font, size)
    words, line = text.split(), ""
    for w in words:
        trial = f"{line} {w}".strip()
        if c.stringWidth(trial, font, size) > width and line:
            c.drawString(x, y, line)
            y -= leading
            line = w
        else:
            line = trial
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def build_certificate(rec: Record, version: RecordVersion, trust: dict, include_title: bool = True) -> bytes:
    buf = io.BytesIO()
    W, H = landscape(A4)
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"ProofPulse Certificate {rec.public_id}")
    c.setAuthor("ProofPulse")

    # background + frame
    c.setFillColor(colors.white)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.rect(0, H - 92, W, 92, stroke=0, fill=1)
    c.setFillColor(CYAN)
    c.rect(0, H - 96, W * 0.55, 4, stroke=0, fill=1)
    c.setFillColor(VIOLET)
    c.rect(W * 0.55, H - 96, W * 0.45, 4, stroke=0, fill=1)
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(0.8)
    c.rect(18, 18, W - 36, H - 36, stroke=1, fill=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(44, H - 52, "ProofPulse")
    c.setFont("Helvetica", 11)
    c.setFillColor(colors.HexColor("#A5F3FC"))
    c.drawString(44, H - 72, "Blockchain Authenticity & Provenance Certificate")
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(W - 44, H - 52, rec.public_id)
    c.setFont("Helvetica", 9)
    c.drawRightString(W - 44, H - 70, f"Issued {iso(utcnow())}")

    y = H - 135
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 20)
    title = rec.title if include_title else "Private record"
    c.drawString(44, y, title[:70] + ("…" if len(title) > 70 else ""))
    y -= 22
    c.setFont("Helvetica", 11)
    c.setFillColor(GREY)
    c.drawString(44, y, f"{rec.category.title()}  •  Version {version.version_no} of {len(rec.versions)}  •  File: {version.filename}")
    y -= 14
    c.drawString(44, y, f"Registered by {rec.owner.full_name if include_title else 'a verified account holder'}")

    # facts
    y -= 34
    left = 44
    facts = [
        ("Status", rec.status.replace("_", " ").title()),
        ("Registered", iso(rec.created_at) or "-"),
        ("Anchored at (chain time)", iso(version.chain_timestamp) or "not anchored"),
        ("Block number", str(version.block_number) if version.block_number is not None else "-"),
        ("Trust score", f"{trust['score']}/100 ({trust['label']})"),
        ("Risk analysis", f"{version.risk_level.title()} ({version.risk_score}/100)"),
        ("File size", f"{version.size:,} bytes"),
    ]
    for k, v in facts:
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(GREY)
        c.drawString(left, y, k.upper())
        c.setFont("Helvetica", 11)
        c.setFillColor(NAVY)
        c.drawString(left + 150, y, v)
        y -= 19

    # hashes
    y -= 8
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(GREY)
    c.drawString(left, y, "SHA-256 FINGERPRINT")
    y -= 15
    c.setFont("Courier-Bold", 9.5)
    c.setFillColor(NAVY)
    c.drawString(left, y, version.sha256)
    y -= 22
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(GREY)
    c.drawString(left, y, "TRANSACTION HASH")
    y -= 15
    c.setFont("Courier", 8.5)
    c.setFillColor(NAVY)
    c.drawString(left, y, version.tx_hash or "not anchored")
    y -= 22
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(GREY)
    c.drawString(left, y, "SMART CONTRACT")
    y -= 15
    c.setFont("Courier", 8.5)
    c.setFillColor(NAVY)
    try:
        c.drawString(left, y, f"{chain.contract.address}  ({chain.mode} network {chain.w3.eth.chain_id})")
    except Exception:
        c.drawString(left, y, "unavailable")

    # QR
    qr = ImageReader(io.BytesIO(qr_png(rec.public_id, box=9)))
    qx, qy, qs = W - 44 - 150, 140, 150
    c.drawImage(qr, qx, qy, qs, qs)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(NAVY)
    c.drawCentredString(qx + qs / 2, qy - 14, "Scan to verify")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(GREY)
    c.drawCentredString(qx + qs / 2, qy - 26, verify_url(rec.public_id).replace("https://", "").replace("http://", ""))

    # footer
    c.setStrokeColor(colors.HexColor("#E2E8F0"))
    c.line(44, 78, W - 44, 78)
    c.setFont("Helvetica", 8)
    c.setFillColor(GREY)
    foot = (
        "This certificate attests that a file with the fingerprint above was registered on the ProofPulse smart contract "
        "at the time shown. It does not store the file itself. To confirm authenticity, upload the file at the verification "
        "link: any change of even one byte produces a different fingerprint and the check fails."
    )
    _wrap(c, foot, 44, 62, W - 88, "Helvetica", 8, 11)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(NAVY)
    c.drawString(44, 28, f"Seal: {seal(rec.public_id, version.sha256, version.tx_hash)}")
    c.setFont("Helvetica", 8)
    c.setFillColor(GREY)
    c.drawRightString(W - 44, 28, "Generated by ProofPulse")
    c.showPage()
    c.save()
    return buf.getvalue()
