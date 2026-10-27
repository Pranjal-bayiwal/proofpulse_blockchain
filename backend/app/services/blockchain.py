"""Web3.py integration with the ProofPulse smart contract.

Modes
  embedded : in-process EVM (eth-tester). Zero setup, ephemeral – ideal for tests and offline demos.
  rpc      : any Ethereum-compatible JSON-RPC node (Hardhat node, Ganache, Sepolia ...).
"""
import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path

from web3 import Web3

from ..config import BASE_DIR, get_settings

settings = get_settings()
log = logging.getLogger("proofpulse.chain")
ARTIFACT = BASE_DIR / "app" / "contract" / "ProofPulse.json"
ADDRESS_FILE = BASE_DIR / "data" / "contract_address.txt"


class ChainError(Exception):
    pass


def rid(public_id: str) -> bytes:
    """bytes32 record id on chain = sha256(public id)."""
    return hashlib.sha256(public_id.encode()).digest()


def to_b32(hex_str: str) -> bytes:
    b = bytes.fromhex(hex_str[2:] if hex_str.startswith("0x") else hex_str)
    if len(b) != 32:
        raise ChainError("Expected a 32-byte hash")
    return b


def actor_id(user_id: int) -> str:
    """Pseudonymous on-chain identity: salted hash of the user id (no PII on chain)."""
    return hashlib.sha256(f"{settings.pseudonym_salt}:{user_id}".encode()).hexdigest()


