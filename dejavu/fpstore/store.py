"""
The compact fingerprint store: writes songs into song_fp / fp_postings / fp_df / fp_gen, and searches them.

hash32 = (f1 << 20) | (f2 << 8) | dt is the peak pair itself, packed (fingerprint.fingerprint_hash32), so a
hash is 4 bytes and collision-free. Each row holds a codec blob of many postings instead of one row per
fingerprint: about 2.4 to 3.1 bytes per posting, against ~70 bytes per row of the fingerprints table.

  song_fp      one row per (song_id, block): the song's (hash32, offset) pairs in one time block, sorted by
               hash. A new song only ever adds rows.
  fp_postings  one row per (hash, gen, part): the hash's (song_id, offset) postings, sorted by song. A song's
               postings are appended to each hash's last part until it holds part_postings entries, then
               as further parts, so existing blobs are only ever topped up, never rewritten wholesale.
  fp_df        postings per hash.
  fp_gen       the live generation: block and part sizes, song and posting counts.

Search
  1. df lookup     posting counts of the query's distinct hashes (fp_df)
  2. staged fetch  rarest usable hashes first under a posting budget; vote on (song, offset difference);
                   stop when the top song has >= min_votes and >= margin x the runner-up
  3. verify        each top song re-scored at its best few offset differences against the song_fp blocks
                   those offsets point to, using every query hash (including ones skipped in step 2).
                   Several offsets matter for songs whose sections repeat: the rare hashes of step 2 can
                   favour a weaker repeat of the passage.

Results have the same keys as Dejavu.align_matches. HASHES_MATCHED is the verified, time-aligned match
count, where align_matches counts every fingerprint row the song returned.

Removals rewrite only the parts they touch and leave partly filled parts behind: correct, but slightly
less compact than a rebuild. The tables are fillfactor 100, so run VACUUM (ANALYZE) after a large ingest.
"""
import time
from contextlib import contextmanager
from typing import Callable, Dict, List, Sequence, Tuple

import numpy as np
from psycopg2.extras import execute_batch, execute_values

from dejavu.config.settings import (DEFAULT_FS, DEFAULT_OVERLAP_RATIO,
                                    DEFAULT_WINDOW_SIZE, FIELD_FILE_SHA1,
                                    FIELD_FINGERPRINTED, FIELD_SONG_ID,
                                    FIELD_SONGNAME, FIELD_TOTAL_HASHES,
                                    FINGERPRINTED_CONFIDENCE,
                                    FINGERPRINTED_HASHES,
                                    FPSTORE_BLOCK_SECONDS, FPSTORE_MARGIN,
                                    FPSTORE_MIN_VOTES,
                                    FPSTORE_OFFSETS_PER_SONG,
                                    FPSTORE_PART_POSTINGS, FPSTORE_STAGES,
                                    FPSTORE_STOP_DF, HASHES_MATCHED,
                                    INPUT_CONFIDENCE, INPUT_HASHES, OFFSET,
                                    OFFSET_SECS, SONG_ID, SONG_NAME,
                                    SONGS_TABLENAME, TOPN)
from dejavu.fpstore import codec, schema
from dejavu.logic.fingerprint import unique_pairs

FRAMES_PER_S = DEFAULT_FS / (DEFAULT_WINDOW_SIZE * DEFAULT_OVERLAP_RATIO)
MAX_OFFSET = 1 << 16                    # song_fp / fp_postings store offsets as uint16
MAX_BLOCK = 1 << 15                     # song_fp.block is smallint
CHUNK_HASHES = 50_000                   # hashes whose tail parts are held in memory at once
REMOVE_CHUNK = 20_000                   # hashes whose full part lists are held in memory at once
DIFF_BIAS = 1 << 16                     # offset differences are within +/- 65535 frames
KEY_SCALE = 1 << 17

SELECT_SONGS = f"""
    SELECT "{FIELD_SONG_ID}", "{FIELD_SONGNAME}", upper(encode("{FIELD_FILE_SHA1}", 'hex')), "{FIELD_TOTAL_HASHES}"
    FROM "{SONGS_TABLENAME}"
    WHERE "{FIELD_SONG_ID}" = ANY(%s::int4[])
"""

UPDATE_SONG_FINGERPRINTED = f"""
    UPDATE "{SONGS_TABLENAME}" SET
        "{FIELD_FINGERPRINTED}" = 1
    ,   "{FIELD_TOTAL_HASHES}" = %s
    ,   "date_modified" = now()
    WHERE "{FIELD_SONG_ID}" = %s
"""


