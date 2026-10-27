"""Direct smart-contract tests (access control, invariants) on the in-process EVM."""
import hashlib
import json

import pytest
from web3 import EthereumTesterProvider, Web3
from web3.exceptions import ContractLogicError

from app.config import BASE_DIR

ART = json.loads((BASE_DIR / "app" / "contract" / "ProofPulse.json").read_text())


def h(s: str) -> bytes:
    return hashlib.sha256(s.encode()).digest()


@pytest.fixture()
def env():
    w3 = Web3(EthereumTesterProvider())
    admin, registrar, stranger = w3.eth.accounts[:3]
    c = w3.eth.contract(abi=ART["abi"], bytecode=ART["bytecode"])
    addr = w3.eth.wait_for_transaction_receipt(c.constructor().transact({"from": admin}))["contractAddress"]
    contract = w3.eth.contract(address=addr, abi=ART["abi"])
    return w3, contract, admin, registrar, stranger


def test_only_registrars_can_write(env):
    w3, c, admin, registrar, stranger = env
    with pytest.raises(Exception):
        c.functions.registerRecord(h("r1"), h("c1"), h("m1"), h("o")).transact({"from": stranger})
    c.functions.setRegistrar(registrar, True).transact({"from": admin})
    c.functions.registerRecord(h("r1"), h("c1"), h("m1"), h("o")).transact({"from": registrar})
    assert c.functions.totalRecords().call() == 1
    with pytest.raises(Exception):
        c.functions.setRegistrar(stranger, True).transact({"from": stranger})


def test_no_duplicate_ids_and_empty_hash_rejected(env):
    w3, c, admin, *_ = env
    c.functions.registerRecord(h("r1"), h("c1"), h("m1"), h("o")).transact({"from": admin})
    with pytest.raises(Exception):
        c.functions.registerRecord(h("r1"), h("c2"), h("m1"), h("o")).transact({"from": admin})
    with pytest.raises(Exception):
        c.functions.registerRecord(h("r2"), b"\x00" * 32, h("m1"), h("o")).transact({"from": admin})


def test_versions_are_append_only_and_verifiable(env):
    w3, c, admin, *_ = env
    c.functions.registerRecord(h("r"), h("v1"), h("m"), h("o")).transact({"from": admin})
    c.functions.addVersion(h("r"), h("v2"), h("m"), h("o")).transact({"from": admin})
    assert c.functions.verifyLatest(h("r"), h("v2")).call() is True
    assert c.functions.verifyLatest(h("r"), h("v1")).call() is False
    ok, idx = c.functions.verifyAny(h("r"), h("v1")).call()
    assert ok and idx == 1
    assert list(c.functions.verifyAny(h("r"), h("nope")).call()) == [False, 0]
    assert c.functions.getRecord(h("r")).call()[3] == 2


def test_decisions_once_per_approver_and_counts(env):
    w3, c, admin, *_ = env
    c.functions.registerRecord(h("r"), h("v1"), h("m"), h("o")).transact({"from": admin})
    c.functions.recordDecision(h("r"), 1, h("a1"), True, h("c")).transact({"from": admin})
    c.functions.recordDecision(h("r"), 1, h("a2"), False, h("c")).transact({"from": admin})
    with pytest.raises(Exception):
        c.functions.recordDecision(h("r"), 1, h("a1"), False, h("c")).transact({"from": admin})
    v = c.functions.getVersion(h("r"), 1).call()
    assert v[4] == 1 and v[5] == 1
    with pytest.raises(Exception):
        c.functions.recordDecision(h("r"), 9, h("a3"), True, h("c")).transact({"from": admin})


def test_revoked_record_is_frozen(env):
    w3, c, admin, *_ = env
    c.functions.registerRecord(h("r"), h("v1"), h("m"), h("o")).transact({"from": admin})
    c.functions.revokeRecord(h("r"), h("o"), h("why")).transact({"from": admin})
    assert c.functions.verifyLatest(h("r"), h("v1")).call() is False
    with pytest.raises(Exception):
        c.functions.addVersion(h("r"), h("v2"), h("m"), h("o")).transact({"from": admin})
    assert c.functions.getRecord(h("r")).call()[2] is True


def test_first_record_for_hash_gives_priority(env):
    w3, c, admin, *_ = env
    c.functions.registerRecord(h("first"), h("same"), h("m"), h("o")).transact({"from": admin})
    c.functions.registerRecord(h("second"), h("same"), h("m"), h("o")).transact({"from": admin})
    assert bytes(c.functions.firstRecordForHash(h("same")).call()) == h("first")
