# ProofPulse — AI-Powered Blockchain Authenticity & Provenance Platform

Register any document, dataset, research file or project submission. ProofPulse computes its SHA-256 fingerprint,
anchors **only the fingerprint** on an Ethereum-compatible blockchain (Solidity smart contract), scores the file with an
**explainable risk engine**, runs a **multi-reviewer approval workflow**, and lets **anyone** verify authenticity from an
ID, a QR code, or the file itself. Tampering, outdated versions, revocations and duplicates are all detected and explained.

| Layer | Technology |
|---|---|
| Backend | Python 3.11–3.13, **FastAPI**, SQLAlchemy 2, Pydantic 2, JWT, WebSockets |
| Blockchain | **Solidity 0.8** contract (`contracts/ProofPulse.sol`), **Web3.py 7**, in-process EVM (eth-tester / py-evm) or any JSON-RPC node |
| Database | SQLite by default (PostgreSQL via `DATABASE_URL`) |
| Frontend | **React 18 + Vite**, Framer Motion, Recharts, dark/light theme, mobile-first |
| Reports | ReportLab (PDF certificates), `qrcode` (QR), `jsQR` (in-browser QR scanning) |

---

## 1. What is implemented (and what is optional)

Everything in the "Implemented" column is working code covered by the tests or the browser run-through, not a mock-up.

| Feature | Status | Where |
|---|---|---|
| File fingerprinting (SHA-256), local hashing in the browser for verification | Implemented | `services/registry.py`, `frontend/src/api.js` |
| Smart contract: register, versions, approvals, revoke, first-registrant evidence | Implemented, covered by contract tests | `contracts/ProofPulse.sol` |
| Web3.py integration, embedded **persistent** chain (journal replay with original block timestamps), RPC mode | Implemented | `services/blockchain.py` |
| Ownership, timestamps, version history on chain | Implemented | contract + `/api/records/*` |
| Tamper detection: by ID + file, by hash only, by file only (prior-art lookup), server-side integrity scan, DB↔chain consistency | Implemented | `routers/verify.py`, `routers/admin.py` |
| Verification by unique ID, QR code (camera or image upload), file | Implemented | `pages/Verify.jsx`, `components/QrScanner.jsx` |
| Explainable risk engine (noisy-OR over a dozen signals, each with weight and "why it matters") | Implemented | `services/risk.py`, `analysis.py` |
| Duplicate / near-duplicate detection (MinHash on text, dHash on images, exact hash) | Implemented | `services/similarity.py` |
| Multi-user approval workflow (request, approve/reject with comment, decision recorded on chain) | Implemented | `routers/approvals.py` |
| Explainable trust score (6 components, 0–100) | Implemented | `services/trust.py` |
| Hash-chained, searchable, exportable audit trail with integrity check | Implemented | `services/audit.py`, `routers/audit.py` |
| PDF verification certificates with QR | Implemented | `services/certificate.py` |
| Admin dashboard: users, all records, charts, chain status, global integrity scan | Implemented | `pages/Admin.jsx` |
| Live updates + notifications (WebSocket, toasts, bell) | Implemented | `services/events.py`, `context.jsx` |
| Auth: bcrypt hashing, JWT, lockout after repeated failures, rate limiting, input validation, security headers | Implemented | `security.py` |
| Privacy: no documents on chain, salted pseudonymous actor IDs, optional AES (Fernet) encrypted copy, private-by-default visibility | Implemented | see §6 |
| Public testnet (Sepolia) deployment | **Supported by configuration, not exercised here** | §8 |
| Hardhat local node (`npm run node`) | **Supported, not exercised here** — the embedded chain was used for all tests | §8 |
| E-mail verification, password reset by e-mail, refresh tokens, OAuth/SSO, IPFS storage | **Not implemented** (optional extensions) | §10 |