class ChainService:
    def __init__(self) -> None:
        self.w3: Web3 | None = None
        self.contract = None
        self.account: str | None = None
        self._private_key: str | None = None
        self.mode = settings.blockchain_mode
        self.lock = threading.RLock()
        self.freshly_deployed = False
        self.last_error: str | None = None
        self.tester = None  # eth-tester handle (embedded mode)
        self.journal_path: Path | None = None
        self._replay_ts: int | None = None  # forced block timestamp while replaying the journal
        self.replayed = 0
        self._journal_lines = 0

    # ───────────── connection ─────────────
    def connect(self) -> None:
        if not ARTIFACT.exists():
            raise ChainError("Contract artifact missing. Run `npm run compile` in the project root first.")
        artifact = json.loads(ARTIFACT.read_text())

        if self.mode == "embedded":
            self._connect_embedded(artifact)
            return
        self._connect_rpc(artifact)

    # ───────────── embedded chain (eth-tester) with a replayable journal ─────────────
    def _new_tester(self, genesis_ts: int | None = None):
        from eth_tester import EthereumTester, PyEVMBackend
        from web3 import EthereumTesterProvider

        params = PyEVMBackend.generate_genesis_params(overrides={"timestamp": genesis_ts}) if genesis_ts else None
        self.tester = EthereumTester(backend=PyEVMBackend(genesis_parameters=params))
        self.w3 = Web3(EthereumTesterProvider(self.tester))
        self.account = self.w3.eth.accounts[0]

    def _set_block_time(self, ts: int) -> None:
        chain = self.tester.backend.chain
        chain.header = chain.header.copy(timestamp=ts)

    def _journal_len(self) -> int:
        try:
            return sum(1 for line in self.journal_path.read_text(encoding="utf-8").splitlines() if line.strip())
        except FileNotFoundError:
            return 0

    def _journal_write(self, entry: dict) -> None:
        if not self.journal_path:
            return
        with open(self.journal_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._journal_lines += 1

    def _guard_single_process(self) -> None:
        """The embedded EVM lives inside one process. A second process appending to the same journal would fork the chain."""
        if self.journal_path and self._journal_len() != self._journal_lines:
            raise ChainError("The embedded chain journal was changed by another process. Run only one ProofPulse backend "
                             "per data folder, or switch to BLOCKCHAIN_MODE=rpc for multi-process setups.")

    def _connect_embedded(self, artifact: dict) -> None:
        code_id = hashlib.sha256(artifact["bytecode"].encode()).hexdigest()[:16]
        self.journal_path = Path(settings.chain_journal) if settings.chain_journal else None
        entries: list[dict] = []
        if self.journal_path and self.journal_path.exists():
            entries = [json.loads(line) for line in self.journal_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if entries:
            try:
                self._replay(artifact, entries, code_id)
                self._journal_lines = len(entries)
                self.freshly_deployed = False
                return
            except Exception as exc:  # corrupt journal or a different contract build
                backup = self.journal_path.with_suffix(f".bad-{int(time.time())}")
                self.journal_path.rename(backup)
                log.error("Chain journal could not be replayed (%s). Moved to %s and starting a fresh chain.", exc, backup.name)
        self._new_tester()
        if self.journal_path:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            self._journal_lines = 0
            self._journal_write({"kind": "genesis", "timestamp": int(self.w3.eth.get_block(0)["timestamp"]), "code": code_id})
        self._deploy(artifact)
        self.freshly_deployed = True

    def _replay(self, artifact: dict, entries: list[dict], code_id: str) -> None:
        head = entries[0]
        if head.get("kind") != "genesis" or head.get("code") != code_id:
            raise ChainError("journal was written by a different contract build")
        journal, self.journal_path = self.journal_path, None  # do not re-journal while replaying
        try:
            self._new_tester(int(head["timestamp"]))
            for e in entries[1:]:
                self._replay_ts = int(e["timestamp"])
                if e["kind"] == "deploy":
                    self._deploy(artifact)
                else:
                    abi = next(a for a in artifact["abi"] if a.get("type") == "function" and a["name"] == e["fn"])
                    args = [_dec(i["type"], v) for i, v in zip(abi["inputs"], e["args"])]
                    receipt = self._send(getattr(self.contract.functions, e["fn"])(*args))
                    if receipt["tx_hash"] != e["tx_hash"]:
                        raise ChainError(f"replayed transaction hash differs at block {receipt['block_number']}")
                self.replayed += 1
        finally:
            self._replay_ts = None
            self.journal_path = journal
        if self.contract is None:
            raise ChainError("journal contains no deployment")

    def _connect_rpc(self, artifact: dict) -> None:
        self.w3 = Web3(Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": 30}))
        if not self.w3.is_connected():
            raise ChainError(f"Cannot reach blockchain node at {settings.rpc_url}. Start it with `npm run node`.")
        if settings.chain_private_key:
            acct = self.w3.eth.account.from_key(settings.chain_private_key)
            self._private_key = settings.chain_private_key
            self.account = acct.address
        else:
            accounts = self.w3.eth.accounts
            if not accounts:
                raise ChainError("Node exposes no unlocked accounts; set CHAIN_PRIVATE_KEY.")
            self.account = accounts[0]

        address = settings.contract_address.strip()
        if not address and ADDRESS_FILE.exists() and self.mode == "rpc":
            address = ADDRESS_FILE.read_text().strip()

        if address and Web3.is_address(address) and self.w3.eth.get_code(Web3.to_checksum_address(address)):
            self.contract = self.w3.eth.contract(address=Web3.to_checksum_address(address), abi=artifact["abi"])
            self.freshly_deployed = False
        else:
            self._deploy(artifact)
            self.freshly_deployed = True

    def _deploy(self, artifact: dict) -> None:
        factory = self.w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
        receipt = self._send(factory.constructor(), journal={"kind": "deploy"})
        address = receipt["contractAddress"]
        self.contract = self.w3.eth.contract(address=address, abi=artifact["abi"])
        if self.mode == "rpc":
            ADDRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
            ADDRESS_FILE.write_text(address)

    # ───────────── transactions ─────────────
    def _send(self, fn, journal: dict | None = None) -> dict:
        with self.lock:
            if self._replay_ts is None:
                self._guard_single_process()
            try:
                if self._replay_ts is not None:
                    self._set_block_time(self._replay_ts)
                if self._private_key:
                    tx = fn.build_transaction(
                        {
                            "from": self.account,
                            "nonce": self.w3.eth.get_transaction_count(self.account),
                            "chainId": self.w3.eth.chain_id,
                        }
                    )
                    signed = self.w3.eth.account.sign_transaction(tx, self._private_key)
                    tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                else:
                    tx_hash = fn.transact({"from": self.account})
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            except Exception as exc:  # contract reverts, RPC errors
                self.last_error = str(exc)
                raise ChainError(_friendly(exc)) from exc
            if receipt["status"] != 1:
                raise ChainError("Transaction reverted on chain")
            block = self.w3.eth.get_block(receipt["blockNumber"])
            result = {
                "tx_hash": "0x" + bytes(receipt["transactionHash"]).hex(),
                "block_number": int(receipt["blockNumber"]),
                "timestamp": int(block["timestamp"]),
                "contractAddress": receipt.get("contractAddress"),
            }
            if self.journal_path and self._replay_ts is None:
                entry = journal or {"kind": "call", "fn": fn.fn_name, "args": [_enc(a) for a in fn.args]}
                self._journal_write({**entry, "timestamp": result["timestamp"], "tx_hash": result["tx_hash"]})
            return result

    @staticmethod
    def _res(r: dict) -> dict:
        return {k: r[k] for k in ("tx_hash", "block_number", "timestamp")}

    def register(self, public_id: str, content_hash: str, metadata_hash: str, owner: str) -> dict:
        fn = self.contract.functions.registerRecord(rid(public_id), to_b32(content_hash), to_b32(metadata_hash), to_b32(owner))
        return self._res(self._send(fn))

    def add_version(self, public_id: str, content_hash: str, metadata_hash: str, actor: str) -> dict:
        fn = self.contract.functions.addVersion(rid(public_id), to_b32(content_hash), to_b32(metadata_hash), to_b32(actor))
        return self._res(self._send(fn))

    def decision(self, public_id: str, version_no: int, approver: str, approved: bool, comment_hash: str) -> dict:
        fn = self.contract.functions.recordDecision(rid(public_id), version_no, to_b32(approver), approved, to_b32(comment_hash))
        return self._res(self._send(fn))

    def revoke(self, public_id: str, actor: str, reason_hash: str) -> dict:
        fn = self.contract.functions.revokeRecord(rid(public_id), to_b32(actor), to_b32(reason_hash))
        return self._res(self._send(fn))

    # ───────────── reads ─────────────
    def get_record(self, public_id: str) -> dict | None:
        try:
            owner, created, revoked, count = self.contract.functions.getRecord(rid(public_id)).call()
        except Exception:
            return None
        versions = []
        for i in range(1, count + 1):
            h, m, a, ts, ap, rj = self.contract.functions.getVersion(rid(public_id), i).call()
            versions.append(
                {
                    "version_no": i,
                    "content_hash": bytes(h).hex(),
                    "metadata_hash": bytes(m).hex(),
                    "actor_id": bytes(a).hex(),
                    "timestamp": int(ts),
                    "approvals": int(ap),
                    "rejections": int(rj),
                }
            )
        return {
            "owner_id": bytes(owner).hex(),
            "created_at": int(created),
            "revoked": bool(revoked),
            "version_count": int(count),
            "versions": versions,
        }

    def history(self, public_id: str) -> list[dict]:
        """Raw event log straight from the chain (independent of the database)."""
        rec = rid(public_id)
        out: list[dict] = []
        ev = self.contract.events
        specs = [
            ("RecordRegistered", ev.RecordRegistered),
            ("VersionAdded", ev.VersionAdded),
            ("DecisionRecorded", ev.DecisionRecorded),
            ("RecordRevoked", ev.RecordRevoked),
        ]
        for name, event in specs:
            try:
                logs = event().get_logs(from_block=0, argument_filters={"recordId": rec})
            except Exception:
                continue
            for log in logs:
                args = dict(log["args"])
                item = {
                    "event": name,
                    "block_number": int(log["blockNumber"]),
                    "tx_hash": "0x" + bytes(log["transactionHash"]).hex(),
                    "log_index": int(log["logIndex"]),
                    "timestamp": int(args.get("timestamp", 0)),
                }
                if "versionIndex" in args:
                    item["version_no"] = int(args["versionIndex"])
                if "approved" in args:
                    item["approved"] = bool(args["approved"])
                if "contentHash" in args:
                    item["content_hash"] = bytes(args["contentHash"]).hex()
                out.append(item)
        out.sort(key=lambda e: (e["block_number"], e["log_index"]))
        return out

    def status(self) -> dict:
        try:
            c = self.contract.functions
            return {
                "connected": True,
                "mode": self.mode,
                "network_id": str(self.w3.eth.chain_id),
                "block_number": int(self.w3.eth.block_number),
                "contract_address": self.contract.address,
                "registrar": self.account,
                "balance_eth": float(Web3.from_wei(self.w3.eth.get_balance(self.account), "ether")),
                "total_records": int(c.totalRecords().call()),
                "total_versions": int(c.totalVersions().call()),
                "total_approvals": int(c.totalApprovals().call()),
                "persistent": self.mode != "embedded" or bool(self.journal_path),
                "replayed_transactions": self.replayed,
            }
        except Exception as exc:
            return {"connected": False, "mode": self.mode, "error": str(exc)}

    def first_record_for_hash(self, content_hash: str) -> str | None:
        try:
            r = self.contract.functions.firstRecordForHash(to_b32(content_hash)).call()
        except Exception:
            return None
        return bytes(r).hex() if any(r) else None


def _enc(v):
    return "0x" + bytes(v).hex() if isinstance(v, (bytes, bytearray)) else v


def _dec(abi_type: str, v):
    if abi_type.startswith("bytes"):
        return bytes.fromhex(v[2:] if isinstance(v, str) and v.startswith("0x") else v)
    return v


def _friendly(exc: Exception) -> str:
    text = str(exc)
    mapping = {
        "AlreadyExists": "Record already exists on chain",
        "UnknownRecord": "Record is unknown to the chain",
        "RecordIsRevoked": "Record has been revoked",
        "AlreadyDecided": "This approver already decided on this version",
        "NotRegistrar": "Backend account is not authorised as registrar",
        "UnknownVersion": "Unknown version",
        "EmptyHash": "Empty hash rejected",
    }
    for key, msg in mapping.items():
        selector = Web3.keccak(text=f"{key}()")[:4]
        if key in text or selector.hex() in text or repr(bytes(selector)) in text or repr(bytes(selector))[2:-1] in text:
            return msg
    return f"Blockchain error: {text[:200]}"


chain = ChainService()
