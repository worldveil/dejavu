"""
Tests for the compact fingerprint store and the numpy align_matches. No database needed: the store's
search runs against a synthetic catalogue served through an in-memory cursor.

usage:
  python -m dejavu.tests.test_fpstore
"""
import hashlib
import sys
from contextlib import contextmanager
from itertools import groupby

import numpy as np

from dejavu import Dejavu
from dejavu.config.settings import (FINGERPRINT_REDUCTION, HASHES_MATCHED,
                                    OFFSET, SONG_ID)
from dejavu.fpstore import FpStore, codec
from dejavu.fpstore.store import best_per_song, top_offsets
from dejavu.logic.fingerprint import fingerprint, fingerprint_hash32

BLOCK_FRAMES = 431
PART = 50


class FakeCursor:
    """Answers the store's search statements from dicts, the way psycopg2 returns them."""
    def __init__(self, db):
        self.db, self.rows = db, []

    def execute(self, sql, params=None):
        if "FROM fp_gen" in sql:
            self.rows = [(0, BLOCK_FRAMES, PART)]
        elif "FROM fp_df" in sql:
            self.rows = [(h, self.db["df"][h]) for h in params[0] if h in self.db["df"]]
        # blobs come back as psycopg2 returns bytea: a memoryview whose items are 1-byte bytes
        elif "FROM fp_postings" in sql:
            self.rows = [(h, n, memoryview(b).cast("c")) for hh in params[0] for h, n, b in self.db["postings"].get(hh, [])]
        elif "FROM song_fp" in sql:
            self.rows = [(s, n, memoryview(b).cast("c")) for s, n, b in
                         (self.db["song_fp"][k] for k in zip(params[0], params[1]) if k in self.db["song_fp"])]
        elif 'FROM "songs"' in sql:
            self.rows = [self.db["songs"][s] for s in params[0] if s in self.db["songs"]]
        else:
            raise AssertionError(sql)

    def fetchall(self):
        return self.rows


def build_catalogue(rng, n_songs=30, per_song=6000, frames=4000):
    h, s, o = [], [], []
    for song in range(1, n_songs + 1):
        f1, f2, dt = rng.integers(0, 2049, per_song), rng.integers(0, 2049, per_song), rng.integers(1, 200, per_song)
        common = rng.random(per_song) < 0.05
        f1[common], f2[common], dt[common] = 5, 6, 7                   # one very frequent hash
        h.append((f1.astype(np.uint32) << 20) | (f2.astype(np.uint32) << 8) | dt.astype(np.uint32))
        s.append(np.full(per_song, song, np.uint32))
        o.append(rng.integers(0, frames, per_song).astype(np.uint16))
    h, s, o = np.concatenate(h), np.concatenate(s), np.concatenate(o)
    key = np.unique(h.astype(np.uint64) << np.uint64(32) | s.astype(np.uint64) << np.uint64(16) | o)
    h = (key >> np.uint64(32)).astype(np.uint32)
    s = ((key >> np.uint64(16)) & np.uint64(0xFFFF)).astype(np.uint32)
    o = (key & np.uint64(0xFFFF)).astype(np.uint16)

    postings, df = {}, {}
    uh, start, cnt = np.unique(h, return_index=True, return_counts=True)
    for hh, st, n in zip(uh.tolist(), start.tolist(), cnt.tolist()):
        hi = int(np.uint32(hh).view(np.int32))
        df[hi] = n
        postings[hi] = [(hi, min(PART, st + n - p), codec.encode(s[p:min(p + PART, st + n)], o[p:min(p + PART, st + n)],
                                                                 presorted=True))
                        for p in range(st, st + n, PART)]
    song_fp = {}
    blocks = o // BLOCK_FRAMES
    for song in np.unique(s).tolist():
        for b in np.unique(blocks[s == song]).tolist():
            m = (s == song) & (blocks == b)
            song_fp[(song, b)] = (song, int(m.sum()), codec.encode(h[m], o[m]))
    songs = {sid: (sid, f"song {sid}", "AB" * 20, int((s == sid).sum())) for sid in np.unique(s).tolist()}
    return h, s, o, {"postings": postings, "df": df, "song_fp": song_fp, "songs": songs}


