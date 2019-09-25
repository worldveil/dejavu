import queue

import psycopg2
from psycopg2.extras import DictCursor

from dejavu.base_classes.common_database import CommonDatabase
from dejavu.config.settings import (FIELD_FILE_SHA1, FIELD_FINGERPRINTED,
                                    FIELD_HASH, FIELD_OFFSET, FIELD_SONG_ID,
                                    FIELD_SONGNAME, FINGERPRINTS_TABLENAME,
                                    SONGS_TABLENAME)


class PostgreSQLDatabase(CommonDatabase):
    type = "postgres"

    # CREATES
    CREATE_SONGS_TABLE = f"""
        CREATE TABLE IF NOT EXISTS "{SONGS_TABLENAME}" (
            "{FIELD_SONG_ID}" SERIAL
        ,   "{FIELD_SONGNAME}" VARCHAR(250) NOT NULL
        ,   "{FIELD_FINGERPRINTED}" SMALLINT DEFAULT 0
        ,   "{FIELD_FILE_SHA1}" BYTEA
        ,   "date_created" TIMESTAMP NOT NULL DEFAULT now()
        ,   "date_modified" TIMESTAMP NOT NULL DEFAULT now()
        ,   CONSTRAINT "pk_{SONGS_TABLENAME}_{FIELD_SONG_ID}" PRIMARY KEY ("{FIELD_SONG_ID}")
        ,   CONSTRAINT "uq_{SONGS_TABLENAME}_{FIELD_SONG_ID}" UNIQUE ("{FIELD_SONG_ID}")
        );
    """

    CREATE_FINGERPRINTS_TABLE = f"""
        CREATE TABLE IF NOT EXISTS "{FINGERPRINTS_TABLENAME}" (
            "{FIELD_HASH}" BYTEA NOT NULL
        ,   "{FIELD_SONG_ID}" INT NOT NULL
        ,   "{FIELD_OFFSET}" INT NOT NULL
        ,   "date_created" TIMESTAMP NOT NULL DEFAULT now()
        ,   "date_modified" TIMESTAMP NOT NULL DEFAULT now()
        ,   CONSTRAINT "uq_{FINGERPRINTS_TABLENAME}" UNIQUE  ("{FIELD_SONG_ID}", "{FIELD_OFFSET}", "{FIELD_HASH}")
        ,   CONSTRAINT "fk_{FINGERPRINTS_TABLENAME}_{FIELD_SONG_ID}" FOREIGN KEY ("{FIELD_SONG_ID}")
                REFERENCES "{SONGS_TABLENAME}"("{FIELD_SONG_ID}") ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS "ix_{FINGERPRINTS_TABLENAME}_{FIELD_HASH}" ON "{FINGERPRINTS_TABLENAME}"
        USING hash ("{FIELD_HASH}");
    """

    CREATE_FINGERPRINTS_TABLE_INDEX = f"""
        CREATE INDEX "ix_{FINGERPRINTS_TABLENAME}_{FIELD_HASH}" ON "{FINGERPRINTS_TABLENAME}"
        USING hash ("{FIELD_HASH}");
    """

    # INSERTS (IGNORES DUPLICATES)
    INSERT_FINGERPRINT = f"""
        INSERT INTO "{FINGERPRINTS_TABLENAME}" (
                "{FIELD_SONG_ID}"
            ,   "{FIELD_HASH}"
            ,   "{FIELD_OFFSET}")
        VALUES (%s, decode(%s, 'hex'), %s) ON CONFLICT DO NOTHING;
    """

    INSERT_SONG = f"""
        INSERT INTO "{SONGS_TABLENAME}" ("{FIELD_SONGNAME}", "{FIELD_FILE_SHA1}")
        VALUES (%s, decode(%s, 'hex'))
        RETURNING "{FIELD_SONG_ID}";
    """

    # SELECTS
    SELECT = f"""
        SELECT "{FIELD_SONG_ID}", "{FIELD_OFFSET}"
        FROM "{FINGERPRINTS_TABLENAME}"
        WHERE "{FIELD_HASH}" = decode(%s, 'hex');
    """

    SELECT_MULTIPLE = f"""
        SELECT upper(encode("{FIELD_HASH}", 'hex')), "{FIELD_SONG_ID}", "{FIELD_OFFSET}"
        FROM "{FINGERPRINTS_TABLENAME}"
        WHERE "{FIELD_HASH}" IN (%s);
    """

    SELECT_ALL = f'SELECT "{FIELD_SONG_ID}", "{FIELD_OFFSET}" FROM "{FINGERPRINTS_TABLENAME}";'

    SELECT_SONG = f"""
        SELECT "{FIELD_SONGNAME}", upper(encode("{FIELD_FILE_SHA1}", 'hex')) AS "{FIELD_FILE_SHA1}"
        FROM "{SONGS_TABLENAME}"
        WHERE "{FIELD_SONG_ID}" = %s;
    """

    SELECT_NUM_FINGERPRINTS = f'SELECT COUNT(*) AS n FROM "{FINGERPRINTS_TABLENAME}";'

    SELECT_UNIQUE_SONG_IDS = f"""
        SELECT COUNT("{FIELD_SONG_ID}") AS n
        FROM "{SONGS_TABLENAME}"
        WHERE "{FIELD_FINGERPRINTED}" = 1;
    """

    SELECT_SONGS = f"""
        SELECT
            "{FIELD_SONG_ID}"
        ,   "{FIELD_SONGNAME}"
        ,   upper(encode("{FIELD_FILE_SHA1}", 'hex')) AS "{FIELD_FILE_SHA1}"
        FROM "{SONGS_TABLENAME}"
        WHERE "{FIELD_FINGERPRINTED}" = 1;
    """

    # DROPS
    DROP_FINGERPRINTS = F'DROP TABLE IF EXISTS "{FINGERPRINTS_TABLENAME}";'
    DROP_SONGS = F'DROP TABLE IF EXISTS "{SONGS_TABLENAME}";'

    # UPDATE
    UPDATE_SONG_FINGERPRINTED = f"""
        UPDATE "{SONGS_TABLENAME}" SET
            "{FIELD_FINGERPRINTED}" = 1
        ,   "date_modified" = now()
        WHERE "{FIELD_SONG_ID}" = %s;
    """

    # DELETE
    DELETE_UNFINGERPRINTED = f"""
        DELETE FROM "{SONGS_TABLENAME}" WHERE "{FIELD_FINGERPRINTED}" = 0;
    """

    # IN
    IN_MATCH = f"decode(%s, 'hex')"

    def __init__(self, **options):
        super().__init__()
        self.cursor = cursor_factory(**options)
        self._options = options

    def after_fork(self):
        # Clear the cursor cache, we don't want any stale connections from
        # the previous process.
        Cursor.clear_cache()

    def insert_song(self, song_name, file_hash):
        """
        Inserts song in the database and returns the ID of the inserted record.
        """
        with self.cursor() as cur:
            cur.execute(self.INSERT_SONG, (song_name, file_hash))
            return cur.fetchone()[0]

    def __getstate__(self):
        return self._options,

    def __setstate__(self, state):
        self._options, = state
        self.cursor = cursor_factory(**self._options)