### Honest design notes (good to mention in the viva)
* **Custodial registrar model.** Users log in with ordinary accounts; the backend holds one *registrar* key and submits transactions on their behalf. The chain records a **salted-hash pseudonym** of the user id, so identities are not on the chain. Users do not sign with their own wallets.
* **The chain is the source of truth.** Verification reads the contract directly; if the database disagrees with the chain, the verdict is *Database does not match the chain*.
* **Embedded chain persistence.** The in-process EVM replays `backend/data/chain_journal.jsonl` at start-up, forcing the original block timestamps, and checks that every transaction hash matches. Only **one backend process per data folder** is allowed (a guard refuses otherwise). For multi-process or public use, switch to `BLOCKCHAIN_MODE=rpc`.
* The risk and trust engines are **rule-based and transparent** (deterministic, reproducible by hand) — "AI" here means explainable analytics, not an opaque model.

---

## 2. Architecture

```
React SPA ──HTTP/JSON + WebSocket──▶ FastAPI ──▶ SQLAlchemy ──▶ SQLite/PostgreSQL   (accounts, metadata, audit log)
   │ hashes files locally                │
   │                                     ├──▶ Risk engine / similarity / trust scoring (Python)
   └── public verify page               └──▶ Web3.py ──▶ ProofPulse.sol  on  embedded EVM | Hardhat | Sepolia
```

Registration flow: upload → fingerprint + risk analysis → **tx** `registerRecord(id, sha256, metadataHash, ownerPseudonym)` → block timestamp stored → trust score → audit entry → notification + live event.
Verification flow: ID → read contract (`getRecord/getVersion` + event log) → compare with optional file hash → verdict
`AUTHENTIC | OUTDATED_VERSION | TAMPERED | REVOKED | NOT_FOUND | REGISTERED | ANCHOR_MISMATCH | ON_CHAIN_ONLY`.

### Folder structure
```
proofpulse/
├─ contracts/ProofPulse.sol          Solidity smart contract
├─ scripts/compile.js                solc-js compiler → backend/app/contract/ProofPulse.json (prebuilt copy included)
├─ hardhat.config.js, package.json   optional local JSON-RPC node (`npm run node`)
├─ backend/
│  ├─ app/main.py                    app, lifespan, WebSocket, security headers
│  ├─ app/config.py, database.py, models.py, schemas.py, security.py, serializers.py, utils.py
│  ├─ app/routers/                   auth, records, verify, approvals, audit, notifications, dashboard, admin
│  ├─ app/services/                  blockchain, registry, risk, analysis, similarity, trust, audit, anchor, certificate, storage, events
│  ├─ app/contract/ProofPulse.json   ABI + bytecode
│  ├─ tests/                         pytest suite (contract, API flow, chain persistence)
│  ├─ seed.py                        demo data via the REST API
│  └─ .env.example, requirements.txt
├─ frontend/src/                     main.jsx, App.jsx, api.js, context.jsx, styles.css, components/, pages/
├─ sample_data/                      files for the live demo (original, v2, tampered, plagiarised copy, CSV, report)
├─ deploy/, docker-compose.yml       Dockerfiles + nginx
└─ *.bat                             Windows helpers
```

### Database models (`backend/app/models.py`)
`User` · `Record` (public_id, owner, title, visibility, status, trust) · `RecordVersion` (sha256, metadata hash, MinHash, dHash, risk report JSON, tx hash, block, encrypted-file path) · `ApprovalRequest` · `AuditLog` (prev_hash/entry_hash chain) · `Notification` · `VerificationEvent`.

### Smart contract (`ProofPulse.sol`)
`registerRecord`, `addVersion` (append-only), `recordDecision` (one decision per approver per version), `revokeRecord`, `setRegistrar`, `transferAdmin`; views `getRecord`, `getVersion`, `verifyLatest`, `verifyAny`, `decisionOf`, `firstRecordForHash`. Only registrars may write; hashes only; custom errors; events for everything.

