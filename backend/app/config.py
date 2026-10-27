from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    app_name: str = "ProofPulse"

    # Security
    secret_key: str = "dev-only-secret-change-me-before-any-real-deployment-0123456789"
    pseudonym_salt: str = "dev-only-pseudonym-salt-change-me"
    access_token_minutes: int = 60
    max_failed_logins: int = 5
    lockout_minutes: int = 5
    rate_limit_enabled: bool = True

    # Storage
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'proofpulse.db'}"
    storage_dir: str = str(BASE_DIR / "data" / "files")
    file_encryption_key: str = ""  # Fernet key; auto-generated to data/fernet.key if empty
    max_upload_mb: int = 25

    # Web
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    public_base_url: str = "http://localhost:5173"

    # Blockchain
    blockchain_mode: str = "embedded"  # "embedded" (in-process EVM) or "rpc" (Hardhat/Ganache/testnet)
    rpc_url: str = "http://127.0.0.1:8545"
    chain_private_key: str = ""  # optional; required for public testnets
    contract_address: str = ""
    auto_reanchor: bool = True  # replay DB records onto a fresh local chain
    # Embedded mode only: append-only transaction journal. On restart the chain is rebuilt by replaying it
    # with the ORIGINAL block timestamps, so the embedded chain behaves like a persistent one.
    chain_journal: str = str(BASE_DIR / "data" / "chain_journal.jsonl")  # empty string disables persistence

    # Seed admin
    admin_username: str = "admin"
    admin_email: str = "admin@proofpulse.local"
    admin_password: str = "Admin@12345!"
    admin_full_name: str = "ProofPulse Administrator"

    # Analysis
    near_duplicate_threshold: float = 0.80
    partial_overlap_threshold: float = 0.50

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
