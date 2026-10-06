"""
Tables of the compact fingerprint store. They replace the fingerprints table; songs is unchanged.

There are no secondary indexes: every runtime access is a primary-key probe. Blobs are stored with
STORAGE MAIN and toast_tuple_target 8160 so they stay inline in the heap page instead of being moved
to TOAST, and are not compressed a second time (fpstore.codec has already deflated them).
"""

CREATE_TABLES = [
    """
    CREATE TABLE song_fp (
        song_id int      NOT NULL,
        block   smallint NOT NULL,      -- fixed time window: offset // fp_gen.block_frames
        n       int      NOT NULL,      -- postings in the blob
        fp      bytea    NOT NULL,      -- fpstore.codec blob: hash32 keys, offset values
        PRIMARY KEY (song_id, block)
    ) WITH (fillfactor = 100, toast_tuple_target = 8160)
    """,
    "ALTER TABLE song_fp ALTER COLUMN fp SET STORAGE MAIN",
    """
    CREATE TABLE fp_postings (
        hash     int      NOT NULL,     -- hash32 = (f1 << 20) | (f2 << 8) | dt, as signed int4
        gen      smallint NOT NULL,     -- posting generation
        part     smallint NOT NULL,     -- long lists are split so each row fits one page
        n        int      NOT NULL,
        postings bytea    NOT NULL,     -- fpstore.codec blob: song_id keys, offset values
        PRIMARY KEY (hash, gen, part)
    ) WITH (fillfactor = 100, toast_tuple_target = 8160)
    """,
    "ALTER TABLE fp_postings ALTER COLUMN postings SET STORAGE MAIN",
    """
    CREATE TABLE fp_df (
        hash int NOT NULL PRIMARY KEY,
        n    int NOT NULL               -- total postings for the hash, all generations
    ) WITH (fillfactor = 100)
    """,
    """
    CREATE TABLE fp_gen (
        gen           smallint    PRIMARY KEY,
        state         text        NOT NULL CHECK (state IN ('building', 'live', 'retired')),
        block_frames  int         NOT NULL,
        part_postings int         NOT NULL,
        n_songs       int,
        n_postings    bigint,
        built_at      timestamptz NOT NULL DEFAULT now()
    )
    """,
]

INSERT_GEN = """
    INSERT INTO fp_gen (gen, state, block_frames, part_postings, n_songs, n_postings)
    VALUES (0, 'live', %s, %s, 0, 0)
"""

DROP_TABLES = "DROP TABLE IF EXISTS song_fp, fp_postings, fp_df, fp_gen"

TABLES = ("song_fp", "fp_postings", "fp_df", "fp_gen")