### API (interactive docs at http://127.0.0.1:8000/docs)
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/register` · `/api/auth/login` | Create account / sign in |
| `GET` `PUT` | `/api/auth/me` · `/api/auth/password` | Profile / change password |
| `GET` | `/api/users/search` | Find reviewers |
| `POST` | `/api/analyze` | Dry-run fingerprint + risk analysis |
| `POST` `GET` | `/api/records` | Register / list (filters: scope, q, status, category, risk, sort, page) |
| `GET` | `/api/records/{id}` · `/versions` · `/approvals` | Detail, history, reviewers |
| `POST` | `/api/records/{id}/versions` · `/revoke` · `/integrity` · `/approvals` | Add version, revoke, integrity check, request reviews |
| `GET` | `/api/records/{id}/certificate` · `/qr.png` · `/versions/{n}/file` | PDF, QR, decrypted stored copy |
| `GET` `POST` | `/api/verify/{id}` · `/file` · `/hash` | **Public** verification |
| `POST` | `/api/verify-lookup/file` · `/hash` | **Public** "who registered this file first?" |
| `GET` `POST` | `/api/approvals/inbox` · `/sent` · `/{id}/decision` | Review workflow |
| `GET` | `/api/audit` · `/actions` · `/verify-chain` · `/export.csv` | Search, filter, verify, export audit trail |
| `GET` `POST` | `/api/notifications` · `/read-all` · `/{id}/read` | Notifications |
| `GET` | `/api/dashboard` · `/api/public/stats` · `/api/health` | Dashboards / status |
| `GET` `PATCH` `POST` | `/api/admin/overview` · `/users` · `/users/{id}` · `/records` · `/chain` · `/integrity-scan` · `/reanchor` | Admin |
| `WS` | `/ws?token=…` | Live events |

---

## 3. Install and run locally on Windows (step by step)

**Prerequisites:** [Python 3.11, 3.12 or 3.13](https://www.python.org/downloads/windows/) (**not 3.14**; tick *Add python.exe to PATH* and keep the py launcher), [Node.js 18+](https://nodejs.org/). Verify in PowerShell: `python --version`, `node --version`.

**One-time setup** — double-click `setup_windows.bat` (or run these in PowerShell inside the project folder):
```powershell
cd backend
py -3.13 -m venv .venv      # or py -3.12 / py -3.11
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
cd ..\frontend
npm install
```

**Run (two terminals):**
```powershell
# Terminal 1 — API + blockchain      (or double-click start_backend.bat)
cd backend
.venv\Scripts\activate
python -m uvicorn app.main:app --port 8000

