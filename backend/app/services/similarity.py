"""Duplicate / near-duplicate detection.

Text   : normalised word 5-shingles -> 128-permutation MinHash. Jaccard ≈ fraction of equal slots.
Images : 64-bit difference hash (dHash). Similarity = 1 - hamming/64.
Both fingerprints are stored instead of the document text, so the platform can compare
files without retaining their content.
"""
import hashlib
import io

import numpy as np

from .analysis import normalise_text

NUM_PERM = 128
SHINGLE = 5
_rng = np.random.default_rng(20260101)
_A = _rng.integers(1, 2**63 - 1, size=NUM_PERM, dtype=np.uint64) | np.uint64(1)
_B = _rng.integers(0, 2**63 - 1, size=NUM_PERM, dtype=np.uint64)


def text_hash(text: str) -> str | None:
    norm = normalise_text(text)
    if len(norm) < 20:
        return None
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def minhash(text: str) -> list[int] | None:
    norm = normalise_text(text)
    words = norm.split()
    if len(norm) < 40 or len(words) < 8:
        return None
    if len(words) < SHINGLE:
        shingles = {" ".join(words)}
    else:
        shingles = {" ".join(words[i : i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}
    hashes = np.fromiter(
        (int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big") for s in shingles),
        dtype=np.uint64,
        count=len(shingles),
    )
    sig = np.full(NUM_PERM, np.iinfo(np.uint64).max, dtype=np.uint64)
    with np.errstate(over="ignore"):
        for start in range(0, len(hashes), 4096):
            chunk = hashes[start : start + 4096]
            vals = chunk[:, None] * _A[None, :] + _B[None, :]
            sig = np.minimum(sig, vals.min(axis=0))
    return [int(x) for x in sig]


def jaccard(sig_a: list[int] | None, sig_b: list[int] | None) -> float:
    if not sig_a or not sig_b or len(sig_a) != len(sig_b):
        return 0.0
    a = np.array(sig_a, dtype=np.uint64)
    b = np.array(sig_b, dtype=np.uint64)
    return float(np.mean(a == b))


def dhash(data: bytes) -> str | None:
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("L").resize((9, 8), Image.LANCZOS)
        px = np.asarray(img, dtype=np.int16)
        bits = (px[:, 1:] > px[:, :-1]).flatten()
        value = 0
        for bit in bits:
            value = (value << 1) | int(bit)
        return f"{value:016x}"
    except Exception:
        return None


def dhash_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return 1 - bin(int(a, 16) ^ int(b, 16)).count("1") / 64
