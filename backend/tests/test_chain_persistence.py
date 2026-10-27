"""The embedded chain must survive a restart with identical blocks, timestamps and transaction hashes."""
import hashlib
import time

from app.config import get_settings
from app.services.blockchain import ChainService, rid


def h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def test_restart_replays_journal_with_original_timestamps(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "chain_journal", str(tmp_path / "journal.jsonl"))
    import app.services.blockchain as bc
    monkeypatch.setattr(bc, "settings", settings)

    first = ChainService()
    first.connect()
    assert first.freshly_deployed
    a = first.register("PP-AAAAAAAAAA", h("c1"), h("m1"), h("o1"))
    time.sleep(1.1)
    b = first.add_version("PP-AAAAAAAAAA", h("c2"), h("m2"), h("o1"))
    c = first.decision("PP-AAAAAAAAAA", 2, h("approver"), True, h("ok"))
    d = first.revoke("PP-AAAAAAAAAA", h("o1"), h("why"))
    address = first.contract.address
    before = first.get_record("PP-AAAAAAAAAA")

    time.sleep(1.1)
    second = ChainService()  # simulates a server restart: brand-new EVM, same journal
    second.connect()
    assert not second.freshly_deployed
    assert second.replayed == 5  # deploy + 4 calls
    assert second.contract.address == address
    after = second.get_record("PP-AAAAAAAAAA")
    assert after == before  # contents AND timestamps identical
    assert after["revoked"] and after["version_count"] == 2
    assert after["versions"][0]["timestamp"] == a["timestamp"]
    assert after["versions"][1]["timestamp"] == b["timestamp"]
    # transaction receipts are identical, so hashes stored in the database stay valid
    for r in (a, b, c, d):
        assert second.w3.eth.get_transaction_receipt(r["tx_hash"])["blockNumber"] == r["block_number"]
    # the chain keeps working after the replay
    e = second.register("PP-BBBBBBBBBB", h("c9"), h("m9"), h("o2"))
    assert e["timestamp"] > d["timestamp"]
    assert second.status()["persistent"] is True


def test_incompatible_journal_falls_back_to_fresh_chain(tmp_path, monkeypatch):
    settings = get_settings()
    journal = tmp_path / "journal.jsonl"
    journal.write_text('{"kind":"genesis","timestamp":1700000000,"code":"deadbeef"}\n{"kind":"deploy","timestamp":1700000005,"tx_hash":"0x00"}\n')
    monkeypatch.setattr(settings, "chain_journal", str(journal))
    import app.services.blockchain as bc
    monkeypatch.setattr(bc, "settings", settings)
    svc = ChainService()
    svc.connect()
    assert svc.freshly_deployed
    assert list(tmp_path.glob("journal.bad-*"))
    assert rid("PP-AAAAAAAAAA")  # sanity
