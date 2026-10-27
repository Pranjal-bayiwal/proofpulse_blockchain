import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

_tmp = tempfile.mkdtemp(prefix="proofpulse-test-")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{Path(_tmp) / 'test.db'}",
    "STORAGE_DIR": str(Path(_tmp) / "files"),
    "FILE_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "BLOCKCHAIN_MODE": "embedded",
    "CHAIN_JOURNAL": str(Path(_tmp) / "chain_journal.jsonl"),
    "RATE_LIMIT_ENABLED": "false",
    "ADMIN_PASSWORD": "Admin@12345!",
    "PUBLIC_BASE_URL": "http://localhost:5173",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSWORD = "Str0ng!Passw0rd"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _register(client, username):
    r = client.post("/api/auth/register", json={
        "username": username, "email": f"{username}@example.com", "full_name": username.title() + " Tester", "password": PASSWORD})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def alice(client):
    return _register(client, "alice")


@pytest.fixture(scope="session")
def bob(client):
    return _register(client, "bob")


@pytest.fixture(scope="session")
def carol(client):
    return _register(client, "carol")


@pytest.fixture(scope="session")
def admin(client):
    r = client.post("/api/auth/login", json={"identifier": "admin", "password": "Admin@12345!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def upload(client, headers, content: bytes, name="paper.txt", **fields):
    data = {"title": "Test document", "description": "d", "category": "research", "visibility": "public", "store_file": "false"}
    data.update(fields)
    return client.post("/api/records", headers=headers, data=data, files={"file": (name, content, "text/plain")})
