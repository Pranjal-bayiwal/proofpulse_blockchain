"""Optional encrypted-at-rest file storage. Off by default: only fingerprints are kept."""
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from ..config import BASE_DIR, get_settings

settings = get_settings()
STORAGE = Path(settings.storage_dir)
KEY_FILE = BASE_DIR / "data" / "fernet.key"


def _fernet() -> Fernet:
    key = settings.file_encryption_key.strip()
    if not key:
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not KEY_FILE.exists():
            KEY_FILE.write_bytes(Fernet.generate_key())
            try:
                KEY_FILE.chmod(0o600)
            except OSError:
                pass
        key = KEY_FILE.read_text().strip()
    return Fernet(key.encode())


def save_encrypted(data: bytes) -> str:
    STORAGE.mkdir(parents=True, exist_ok=True)
    name = secrets.token_hex(16) + ".bin"
    (STORAGE / name).write_bytes(_fernet().encrypt(data))
    return name


def load_decrypted(name: str) -> bytes | None:
    path = STORAGE / Path(name).name  # strip any path components
    if not path.exists():
        return None
    try:
        return _fernet().decrypt(path.read_bytes())
    except InvalidToken:
        return None


def delete(name: str | None) -> None:
    if name:
        (STORAGE / Path(name).name).unlink(missing_ok=True)
