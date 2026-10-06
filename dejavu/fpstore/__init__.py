"""
Compact fingerprint store, used by the "postgres_compact" database type.

The fingerprints table keeps one ~70 byte row per fingerprint, and a recognition fetches every row of every
query hash. This store packs the same fingerprints into per-song and per-hash blobs of 2 to 3 bytes per
fingerprint, and searches the rarest hashes first instead of fetching them all. See store.py.
"""
from dejavu.fpstore.store import FpStore

__all__ = ["FpStore"]