def search_checks(rng):
    h, s, o, db = build_catalogue(rng)

    @contextmanager
    def cursor():
        yield FakeCursor(db)

    store = FpStore(cursor, stop_df=1000, stages=(300, 1500, None), min_votes=10, margin=2.0, topn=5)

    # query: song 7 between frames 1000 and 1300, shifted to start at 0, one hash repeated at a second offset, plus noise
    true_song, true_diff = 7, 1000
    m = (s == true_song) & (o >= 1000) & (o < 1300)
    q_h = h[m]
    q_o = o[m].astype(np.int64) - true_diff
    q_h = np.concatenate([q_h, q_h[:1], rng.integers(0, 2 ** 32, 400, dtype=np.uint64).astype(np.uint32)])
    q_o = np.concatenate([q_o, q_o[:1] + 3, rng.integers(0, 300, 400)])
    results, stats = store.search(q_h, q_o)
    # the same query as if the true song were not in the catalogue
    absent, _ = store.search(q_h, q_o, exclude_songs=[true_song])

    # brute force: votes over every query pair and every posting, no budget
    votes = {}
    for hh, oo in zip(q_h.tolist(), q_o.tolist()):
        for ss, pp in zip(s[h == hh].tolist(), o[h == hh].tolist()):
            votes[(ss, pp - oo)] = votes.get((ss, pp - oo), 0) + 1
    best = max(votes.items(), key=lambda kv: kv[1])
    exact_true = int(m.sum())

    print(f"     search stats: {stats}")
    return {
        "top song is the true song": bool(results) and results[0][SONG_ID] == true_song,
        "offset difference is exact": bool(results) and results[0][OFFSET] == true_diff,
        "verified count equals the song's aligned pairs": bool(results) and results[0][HASHES_MATCHED] >= exact_true,
        "brute force agrees": best[0] == (true_song, true_diff),
        "stopped before fetching everything": stats["stage"] < 3,
        "excluded song never returned": all(r[SONG_ID] != true_song for r in absent),
        "best wrong song scores far below the true song":
            not absent or absent[0][HASHES_MATCHED] * 5 < results[0][HASHES_MATCHED],
        "empty query returns nothing": store.search(np.empty(0, np.uint32), np.empty(0, np.int64))[0] == [],
        # ties keep ascending song_id, as Dejavu.align_matches does
        "best_per_song breaks ties by song_id": best_per_song(np.array([1, 1, 2, 2, 2]), np.array([5, 5, 9, 9, 1]), 2)
                                                == [(1, 5, 2), (2, 9, 2)],
        "best_per_song ranks by votes": best_per_song(np.array([1, 2, 2, 2, 3]), np.array([4, 9, 9, 9, 0]), 3)
                                        == [(2, 9, 3), (1, 4, 1), (3, 0, 1)],
        # ties keep the smaller offset
        "top_offsets keeps each song's best offsets": top_offsets(np.array([1, 1, 1, 2, 1]),
                                                                  np.array([5, 5, 9, 3, 7]), [1], 2)
                                                      == [(1, 5, 2), (1, 7, 1)],
    }


def codec_checks(rng):
    keys = rng.integers(0, 2 ** 32, 5000, dtype=np.uint64).astype(np.uint32)
    vals = rng.integers(0, 2 ** 16, 5000).astype(np.uint16)
    k, v = codec.decode(memoryview(codec.encode(keys, vals)).cast("c"), len(keys))
    order = np.lexsort((vals, keys))
    rand = codec.encode(rng.integers(0, 2 ** 32, 3, dtype=np.uint64).astype(np.uint32),
                        rng.integers(0, 2 ** 16, 3).astype(np.uint16))
    return {
        "codec round trip": np.array_equal(k, keys[order]) and np.array_equal(v, vals[order]),
        "codec stores incompressible blobs raw": rand[0] == codec.RAW and len(rand) == 1 + 6 * 3,
    }


def hash32_checks(rng):
    fs = 44100
    t = np.arange(8 * fs) / fs
    tones = sum(np.sin(2 * np.pi * f * t) * (t % p < p / 2) for f, p in ((440, 0.5), (1250, 0.7), (3100, 0.3)))
    samples = (8000 * tones + 300 * rng.standard_normal(len(t))).astype(np.int16)

    sha1 = set(fingerprint(samples, Fs=fs))
    h32, offsets = fingerprint_hash32(samples, Fs=fs)
    f1, f2, dt = h32 >> 20, (h32 >> 8) & 0xFFF, h32 & 0xFF
    packed = {(hashlib.sha1(f"{a}|{b}|{c}".encode("utf-8")).hexdigest()[0:FINGERPRINT_REDUCTION], int(off))
              for a, b, c, off in zip(f1.tolist(), f2.tolist(), dt.tolist(), offsets.tolist())}
    print(f"     {len(sha1)} sha1 fingerprints, {len(set(zip(h32.tolist(), offsets.tolist())))} hash32 fingerprints")
    return {"fingerprint_hash32 finds the same pairs as fingerprint": len(sha1) > 1000 and packed == sha1}


def align_checks(rng):
    class FakeDB:
        @staticmethod
        def get_song_by_id(song_id):
            return {"song_name": f"song {song_id}", "total_hashes": 1000, "file_sha1": "AB" * 20}

    def groupby_order(matches, topn):
        # the pure Python version align_matches replaced
        sorted_matches = sorted(matches, key=lambda m: (m[0], m[1]))
        counts = [(*key, len(list(group))) for key, group in groupby(sorted_matches, key=lambda m: (m[0], m[1]))]
        return sorted(
            [max(list(group), key=lambda g: g[2]) for key, group in groupby(counts, key=lambda count: count[0])],
            key=lambda count: count[2], reverse=True
        )[:topn]

    djv = Dejavu.__new__(Dejavu)                         # no database: align_matches only reads song rows
    djv.db = FakeDB()
    ok = True
    for _ in range(50):
        n = int(rng.integers(1, 3000))
        # few songs and offsets, so ties on count are frequent
        matches = list(zip(rng.integers(1, 15, n).tolist(), rng.integers(-20, 20, n).tolist()))
        dedup = {sid: 1 for sid, _ in matches}
        got = [(r[SONG_ID], r[OFFSET]) for r in djv.align_matches(matches, dedup, n, topn=10)]
        ok &= got == [(sid, off) for sid, off, _ in groupby_order(matches, 10)]
    return {"numpy align_matches equals the groupby version, ties included": ok,
            "align_matches of no matches is empty": djv.align_matches([], {}, 0) == []}


def main():
    rng = np.random.default_rng(5)
    checks = {}
    for group in (codec_checks, search_checks, hash32_checks, align_checks):
        checks.update(group(rng))
    for k, v in checks.items():
        print(f"{'ok  ' if v else 'FAIL'} {k}")
    ok = all(checks.values())
    print("FPSTORE TESTS PASSED" if ok else "FPSTORE TESTS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