def best_per_song(song: np.ndarray, diff: np.ndarray, k: int):
    """Top k songs by their best (song, offset difference) vote count: [(song, diff, votes), ...]."""
    if len(song) == 0:
        return []
    keys, counts = np.unique(song.astype(np.int64) * KEY_SCALE + (diff + DIFF_BIAS), return_counts=True)
    order = np.argsort(-counts, kind="stable")
    songs_sorted = keys[order] // KEY_SCALE
    _, first = np.unique(songs_sorted, return_index=True)
    top = order[np.sort(first)[:k]]
    return [(int(keys[i] // KEY_SCALE), int(keys[i] % KEY_SCALE) - DIFF_BIAS, int(counts[i])) for i in top]


def top_offsets(song: np.ndarray, diff: np.ndarray, song_ids, n: int):
    """The n best offset differences of each song in song_ids, by votes; ties keep the smaller offset."""
    if len(song) == 0 or not song_ids:
        return []
    mask = np.isin(song, song_ids)
    keys, counts = np.unique(song[mask].astype(np.int64) * KEY_SCALE + (diff[mask] + DIFF_BIAS), return_counts=True)
    key_songs = keys // KEY_SCALE
    out = []
    for sid in song_ids:
        sel = np.flatnonzero(key_songs == sid)
        for i in sel[np.argsort(-counts[sel], kind="stable")[:n]]:
            out.append((int(sid), int(keys[i] % KEY_SCALE) - DIFF_BIAS, int(counts[i])))
    return out


class FpStore:
    def __init__(self, cursor: Callable, stop_df: int = FPSTORE_STOP_DF, stages=FPSTORE_STAGES,
                 min_votes: int = FPSTORE_MIN_VOTES, margin: float = FPSTORE_MARGIN, topn: int = TOPN,
                 offsets_per_song: int = FPSTORE_OFFSETS_PER_SONG, chunk_hashes: int = CHUNK_HASHES):
        """
        :param cursor: cursor factory used as `with cursor() as cur:` that commits on exit, such as the
         PostgreSQL handler's. The store keeps no other state, so it sees writes from other processes.
        The other parameters tune the search, see FPSTORE_* in dejavu.config.settings.
        """
        self._cursor = cursor
        self.stop_df, self.stages, self.min_votes, self.margin, self.topn = stop_df, stages, min_votes, margin, topn
        self.offsets_per_song, self.chunk_hashes = offsets_per_song, chunk_hashes

    @contextmanager
    def _transaction(self):
        """A cursor whose work is committed on exit, or rolled back if the block raises."""
        with self._cursor() as cur:
            try:
                yield cur
            except Exception:
                cur.connection.rollback()
                raise

    # ── tables ────────────────────────────────────────────────────────────────

    def setup(self, block_s: float = FPSTORE_BLOCK_SECONDS, part_postings: int = FPSTORE_PART_POSTINGS) -> None:
        """Creates the tables and their live generation unless they exist. Block and part sizes are fixed then."""
        with self._transaction() as cur:
            # processes starting together must not both create the tables
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('dejavu.fpstore'))")
            cur.execute("SELECT to_regclass('fp_gen') IS NOT NULL")
            if cur.fetchone()[0]:
                return
            for statement in schema.CREATE_TABLES:
                cur.execute(statement)
            cur.execute(schema.INSERT_GEN, (int(round(block_s * FRAMES_PER_S)), part_postings))

    def drop(self) -> None:
        with self._transaction() as cur:
            cur.execute(schema.DROP_TABLES)

    def num_postings(self) -> int:
        with self._cursor() as cur:
            cur.execute("SELECT coalesce(sum(n_postings), 0) FROM fp_gen WHERE state = 'live'")
            return int(cur.fetchone()[0])

    @staticmethod
    def _live(cur) -> List[Tuple[int, int, int]]:
        """(gen, block_frames, part_postings) of each live generation."""
        cur.execute("SELECT gen, block_frames, part_postings FROM fp_gen WHERE state = 'live' ORDER BY gen")
        live = [(int(g), int(b), int(p)) for g, b, p in cur.fetchall()]
        if not live:
            raise RuntimeError("fp_gen has no live generation")
        return live

    def _writable_gen(self, cur) -> Tuple[int, int, int]:
        live = self._live(cur)
        if len(live) != 1:
            raise RuntimeError(f"writing needs exactly one live generation, found {len(live)}")
        return live[0]

    # ── writer ────────────────────────────────────────────────────────────────

    def add_songs(self, items: Sequence[Tuple[int, np.ndarray, np.ndarray]]) -> Dict[str, int]:
        """
        Writes songs into the live generation and flags their songs rows fingerprinted, in one transaction,
        so a song is either searchable and fingerprinted or neither.

        :param items: (song_id, hash32, offsets) per song, as fingerprint_hash32 returns them; the songs rows
         must exist. A song already in the store is refused.
        :return: counts of what was written.
        """
        stats = {"songs": 0, "postings": 0, "song_fp_rows": 0, "hashes": 0, "hashes_new": 0,
                 "parts_updated": 0, "parts_inserted": 0}
        if not items:
            return stats
        songs = []
        for sid, h32, off in items:
            sid = int(sid)
            if not 0 < sid < 1 << 31:
                raise ValueError(f"song id {sid} out of range")
            h32 = np.ascontiguousarray(h32, np.uint32)
            off = np.ascontiguousarray(off, np.int64)
            if len(h32) == 0:
                raise ValueError(f"song {sid}: no fingerprints to write")
            if off.min() < 0 or off.max() >= MAX_OFFSET:
                raise ValueError(f"song {sid}: offset {int(off.max())} does not fit uint16 — the track is longer "
                                 f"than {MAX_OFFSET / FRAMES_PER_S / 60:.0f} minutes")
            songs.append((sid, *unique_pairs(h32, off)))

        with self._transaction() as cur:
            gen, block_frames, part_postings = self._writable_gen(cur)
            song_rows, h_all, s_all, o_all = [], [], [], []
            for sid, h32, off in songs:
                block = off // block_frames
                if block.max() >= MAX_BLOCK:
                    raise ValueError(f"song {sid}: block {int(block.max())} does not fit smallint")
                order = np.lexsort((off, h32, block))
                h32, off, block = h32[order], off[order].astype(np.uint16), block[order]
                starts = np.flatnonzero(np.r_[True, block[1:] != block[:-1]])
                for s, e in zip(starts.tolist(), np.r_[starts[1:], len(block)].tolist()):
                    song_rows.append((sid, int(block[s]), e - s, codec.encode(h32[s:e], off[s:e], presorted=True)))
                h_all.append(h32)
                o_all.append(off)
                s_all.append(np.full(len(h32), sid, np.uint32))
                stats["songs"] += 1
                stats["postings"] += int(len(h32))
            stats["song_fp_rows"] = len(song_rows)

            h, s, o = np.concatenate(h_all), np.concatenate(s_all), np.concatenate(o_all)
            order = np.lexsort((o, s, h))               # hash, then song, then offset
            h, s, o = h[order], s[order], o[order]
            uh, first, cnt = np.unique(h, return_index=True, return_counts=True)
            stats["hashes"] = int(len(uh))

            execute_values(cur, "INSERT INTO song_fp (song_id, block, n, fp) VALUES %s", song_rows, page_size=200)
            for c0 in range(0, len(uh), self.chunk_hashes):
                sl = slice(c0, min(c0 + self.chunk_hashes, len(uh)))
                hashes = uh[sl].view(np.int32)
                tails = self._tail_parts(cur, gen, hashes)
                updates, inserts, df_rows = [], [], []
                for hi, st, n in zip(hashes.tolist(), first[sl].tolist(), cnt[sl].tolist()):
                    new_s, new_o, part = s[st:st + n], o[st:st + n], 0
                    tail = tails.get(hi)
                    if tail is None:
                        stats["hashes_new"] += 1
                    else:
                        part, tn, blob = tail
                        if tn < part_postings:          # top the last part up before starting a new one
                            ts, to = codec.decode(blob, tn)
                            new_s, new_o = np.concatenate([ts, new_s]), np.concatenate([to, new_o])
                            merge = np.lexsort((new_o, new_s))
                            new_s, new_o = new_s[merge], new_o[merge]
                            take = min(len(new_s), part_postings)
                            updates.append((take, codec.encode(new_s[:take], new_o[:take], presorted=True),
                                            hi, gen, part))
                            new_s, new_o = new_s[take:], new_o[take:]
                        part += 1
                    for p0 in range(0, len(new_s), part_postings):
                        p1 = min(p0 + part_postings, len(new_s))
                        inserts.append((hi, gen, part, p1 - p0,
                                        codec.encode(new_s[p0:p1], new_o[p0:p1], presorted=True)))
                        part += 1
                    df_rows.append((hi, n))
                if updates:
                    execute_batch(cur, "UPDATE fp_postings SET n = %s, postings = %s "
                                       "WHERE hash = %s AND gen = %s AND part = %s", updates, page_size=500)
                if inserts:
                    execute_values(cur, "INSERT INTO fp_postings (hash, gen, part, n, postings) VALUES %s",
                                   inserts, page_size=500)
                execute_values(cur, "INSERT INTO fp_df (hash, n) VALUES %s "
                                    "ON CONFLICT (hash) DO UPDATE SET n = fp_df.n + EXCLUDED.n",
                               df_rows, page_size=1000)
                stats["parts_updated"] += len(updates)
                stats["parts_inserted"] += len(inserts)
            cur.execute("UPDATE fp_gen SET n_songs = coalesce(n_songs, 0) + %s, "
                        "n_postings = coalesce(n_postings, 0) + %s WHERE gen = %s",
                        (stats["songs"], stats["postings"], gen))
            for sid, h32, _ in songs:
                cur.execute(UPDATE_SONG_FINGERPRINTED, (int(len(h32)), sid))
                if cur.rowcount != 1:                   # postings must not outlive a missing songs row
                    raise RuntimeError(f"song {sid} has no row in {SONGS_TABLENAME}")
        return stats

    @staticmethod
    def _tail_parts(cur, gen: int, hashes_i32: np.ndarray) -> Dict[int, Tuple[int, int, memoryview]]:
        """hash -> (highest part number, n, blob), for the hashes that already exist."""
        cur.execute("""SELECT DISTINCT ON (hash) hash, part, n, postings FROM fp_postings
                       WHERE gen = %s AND hash = ANY(%s::int4[]) ORDER BY hash, part DESC""",
                    (gen, hashes_i32.tolist()))
        return {int(h): (int(p), int(n), b) for h, p, n, b in cur.fetchall()}

    def remove_songs(self, song_ids: Sequence[int]) -> Dict[str, int]:
        """Takes songs out of the store: song_fp rows, their postings in every part, and the fp_df counts.
        Their songs rows are left to the caller."""
        stats = {"songs": 0, "postings": 0, "parts_updated": 0, "parts_deleted": 0}
        with self._transaction() as cur:
            gen, _, _ = self._writable_gen(cur)
            for sid in map(int, song_ids):
                cur.execute("SELECT n, fp FROM song_fp WHERE song_id = %s", (sid,))
                blocks = cur.fetchall()
                if not blocks:
                    continue
                hashes = np.unique(np.concatenate([codec.decode(b, n)[0] for n, b in blocks])).view(np.int32)
                removed = 0
                for c0 in range(0, len(hashes), REMOVE_CHUNK):
                    chunk = hashes[c0:c0 + REMOVE_CHUNK]
                    cur.execute("SELECT hash, part, n, postings FROM fp_postings "
                                "WHERE gen = %s AND hash = ANY(%s::int4[]) ORDER BY hash, part",
                                (gen, chunk.tolist()))
                    updates, deletes, df_updates = [], [], {}
                    for hi, part, n, blob in cur.fetchall():
                        s, o = codec.decode(blob, n)
                        keep = s != sid
                        left = int(keep.sum())
                        if left == n:
                            continue
                        df_updates[int(hi)] = df_updates.get(int(hi), 0) + (n - left)
                        if left:
                            updates.append((left, codec.encode(s[keep], o[keep], presorted=True),
                                            int(hi), gen, int(part)))
                        else:
                            deletes.append((int(hi), gen, int(part)))
                    if updates:
                        execute_batch(cur, "UPDATE fp_postings SET n = %s, postings = %s "
                                           "WHERE hash = %s AND gen = %s AND part = %s", updates, page_size=500)
                    if deletes:
                        execute_batch(cur, "DELETE FROM fp_postings WHERE hash = %s AND gen = %s AND part = %s",
                                      deletes, page_size=500)
                    if df_updates:
                        execute_batch(cur, "UPDATE fp_df SET n = n - %s WHERE hash = %s",
                                      [(n, hi) for hi, n in df_updates.items()], page_size=1000)
                        cur.execute("DELETE FROM fp_df WHERE hash = ANY(%s::int4[]) AND n <= 0",
                                    (list(df_updates),))
                    stats["parts_updated"] += len(updates)
                    stats["parts_deleted"] += len(deletes)
                    removed += sum(df_updates.values())
                cur.execute("DELETE FROM song_fp WHERE song_id = %s", (sid,))
                stats["songs"] += 1
                stats["postings"] += removed
            if stats["songs"]:
                cur.execute("UPDATE fp_gen SET n_songs = n_songs - %s, n_postings = n_postings - %s WHERE gen = %s",
                            (stats["songs"], stats["postings"], gen))
        return stats

    # ── search ────────────────────────────────────────────────────────────────

    def search(self, h32: np.ndarray, offsets: np.ndarray, exclude_songs=None) -> Tuple[List[Dict], Dict]:
        """
        Recognizes a query from its (hash32, offset) pairs, as fingerprint_hash32 returns them.

        :param exclude_songs: song ids left out entirely, as if they were not in the catalogue (for evaluation).
        :return: up to topn results, best first, with the keys of Dejavu.align_matches; and search statistics.
        """
        stats = {"query_pairs": int(len(h32))}
        exclude = np.asarray(sorted(exclude_songs), np.int64) if exclude_songs else None
        if len(h32) == 0:
            return [], stats
        t0 = time.perf_counter()
        h32, offsets = unique_pairs(np.asarray(h32), np.asarray(offsets))
        uh, inv = np.unique(h32, return_inverse=True)            # distinct query hashes
        uh_i32 = uh.view(np.int32)
        q_order = np.argsort(inv, kind="stable")                 # query offsets grouped by distinct hash
        q_cnt = np.bincount(inv, minlength=len(uh))
        q_start = np.concatenate(([0], np.cumsum(q_cnt)[:-1]))
        q_off = offsets[q_order]

        with self._cursor() as cur:
            live = self._live(cur)
            gens = [g for g, _, _ in live]
            block_frames = {b for _, b, _ in live}
            if len(block_frames) != 1:
                raise RuntimeError(f"live generations disagree on block_frames: {block_frames}")
            block_frames = block_frames.pop()

            df = self._df(cur, uh)
            found = df > 0
            usable = np.flatnonzero(found & (df <= self.stop_df))
            order = usable[np.argsort(df[usable], kind="stable")]
            cum = np.cumsum(df[order])
            stats.update(distinct_hashes=int(len(uh)), found_hashes=int(found.sum()), usable_hashes=int(len(usable)))

            fetched = 0
            songs, diffs = [], []
            all_s, all_d = np.empty(0, np.int64), np.empty(0, np.int64)
            stage = 0
            candidates = []
            for stage, budget in enumerate(self.stages, 1):
                take = len(order) if budget is None else min(len(order), int(np.searchsorted(cum, budget)) + 1)
                new = order[fetched:take]
                fetched = take
                if len(new):
                    s, d = self._fetch_votes(cur, gens, uh_i32, new, q_start, q_cnt, q_off)
                    if exclude is not None:
                        keep = ~np.isin(s, exclude)
                        s, d = s[keep], d[keep]
                    songs.append(s)
                    diffs.append(d)
                    all_s, all_d = np.concatenate(songs), np.concatenate(diffs)
                candidates = best_per_song(all_s, all_d, self.topn)
                v1 = candidates[0][2] if candidates else 0
                v2 = candidates[1][2] if len(candidates) > 1 else 0
                if (v1 >= self.min_votes and v1 >= self.margin * v2) or fetched == len(order):
                    break
            stats.update(stage=stage, postings_fetched=int(cum[fetched - 1]) if fetched else 0,
                         fetch_ms=round((time.perf_counter() - t0) * 1000, 1))

            t1 = time.perf_counter()
            to_verify = top_offsets(all_s, all_d, [c[0] for c in candidates], self.offsets_per_song)
            results = self._verify(cur, block_frames, to_verify, h32, offsets)
        stats["verify_ms"] = round((time.perf_counter() - t1) * 1000, 1)
        stats["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return results, stats

    @staticmethod
    def _df(cur, uh: np.ndarray) -> np.ndarray:
        """Postings of each distinct query hash (uh: uint32, ascending); 0 for hashes the store does not hold."""
        cur.execute("SELECT hash, n FROM fp_df WHERE hash = ANY(%s::int4[])", (uh.view(np.int32).tolist(),))
        rows = cur.fetchall()
        df = np.zeros(len(uh), np.int64)
        if rows:
            h, n = np.array(rows, np.int64).T
            df[np.searchsorted(uh, h.astype(np.uint32))] = n
        return df

    @staticmethod
    def _fetch_votes(cur, gens, uh_i32, idx, q_start, q_cnt, q_off):
        hashes = np.sort(uh_i32[idx])
        cur.execute("SELECT hash, n, postings FROM fp_postings WHERE hash = ANY(%s::int4[]) AND gen = ANY(%s::int2[])",
                    (hashes.tolist(), gens))
        rows = cur.fetchall()
        where = {int(h): int(i) for h, i in zip(uh_i32[idx], idx)}
        songs, db_off, hid = [], [], []
        for h, n, blob in rows:
            s, o = codec.decode(blob, n)
            songs.append(s)
            db_off.append(o)
            hid.append(np.full(n, where[h], np.int64))
        if not rows:
            return np.empty(0, np.int64), np.empty(0, np.int64)
        song, off, hid = np.concatenate(songs), np.concatenate(db_off).astype(np.int64), np.concatenate(hid)
        rep = q_cnt[hid]                                           # expand postings x query offsets of that hash
        src = np.repeat(np.arange(len(hid)), rep)
        within = np.arange(len(src)) - np.repeat(np.cumsum(rep) - rep, rep)
        return song[src].astype(np.int64), off[src] - q_off[q_start[hid[src]] + within]

    def _verify(self, cur, block_frames: int, candidates, h32, offsets) -> List[Dict]:
        """candidates: (song, offset difference, votes), possibly several per song."""
        if not candidates:
            return []
        q_min, q_max = int(offsets.min()), int(offsets.max())
        windows = set()
        for song, diff, _ in candidates:
            lo, hi = max(0, (diff + q_min) // block_frames), max(0, (diff + q_max) // block_frames)
            windows.update((song, b) for b in range(lo, hi + 1))
        windows = sorted(windows)
        song_ids = sorted({c[0] for c in candidates})
        cur.execute("""SELECT s.song_id, s.n, s.fp FROM song_fp s
                       JOIN unnest(%s::int4[], %s::int2[]) AS w(song_id, block) USING (song_id, block)""",
                    ([w[0] for w in windows], [w[1] for w in windows]))
        blocks = cur.fetchall()
        cur.execute(SELECT_SONGS, (song_ids,))
        meta = {int(r[0]): r for r in cur.fetchall()}
        per_song: Dict[int, List[np.ndarray]] = {}
        for sid, n, blob in blocks:
            h, o = codec.decode(blob, n)
            per_song.setdefault(int(sid), []).append(h.astype(np.uint64) << np.uint64(16) | o.astype(np.uint64))
        keys_of = {sid: np.sort(np.concatenate(parts)) for sid, parts in per_song.items()}

        best: Dict[int, Tuple[int, int, int, int]] = {}      # song -> (verified, votes, song, diff)
        for song, diff, votes in candidates:
            keys = keys_of.get(song)
            verified = 0
            if keys is not None and len(keys):
                aligned = offsets + diff
                ok = (aligned >= 0) & (aligned < MAX_OFFSET)
                want = h32[ok].astype(np.uint64) << np.uint64(16) | aligned[ok].astype(np.uint64)
                p = np.minimum(np.searchsorted(keys, want), len(keys) - 1)
                verified = int((keys[p] == want).sum())
            prev = best.get(song)
            # best verified count; ties go to more votes, then the smaller offset (as align_matches keeps)
            if prev is None or (verified, votes, -diff) > (prev[0], prev[1], -prev[3]):
                best[song] = (verified, votes, song, diff)
        scored = sorted(best.values(), key=lambda x: (-x[0], -x[1]))

        results = []
        queried = len(h32)
        for verified, _, song, diff in scored[:self.topn]:
            m = meta.get(song)
            if m is None or verified == 0:
                continue
            total = m[3] or 0
            results.append({
                SONG_ID: song,
                SONG_NAME: (m[1] or "").encode("utf8"),
                INPUT_HASHES: queried,
                FINGERPRINTED_HASHES: total,
                HASHES_MATCHED: verified,
                # Percentage regarding hashes matched vs hashes from the input.
                INPUT_CONFIDENCE: round(verified / queried, 2),
                # Percentage regarding hashes matched vs hashes fingerprinted in the db.
                FINGERPRINTED_CONFIDENCE: round(verified / total, 2) if total else 0.0,
                OFFSET: diff,
                OFFSET_SECS: round(float(diff) / DEFAULT_FS * DEFAULT_WINDOW_SIZE * DEFAULT_OVERLAP_RATIO, 5),
                FIELD_FILE_SHA1: (m[2] or "").encode("utf8"),
            })
        return results