# Terminal 2 — web app               (or double-click start_frontend.bat)
cd frontend
npm run dev
```
Open **http://localhost:5173**. The first start takes a few seconds while the EVM boots and the contract is deployed.

**Load the demo data** (API must be running; or double-click `seed_demo.bat`):
```powershell
cd backend
.venv\Scripts\activate
python seed.py
```

| Account | Password | Role |
|---|---|---|
| `priya` | `Demo@12345!` | student, owns the "hero" paper |
| `rahul` | `Demo@12345!` | student (use him to register the plagiarised copy) |
| `meera` | `Demo@12345!` | faculty reviewer |
| `admin` | `Admin@12345!` (change via `ADMIN_PASSWORD`) | administrator |

**Run the tests:** `run_tests.bat` or `cd backend && python -m pytest -q` (31 tests: contract rules, full API flows, tamper/revoke/approval scenarios, chain persistence).

**Recompile the contract** (optional, a compiled copy is included): `npm install` then `npm run compile` in the project root.

**Reset everything:** stop the backend and delete `backend/data/`.

---

## 4. Demonstrating every major feature (viva script, ~10 minutes)

Sample files are in `sample_data/`. Keep two browser windows: one signed in, one in a private window (public verifier).

1. **Register + fingerprint + blockchain.** Sign in as `priya` → *Register file* → choose any file of your own (the sample files are already seeded; to register a sample fresh, delete `backend/data/` and skip `seed_demo.bat`). Show the SHA-256, the *Anchored on the blockchain* screen (block number, tx hash, **QR code**).
2. **Risk engine + duplicate warning.** Sign out, sign in as `rahul` → *Register file* → `plagiarised_copy_of_paper.txt`. The pre-check shows **MEDIUM risk (≈36/100)**: the content is ≈80 % similar to another account's record (the seeded hero paper), with the signal's *why it matters* text and the matching record. An *identical* copy of someone else's file scores higher (HIGH). (Privacy: private records of other users are not revealed.)
3. **Versioning.** As `priya`, open the hero paper → *Add version* → `research_paper_v2.txt` ("Added evaluation section"). *Versions* tab shows both with hashes/tx; *Blockchain proof* shows on-chain history.
4. **Multi-user approval.** *Request approvals* → pick `meera`. Sign in as `meera` (second window): live toast + bell notification → *Approvals* → *Approve* with a comment. Back in priya's window the status and trust score update **live**; the decision shows as an on-chain event.
5. **Public verification — authentic / outdated / tampered.** Private window → *Verify* → paste the ID. Drop `research_paper_v2.txt` → **Authentic**; `research_paper_v1.txt` → **Authentic but outdated**; `research_paper_v1_TAMPERED.txt` (one changed number) → **Tampered**. Point out "hashed locally, never uploaded".
6. **QR.** On the record page scan the QR with a phone (or use *Scan QR → upload QR image* on the Verify page).
7. **File-only lookup.** *Verify → I only have the file* → drop any registered file: shows who registered it first and when.
8. **Certificate.** *Certificate (PDF)* button → PDF with ID, hashes, tx, approvals, trust score and QR.
9. **Trust score.** Record overview → six-component breakdown that sums to the score.
10. **Audit trail.** *Audit trail* → search by user/action/tx, expand a row, *Verify log integrity* (green), *Export CSV*. Optional: edit one row in `backend/data/proofpulse.db` (e.g. with DB Browser for SQLite), click verify again → **red, with the broken entry number**.
11. **Integrity scan / storage tampering.** Admin → *Integrity* → *Scan all records*. (Optional: change a byte of a `.bin` file in `backend/data/files/` → rescan reports "Stored file no longer matches its fingerprint" and the trust score drops.)
12. **Revocation.** Owner → *Revoke* with a reason → public page now shows **Revoked**.
13. **Admin dashboard.** Sign in as `admin`: charts, verification outcomes, highest-risk records, chain node status (persistent, block height), user management (disable/promote).
14. **Persistence.** Stop and restart the backend: records, timestamps and tx hashes are unchanged (journal replay). Mention the `chain_journal.jsonl`.
15. **Dark/light mode and mobile.** Toggle the theme; resize the browser — the layout switches to a bottom navigation bar.

---

## 5. Risk engine and trust score (how they work)

**Risk (0–100).** Each signal has a weight *w* in [0, 0.95]. Combined with a noisy-OR: `score = 1 − Π(1 − wᵢ)`. Weak independent signals accumulate; one strong signal dominates. Levels: LOW < 25 ≤ MEDIUM < 55 ≤ HIGH.
Signals include: identical file by another account, same text in a different file, near-duplicate / partial overlap (MinHash Jaccard on word shingles; perceptual dHash for images), self-duplicates, extension ≠ real file type (magic bytes), executables/macros/embedded scripts, double extensions, high entropy (packed/encrypted payloads), hidden/invisible Unicode, mixed-script homoglyphs, impossible/future metadata dates, re-registering revoked content, and burst registration.

**Trust (0–100)** = anchoring 20 + integrity history 20 + peer approvals 25 + inverse content risk 20 + provenance depth 10 + owner reputation 5. Each component states its reason in the UI.

## 6. Security and privacy

* **No documents on the blockchain** — only SHA-256 fingerprints, a metadata hash, comment/reason hashes and salted pseudonymous actor IDs.
* Optional encrypted copy (Fernet/AES-128-CBC + HMAC) at rest; "fingerprint only" mode keeps nothing. Titles/owners are shown publicly only for records marked *Public*.
* Passwords hashed (never stored plain); policy ≥10 chars with upper/lower/digit/symbol; lockout after 5 failures; per-endpoint rate limits; generic login errors with constant-time handling.
* All input validated (Pydantic + explicit checks), upload size limit, sanitised filenames, CSV export neutralises formula injection, security headers, CORS allow-list, no secrets in the repo (use `.env`).
* Private records of other users are invisible (404), even in similarity warnings.
* **Before real use:** set `SECRET_KEY`, `PSEUDONYM_SALT`, `ADMIN_PASSWORD`, `FILE_ENCRYPTION_KEY`, serve over HTTPS, hide the demo-account buttons (`VITE_SHOW_DEMO=false`).

## 7. Configuration

All settings are in `backend/.env` (see `.env.example`): secrets, CORS, `PUBLIC_BASE_URL` (embedded in QR codes — set it to your public address so phones can open the verification page), database URL, upload limit, blockchain mode and RPC/key/contract.

## 8. Using a real node or testnet (optional integrations)

**Hardhat local node** (separate JSON-RPC process, survives backend restarts):
```powershell
npm install            # in project root
npm run node           # leave running; prints funded accounts
# backend/.env
BLOCKCHAIN_MODE=rpc
RPC_URL=http://127.0.0.1:8545
```
The backend deploys the contract on first start and remembers the address in `backend/data/contract_address.txt`.

**Sepolia testnet:** create an RPC URL (Alchemy/Infura), a throw-away wallet funded from a Sepolia faucet, then set `BLOCKCHAIN_MODE=rpc`, `RPC_URL=…`, `CHAIN_PRIVATE_KEY=0x…`. Optionally set `CONTRACT_ADDRESS` to reuse a deployed contract. Verification pages then show `rpc:11155111` and tx hashes can be pasted into Sepolia Etherscan. *(These two paths use the same code as the tested embedded mode but were not run against a live node in development.)*

## 9. Deployment

**Docker:** create `.env` next to `docker-compose.yml` with `SECRET_KEY`, `PSEUDONYM_SALT`, `ADMIN_PASSWORD` (and `PUBLIC_BASE_URL`), then `docker compose up --build` → http://localhost:8080 (nginx serves the SPA and proxies `/api` and `/ws`). Data lives in the `pp-data` volume. Keep **one** backend replica in embedded mode.
**Manual VPS:** `npm run build` in `frontend/`, serve `dist/` with nginx (see `deploy/nginx.conf`), run `uvicorn app.main:app` under systemd/pm2 behind HTTPS (Let's Encrypt). For a production-grade chain use `BLOCKCHAIN_MODE=rpc` with Sepolia (or any EVM network) and PostgreSQL.

## 10. Known limitations and extension ideas
Custodial signing (user wallets/MetaMask signing would remove the trust in the registrar) · no e-mail verification / password reset / refresh tokens · SQLite + `create_all` (add Alembic for migrations) · similarity compares against all records in memory (fine for thousands, use an index/LSH beyond that) · text extraction supports txt/csv/json/md/code/PDF/DOCX · optional IPFS storage and anchoring audit-log heads on chain are natural next steps.

## 11. Troubleshooting
| Symptom | Fix |
|---|---|
| `pip` fails with "Microsoft Visual C++ 14.0 is required" / "failed building wheel" | You are on an unsupported Python (3.14). Install Python 3.13 and re-run `setup_windows.bat`; it deletes an old `.venv` and picks 3.13/3.12/3.11 automatically. |
| `python` / `py` / `node` is not recognised | Reinstall Python (tick *Add to PATH*) or Node.js LTS, then open a **new** terminal. |
| Web page shows "Cannot reach the ProofPulse server" | `start_backend.bat` must be running (first start takes ~10 s). Check http://127.0.0.1:8000/api/health. |
| "The embedded chain journal was changed by another process" | Two backends use the same `backend/data` folder. Close the extra one. |
| Port 8000 or 5173 already in use | Close the old window, or start on another port (`--port 8001`, and `VITE_BACKEND=http://127.0.0.1:8001` for the frontend). |
| Want a clean slate | Stop the backend, delete `backend\data`, start again, run `seed_demo.bat`. |
