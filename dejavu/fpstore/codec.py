"""
Posting-list codec shared by song_fp and fp_postings.

A blob holds n (key, value) pairs: keys uint32 (hash32 or song_id), values uint16 offsets.
Pairs are sorted by (key, value), keys are delta-encoded, each array is byte-shuffled
(all low bytes, then the next bytes, ...) so the mostly-zero high bytes compress well,
then raw-deflated with stdlib zlib. Blobs that deflate would not shrink are stored raw.
The first byte of a blob names the codec. Decoding is two numpy calls.
"""
import zlib

import numpy as np

RAW, DEFLATE = 0, 1
LEVEL = 6


def _shuffle(a: np.ndarray) -> bytes:
    return np.ascontiguousarray(a.view(np.uint8).reshape(len(a), a.itemsize).T).tobytes()


def _unshuffle(b: bytes, dtype, n: int) -> np.ndarray:
    w = np.dtype(dtype).itemsize
    return np.ascontiguousarray(np.frombuffer(b, np.uint8).reshape(w, n).T).view(dtype).ravel()


def encode(keys: np.ndarray, vals: np.ndarray, level: int = LEVEL, presorted: bool = False) -> bytes:
    if not presorted:
        order = np.lexsort((vals, keys))
        keys, vals = keys[order], vals[order]
    k = np.ascontiguousarray(keys, dtype=np.uint32)
    d = np.diff(k, prepend=np.uint32(0))
    payload = _shuffle(d) + _shuffle(np.ascontiguousarray(vals, dtype=np.uint16))
    c = zlib.compressobj(level, zlib.DEFLATED, -15)
    z = c.compress(payload) + c.flush()
    return bytes([DEFLATE]) + z if len(z) < len(payload) else bytes([RAW]) + payload


def decode(blob: bytes, n: int):
    """-> (keys uint32 ascending, vals uint16), both length n.

    blob may be bytes or the memoryview psycopg2 returns for bytea; indexing that view yields 1-byte
    bytes objects, so it is cast to unsigned bytes first.
    """
    mv = memoryview(blob).cast("B")
    payload = zlib.decompress(mv[1:], -15) if mv[0] == DEFLATE else mv[1:]
    assert len(payload) == 6 * n, "blob length does not match n"
    keys = np.cumsum(_unshuffle(payload[:4 * n], np.uint32, n), dtype=np.uint32)
    return keys, _unshuffle(payload[4 * n:], np.uint16, n)
