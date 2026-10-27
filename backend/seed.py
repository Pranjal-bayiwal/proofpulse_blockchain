"""Populate a RUNNING ProofPulse backend with demo users and records, through the public REST API.

    python seed.py [--api http://127.0.0.1:8000]

Creates three demo users (password Demo@12345!) and registers real files from ../sample_data, with approvals,
so every screen has data. It talks to the server over HTTP, exactly like the web app does, so it works with
both the embedded chain and an external node. Safe to run twice (it stops if 'priya' already owns records).

Files left unregistered on purpose for the live demo: research_paper_v2.txt, research_paper_v1_TAMPERED.txt,
plagiarised_copy_of_paper.txt.
"""
import argparse
import random
import sys
import time
from pathlib import Path

import httpx

DATA = Path(__file__).resolve().parent.parent / "sample_data"
DEMO_PASSWORD = "Demo@12345!"


def filler(seed: int) -> bytes:
    rng = random.Random(seed)
    words = ("sensor model dataset analysis method thesis experiment result campus energy network protocol learning "
             "survey interview framework prototype evaluation benchmark algorithm hypothesis variable control sample").split()
    sentences = [" ".join(rng.choice(words) for _ in range(rng.randint(9, 15))).capitalize() + "." for _ in range(40)]
    return "\n".join(sentences).encode()


class Api:
    def __init__(self, base: str):
        self.c = httpx.Client(base_url=base, timeout=60)

    def ensure_user(self, username: str, full_name: str, org: str) -> dict:
        body = {"username": username, "email": f"{username}@proofpulse.demo", "full_name": full_name,
                "organization": org, "password": DEMO_PASSWORD}
        r = self.c.post("/api/auth/register", json=body)
        if r.status_code == 409:
            r = self.c.post("/api/auth/login", json={"identifier": username, "password": DEMO_PASSWORD})
        r.raise_for_status()
        j = r.json()
        return {"h": {"Authorization": f"Bearer {j['token']}"}, "user": j["user"]}

    def register(self, who, name, data, *, title, description, category, visibility, store, tags=()):
        r = self.c.post("/api/records", headers=who["h"], data={
            "title": title, "description": description, "category": category, "visibility": visibility,
            "store_file": "true" if store else "false", "tags": ",".join(tags)}, files={"file": (name, data, "text/plain")})
        r.raise_for_status()
        return r.json()

    def request(self, who, rec, approvers):
        self.c.post(f"/api/records/{rec['public_id']}/approvals", headers=who["h"], json={"approvers": list(approvers)}).raise_for_status()

    def decide(self, who, rec, approve, comment):
        inbox = self.c.get("/api/approvals/inbox", headers=who["h"]).json()
        item = next(a for a in inbox if a["record_public_id"] == rec["public_id"])
        self.c.post(f"/api/approvals/{item['id']}/decision", headers=who["h"], json={"approve": approve, "comment": comment}).raise_for_status()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    api = Api(args.api)
    for _ in range(30):
        try:
            if api.c.get("/api/health").json().get("blockchain", {}).get("connected"):
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        print(f"Cannot reach a healthy ProofPulse backend at {args.api}. Start it first (see README).")
        return 1

    priya = api.ensure_user("priya", "Priya Sharma", "CSE, Final Year")
    rahul = api.ensure_user("rahul", "Rahul Verma", "CSE, Final Year")
    meera = api.ensure_user("meera", "Dr. Meera Iyer", "Faculty Supervisor")
    
    records_response = api.c.get("/api/records", headers=priya["h"])
    print("Records API status:", records_response.status_code)
    print("Records API response:", records_response.text)
    auth_check = api.c.get("/api/auth/me", headers=priya["h"])
    print("Priya authentication status:", auth_check.status_code)
    print("Priya authentication response:", auth_check.text)
    records_response.raise_for_status()
    records_data = records_response.json()

    if records_data.get("total", 0):
        print("Already seeded (priya already owns records). Nothing to do.")
        return 0


    paper = api.register(priya, "research_paper_v1.txt", (DATA / "research_paper_v1.txt").read_bytes(),
                         title="Anchoring Document Fingerprints on a Public Ledger",
                         description="Research paper proposing a lightweight provenance model.",
                         category="research", visibility="public", store=True, tags=["blockchain", "provenance", "research"])
    api.request(priya, paper, ["meera", "rahul"])
    api.decide(meera, paper, True, "Methodology is sound. Approved.")

    dataset = api.register(priya, "lab_dataset.csv", (DATA / "lab_dataset.csv").read_bytes(), title="Lab sensor readings, September",
                           description="Raw sensor export.", category="dataset", visibility="public", store=False,
                           tags=["dataset", "sensors"])
    api.request(priya, dataset, ["meera"])
    api.decide(meera, dataset, True, "Dataset verified against lab notebook.")

    report = api.register(rahul, "project_report.txt", (DATA / "project_report.txt").read_bytes(),
                          title="Smart Campus Energy Monitor: Final Report", description="Final project report.",
                          category="project", visibility="public", store=False, tags=["iot", "energy"])
    api.request(rahul, report, ["meera", "priya"])
    api.decide(meera, report, True, "Good work.")
    api.decide(priya, report, True, "Reviewed. Looks correct.")

    for i, (who, title, cat) in enumerate([(rahul, "Draft survey instrument", "document"),
                                           (meera, "Lecture notes: Distributed Systems", "document"),
                                           (priya, "Experiment log week 3", "research")]):
        api.register(who, f"notes_{i}.txt", filler(100 + i), title=title, description="Seeded sample.", category=cat,
                     visibility="private" if i == 0 else "public", store=False)

    print("\nSeeded demo data. Accounts (password: %s):" % DEMO_PASSWORD)
    print("  priya  (student)     rahul  (student)     meera  (faculty approver)")
    print("  admin / Admin@12345!  (administrator, created on first server start)")
    print(f"\nHero record: {paper['public_id']}  ({paper['title']})")
    print("Unregistered demo files are in ../sample_data (v2, TAMPERED, plagiarised copy).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
