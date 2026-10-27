"""End-to-end tests against a real in-process blockchain (eth-tester)."""
import hashlib

from .conftest import PASSWORD, upload

ORIGINAL = (b"ProofPulse test manuscript. " + b"The quick brown fox jumps over the lazy dog near the river bank. " * 30)


def test_health_and_chain(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["blockchain"]["connected"] is True


def test_auth_validation_and_login(client):
    weak = client.post("/api/auth/register", json={"username": "weak", "email": "weak@example.com", "full_name": "Weak User", "password": "short"})
    assert weak.status_code == 422
    bad_name = client.post("/api/auth/register", json={"username": "a b", "email": "x@example.com", "full_name": "X Y", "password": PASSWORD})
    assert bad_name.status_code == 422
    assert client.get("/api/auth/me").status_code == 401
    bad = client.post("/api/auth/login", json={"identifier": "nobody", "password": "whatever"})
    assert bad.status_code == 401


def test_register_record_and_verify_authentic(client, alice):
    r = upload(client, alice, ORIGINAL, title="My manuscript")
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["public_id"].startswith("PP-")
    assert rec["sha256"] == hashlib.sha256(ORIGINAL).hexdigest()
    assert rec["tx_hash"] and rec["block_number"] is not None

    # public verification, no auth
    v = client.get(f"/api/verify/{rec['public_id']}").json()
    assert v["verdict"] == "REGISTERED"
    assert v["chain"]["found"] and v["consistency"]["ok"]

    ok = client.post(f"/api/verify/{rec['public_id']}/file", files={"file": ("x.txt", ORIGINAL)}).json()
    assert ok["verdict"] == "AUTHENTIC"
    assert ok["file_check"]["is_latest"] is True

    h = client.post(f"/api/verify/{rec['public_id']}/hash", json={"sha256": hashlib.sha256(ORIGINAL).hexdigest()}).json()
    assert h["verdict"] == "AUTHENTIC"


def test_tamper_detection_one_byte(client, alice):
    rec = upload(client, alice, ORIGINAL + b" unique tamper test one", title="Tamper subject").json()
    tampered = bytearray(ORIGINAL + b" unique tamper test one")
    tampered[10] ^= 0x01
    res = client.post(f"/api/verify/{rec['public_id']}/file", files={"file": ("x.txt", bytes(tampered))}).json()
    assert res["verdict"] == "TAMPERED"
    assert res["file_check"]["matches"] is False


def test_unknown_id(client):
    assert client.get("/api/verify/PP-ABCDEFGHJK").json()["verdict"] == "NOT_FOUND"
    assert client.get("/api/verify/garbage").json()["verdict"] == "NOT_FOUND"


def test_versions_and_outdated(client, alice):
    v1 = ORIGINAL + b" version-one marker"
    rec = upload(client, alice, v1, title="Versioned").json()
    v2 = v1 + b" and an edited sentence appended for version two."
    r = client.post(f"/api/records/{rec['public_id']}/versions", headers=alice,
                    data={"note": "Added sentence"}, files={"file": ("paper.txt", v2)})
    assert r.status_code == 201, r.text
    assert r.json()["version_count"] == 2
    old = client.post(f"/api/verify/{rec['public_id']}/file", files={"file": ("a.txt", v1)}).json()
    assert old["verdict"] == "OUTDATED_VERSION" and old["file_check"]["matched_version"] == 1
    new = client.post(f"/api/verify/{rec['public_id']}/file", files={"file": ("a.txt", v2)}).json()
    assert new["verdict"] == "AUTHENTIC"
    dup = client.post(f"/api/records/{rec['public_id']}/versions", headers=alice, data={"note": "again"}, files={"file": ("paper.txt", v2)})
    assert dup.status_code == 409


def test_only_owner_can_add_version(client, alice, bob):
    rec = upload(client, alice, ORIGINAL + b" owner only test", title="Owner only").json()
    r = client.post(f"/api/records/{rec['public_id']}/versions", headers=bob, data={"note": "x"}, files={"file": ("p.txt", b"hello world different")})
    assert r.status_code in (403, 404)


def varied_text(seed: int, n: int = 600) -> bytes:
    import random
    rng = random.Random(seed)
    words = ("ledger block hash provenance research dataset signature proof document authentic timestamp version approval "
             "trust node chain integrity fingerprint author review risk archive record citation method result analysis").split()
    return " ".join(f"{rng.choice(words)}{rng.randint(0, 40)}" for _ in range(n)).encode()


def test_duplicate_detection_other_owner(client, alice, bob):
    text = varied_text(7)
    first = upload(client, alice, text, title="Alice original").json()
    # exact copy by Bob
    copy = upload(client, bob, text, title="Bob copy", visibility="private").json()
    sigs = {s["id"] for s in client.get(f"/api/records/{copy['public_id']}", headers=bob).json()["versions"][0]["risk_report"]["signals"]}
    assert "exact_duplicate_other" in sigs
    assert copy["risk_level"] in ("MEDIUM", "HIGH")
    # near-duplicate: small edit
    edited = text.replace(text.split()[5], b"changedword", 1) + b" one extra closing sentence here"
    near = upload(client, bob, edited, title="Bob edited copy").json()
    report = client.get(f"/api/records/{near['public_id']}", headers=bob).json()["versions"][0]["risk_report"]
    assert any(s["id"] == "near_duplicate_other" for s in report["signals"])
    # Alice (original owner) is notified
    notes = client.get("/api/notifications", headers=alice).json()["items"]
    assert any("copy" in n["title"].lower() for n in notes)
    # privacy: Bob's evidence must not leak Alice's title
    assert "Alice original" not in str(report)
    assert first["public_id"] in str(report)


def test_risk_signals_type_mismatch_and_hidden_chars(client, alice):
    fake_pdf = b"this is not really a pdf, just plain words " * 20
    r = upload(client, alice, fake_pdf, name="report.pdf", title="Fake pdf").json()
    rep = client.get(f"/api/records/{r['public_id']}", headers=alice).json()["versions"][0]["risk_report"]
    assert any(s["id"] == "type_mismatch" for s in rep["signals"])
    sneaky = ("Normal looking sentence about research methods and findings. " * 10 + "​​‮ hidden").encode()
    r2 = upload(client, alice, sneaky, title="Hidden chars").json()
    rep2 = client.get(f"/api/records/{r2['public_id']}", headers=alice).json()["versions"][0]["risk_report"]
    assert any(s["id"] == "hidden_characters" for s in rep2["signals"])
    assert 0 <= rep2["score"] <= 100 and rep2["method"]


def test_analyze_dry_run_does_not_register(client, alice):
    before = client.get("/api/records?scope=mine", headers=alice).json()["total"]
    r = client.post("/api/analyze", headers=alice, files={"file": ("n.txt", b"fresh unique analysis only content " * 12)})
    assert r.status_code == 200 and "risk" in r.json()
    assert client.get("/api/records?scope=mine", headers=alice).json()["total"] == before


def test_approval_workflow_on_chain(client, alice, bob, carol):
    rec = upload(client, alice, ORIGINAL + b" approval workflow doc", title="Needs approval").json()
    pid = rec["public_id"]
    r = client.post(f"/api/records/{pid}/approvals", headers=alice, json={"approvers": ["bob", "carol"]})
    assert r.status_code == 201, r.text
    assert r.json()["record"]["status"] == "PENDING_APPROVAL"
    assert client.post(f"/api/records/{pid}/approvals", headers=alice, json={"approvers": ["alice"]}).status_code == 422

    inbox = client.get("/api/approvals/inbox", headers=bob).json()
    item = next(i for i in inbox if i["record_public_id"] == pid)
    ok = client.post(f"/api/approvals/{item['id']}/decision", headers=bob, json={"approve": True, "comment": "Looks right"})
    assert ok.status_code == 200 and ok.json()["tx_hash"]
    assert ok.json()["record_status"] == "PENDING_APPROVAL"
    again = client.post(f"/api/approvals/{item['id']}/decision", headers=bob, json={"approve": True})
    assert again.status_code == 409
    # carol cannot decide bob's request
    assert client.post(f"/api/approvals/{item['id']}/decision", headers=carol, json={"approve": True}).status_code == 404

    citem = next(i for i in client.get("/api/approvals/inbox", headers=carol).json() if i["record_public_id"] == pid)
    done = client.post(f"/api/approvals/{citem['id']}/decision", headers=carol, json={"approve": True, "comment": "Agreed"})
    assert done.json()["record_status"] == "APPROVED"

    v = client.get(f"/api/verify/{pid}").json()
    assert v["approvals"]["approved"] == 2
    assert v["chain"]["versions"][0]["approvals"] == 2
    assert v["trust"]["score"] > rec["trust_score"]
    kinds = [e["event"] for e in v["chain"]["history"]]
    assert kinds.count("DecisionRecorded") == 2


def test_rejection_requires_reason_and_sets_status(client, alice, bob):
    rec = upload(client, alice, ORIGINAL + b" rejection doc", title="Will be rejected").json()
    pid = rec["public_id"]
    client.post(f"/api/records/{pid}/approvals", headers=alice, json={"approvers": ["bob"]})
    item = next(i for i in client.get("/api/approvals/inbox", headers=bob).json() if i["record_public_id"] == pid)
    assert client.post(f"/api/approvals/{item['id']}/decision", headers=bob, json={"approve": False, "comment": ""}).status_code == 422
    r = client.post(f"/api/approvals/{item['id']}/decision", headers=bob, json={"approve": False, "comment": "Figures do not match"})
    assert r.json()["record_status"] == "REJECTED"


def test_revoke(client, alice):
    rec = upload(client, alice, ORIGINAL + b" revoke doc", title="To revoke").json()
    pid = rec["public_id"]
    r = client.post(f"/api/records/{pid}/revoke", headers=alice, json={"reason": "Published in error"})
    assert r.status_code == 200 and r.json()["status"] == "REVOKED"
    v = client.post(f"/api/verify/{pid}/file", files={"file": ("a.txt", ORIGINAL + b" revoke doc")}).json()
    assert v["verdict"] == "REVOKED"
    assert client.post(f"/api/records/{pid}/revoke", headers=alice, json={"reason": "again please"}).status_code == 409


def test_privacy_private_record_hides_metadata(client, alice, bob):
    rec = upload(client, alice, ORIGINAL + b" private doc", title="Secret title", visibility="private").json()
    pid = rec["public_id"]
    pub = client.get(f"/api/verify/{pid}").json()
    assert pub["record"]["title"] is None and pub["record"]["owner"] is None
    assert client.get(f"/api/records/{pid}", headers=bob).status_code == 404
    assert client.get(f"/api/records/{pid}", headers=alice).json()["title"] == "Secret title"


def test_lookup_by_file_priority(client, alice):
    content = ORIGINAL + b" lookup priority doc"
    rec = upload(client, alice, content, title="Priority").json()
    res = client.post("/api/verify-lookup/file", files={"file": ("any.txt", content)}).json()
    assert res["registered"] and res["earliest"]["public_id"] == rec["public_id"]
    none = client.post("/api/verify-lookup/file", files={"file": ("any.txt", b"never registered content xyz 123")}).json()
    assert none["registered"] is False


def test_certificate_and_qr(client, alice):
    rec = upload(client, alice, ORIGINAL + b" certificate doc", title="Cert doc").json()
    pid = rec["public_id"]
    pdf = client.get(f"/api/records/{pid}/certificate")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    qr = client.get(f"/api/records/{pid}/qr.png")
    assert qr.status_code == 200 and qr.content.startswith(b"\x89PNG")


def test_stored_file_encrypted_and_integrity(client, alice):
    content = ORIGINAL + b" stored copy doc"
    rec = upload(client, alice, content, title="Stored", store_file="true").json()
    pid = rec["public_id"]
    dl = client.get(f"/api/records/{pid}/versions/1/file", headers=alice)
    assert dl.status_code == 200 and dl.content == content and dl.headers["x-integrity"] == "ok"
    from app.models import RecordVersion
    from app.database import SessionLocal
    from app.config import get_settings
    with SessionLocal() as db:
        v = db.query(RecordVersion).filter_by(sha256=hashlib.sha256(content).hexdigest()).first()
        raw = (__import__("pathlib").Path(get_settings().storage_dir) / v.stored_path).read_bytes()
        assert content not in raw  # encrypted at rest
    assert client.post(f"/api/records/{pid}/integrity", headers=alice).json()["ok"] is True


def test_db_tampering_detected_against_chain(client, alice, admin):
    content = ORIGINAL + b" db tamper doc"
    rec = upload(client, alice, content, title="DB tamper").json()
    pid = rec["public_id"]
    from app.database import SessionLocal
    from app.models import RecordVersion, Record
    with SessionLocal() as db:
        r = db.query(Record).filter_by(public_id=pid).one()
        db.query(RecordVersion).filter_by(record_id=r.id).update({"sha256": "0" * 64})
        db.commit()
    v = client.get(f"/api/verify/{pid}").json()
    assert v["verdict"] == "ANCHOR_MISMATCH" and not v["consistency"]["ok"]
    scan = client.post("/api/admin/integrity-scan", headers=admin).json()
    assert not scan["ok"] and any(i["record"] == pid for i in scan["issues"])


def test_audit_chain_and_tamper_evidence(client, alice, admin):
    chain = client.get("/api/audit/verify-chain", headers=alice).json()
    assert chain["valid"] is True and chain["entries"] > 5
    q = client.get("/api/audit?action=RECORD_REGISTERED", headers=alice).json()
    assert q["total"] >= 1 and all(e["action"] == "RECORD_REGISTERED" for e in q["items"])
    csv = client.get("/api/audit/export.csv", headers=admin)
    assert csv.status_code == 200 and csv.text.startswith("seq,")
    from app.database import SessionLocal
    from app.models import AuditLog
    with SessionLocal() as db:
        e = db.query(AuditLog).order_by(AuditLog.seq.desc()).first()
        e.details = {"forged": True}
        db.commit()
    broken = client.get("/api/audit/verify-chain", headers=alice).json()
    assert broken["valid"] is False and broken["broken_at_seq"] is not None


def test_admin_rbac(client, alice, admin):
    assert client.get("/api/admin/overview", headers=alice).status_code == 403
    assert client.get("/api/admin/overview").status_code == 401
    ov = client.get("/api/admin/overview", headers=admin).json()
    assert ov["totals"]["records"] > 5 and ov["chain"]["connected"]
    users = client.get("/api/admin/users", headers=admin).json()
    assert any(u["username"] == "admin" for u in users)


def test_dashboard_and_listing_filters(client, alice):
    d = client.get("/api/dashboard", headers=alice).json()
    assert d["totals"]["records"] > 3 and len(d["registrations_per_day"]) == 14
    lst = client.get("/api/records?q=versioned", headers=alice).json()
    assert lst["total"] >= 1 and all("versioned" in (i["title"] or "").lower() for i in lst["items"])
    pub = client.get("/api/records?scope=public", headers=alice).json()
    assert all(i["visibility"] == "public" for i in pub["items"])


def test_upload_validation(client, alice):
    r = client.post("/api/records", headers=alice, data={"title": "x", "category": "document"}, files={"file": ("a.txt", b"hello hello hello")})
    assert r.status_code == 422  # title too short
    r = client.post("/api/records", headers=alice, data={"title": "Valid title", "category": "bogus"}, files={"file": ("a.txt", b"hello hello hello")})
    assert r.status_code == 422
    r = client.post("/api/records", headers=alice, data={"title": "Valid title"}, files={"file": ("a.txt", b"")})
    assert r.status_code == 400
    assert client.post("/api/records", data={"title": "Valid title"}, files={"file": ("a.txt", b"abc")}).status_code == 401


def test_account_lockout(client):
    client.post("/api/auth/register", json={"username": "locky", "email": "locky@example.com", "full_name": "Locky Test", "password": PASSWORD})
    for _ in range(5):
        assert client.post("/api/auth/login", json={"identifier": "locky", "password": "wrong"}).status_code == 401
    r = client.post("/api/auth/login", json={"identifier": "locky", "password": PASSWORD})
    assert r.status_code == 423