def cursor_factory(**factory_options):
    def cursor(**options):
        options.update(factory_options)
        return Cursor(**options)
    return cursor


class Cursor(object):
    """
    Establishes a connection to the database and returns an open cursor.
    # Use as context manager
    with Cursor() as cur:
        cur.execute(query)
        ...
    """
    def __init__(self, dictionary=False, **options):
        super().__init__()

        self._cache = queue.Queue(maxsize=5)

        try:
            conn = self._cache.get_nowait()
            # Ping the connection before using it from the cache.
            conn.ping(True)
        except queue.Empty:
            conn = psycopg2.connect(**options)

        self.conn = conn
        self.dictionary = dictionary

    @classmethod
    def clear_cache(cls):
        cls._cache = queue.Queue(maxsize=5)

    def __enter__(self):
        if self.dictionary:
            self.cursor = self.conn.cursor(cursor_factory=DictCursor)
        else:
            self.cursor = self.conn.cursor()
        return self.cursor

    def __exit__(self, extype, exvalue, traceback):
        # if we had a PostgreSQL related error we try to rollback the cursor.
        if extype is psycopg2.DatabaseError:
            self.cursor.rollback()

        self.cursor.close()
        self.conn.commit()

        # Put it back on the queue
        try:
            self._cache.put_nowait(self.conn)
        except queue.Full:
            self.conn.close()
