from __future__ import absolute_import
from itertools import zip_longest
import queue as Queue

import sqlite3

from dejavu.database import Database


class SQLiteDatabase(Database):
    """
    Queries:

    1) Find duplicates (shouldn't be any, though):

        select `hash`, `song_id`, `offset`, count(*) cnt
        from fingerprints
        group by `hash`, `song_id`, `offset`
        having cnt > 1
        order by cnt asc;

    2) Get number of hashes by song:

        select song_id, song_name, count(song_id) as num
        from fingerprints
        natural join songs
        group by song_id
        order by count(song_id) desc;

    3) get hashes with highest number of collisions

        select
            hash,
            count(distinct song_id) as n
        from fingerprints
        group by `hash`
        order by n DESC;

    => 26 different songs with same fingerprint (392 times):

        select songs.song_name, fingerprints.offset
        from fingerprints natural join songs
        where fingerprints.hash = "08d3c833b71c60a7b620322ac0c0aba7bf5a3e73";
    """

    type = "sqlite3"

    # tables
    FINGERPRINTS_TABLENAME = "fingerprints"
    SONGS_TABLENAME = "songs"

    # fields
    FIELD_FINGERPRINTED = "fingerprinted"
    FIELD_SONG_ID = "rowid"

    # creates
    CREATE_FINGERPRINTS_TABLE = """
        CREATE TABLE IF NOT EXISTS `%s` (
             `%s` binary not null,
             `%s` mediumint unsigned not null,
             `%s` INTEGER not null,
         UNIQUE(%s, %s, %s),
         FOREIGN KEY (%s) REFERENCES %s(%s) ON DELETE CASCADE
    ) """ % (
        FINGERPRINTS_TABLENAME, Database.FIELD_HASH,
        Database.FIELD_SONG_ID, Database.FIELD_OFFSET,
        Database.FIELD_SONG_ID, Database.FIELD_OFFSET, Database.FIELD_HASH,
        Database.FIELD_SONG_ID, SONGS_TABLENAME, FIELD_SONG_ID
    )

    CREATE_SONGS_TABLE = """
        CREATE TABLE IF NOT EXISTS %s (
                %s STRING NOT NULL,
                %s INTEGER DEFAULT 0,
                %s TEXT NOT NULL
        )
    """ % (
        SONGS_TABLENAME,
        Database.FIELD_SONGNAME,
        FIELD_FINGERPRINTED,
        Database.FIELD_FILE_SHA1,
    )

    # inserts (ignores duplicates)
    INSERT_FINGERPRINT = """
        INSERT OR IGNORE INTO %s (%s, %s, %s) values
            (?, ?, ?);
    """ % (FINGERPRINTS_TABLENAME, Database.FIELD_HASH, Database.FIELD_SONG_ID, Database.FIELD_OFFSET)

    INSERT_SONG = "INSERT INTO %s (%s, %s) values (?, ?)" % (
        SONGS_TABLENAME, Database.FIELD_SONGNAME, Database.FIELD_FILE_SHA1)

    # selects
    SELECT = """
        SELECT %s, %s FROM %s WHERE %s = ?
    """ % (Database.FIELD_SONG_ID, Database.FIELD_OFFSET, FINGERPRINTS_TABLENAME, Database.FIELD_HASH)

    SELECT_MULTIPLE = """
        SELECT %s, %s, %s, %s FROM %s WHERE %s IN (%%s)
    """ % (FIELD_SONG_ID, Database.FIELD_HASH, Database.FIELD_SONG_ID, Database.FIELD_OFFSET,
           FINGERPRINTS_TABLENAME, Database.FIELD_HASH)

    SELECT_ALL = """
        SELECT %s, %s FROM %s;
    """ % (Database.FIELD_SONG_ID, Database.FIELD_OFFSET, FINGERPRINTS_TABLENAME)

    SELECT_SONG = """
        SELECT %s, %s as %s FROM %s WHERE %s = ?
    """ % (Database.FIELD_SONGNAME, Database.FIELD_FILE_SHA1, Database.FIELD_FILE_SHA1, SONGS_TABLENAME, FIELD_SONG_ID)

    SELECT_NUM_FINGERPRINTS = """
        SELECT COUNT(*) as n FROM %s
    """ % (FINGERPRINTS_TABLENAME)

    SELECT_UNIQUE_SONG_IDS = """
        SELECT COUNT(DISTINCT %s) AS n FROM %s WHERE %s = 1;
    """ % (FIELD_SONG_ID, SONGS_TABLENAME, FIELD_FINGERPRINTED)

    SELECT_SONGS = """
        SELECT %s AS %s, %s, %s as %s FROM %s WHERE %s = 1;
    """ % (FIELD_SONG_ID, Database.FIELD_SONG_ID, Database.FIELD_SONGNAME, Database.FIELD_FILE_SHA1, Database.FIELD_FILE_SHA1,
           SONGS_TABLENAME, FIELD_FINGERPRINTED)

    # drops
    DROP_FINGERPRINTS = "DROP TABLE IF EXISTS %s;" % FINGERPRINTS_TABLENAME
    DROP_SONGS = "DROP TABLE IF EXISTS %s;" % SONGS_TABLENAME

    # update
    UPDATE_SONG_FINGERPRINTED = """
        UPDATE %s SET %s = 1 WHERE %s = ?
    """ % (SONGS_TABLENAME, FIELD_FINGERPRINTED, FIELD_SONG_ID)

    # delete
    DELETE_UNFINGERPRINTED = """
        DELETE FROM %s WHERE %s = 0;
    """ % (SONGS_TABLENAME, FIELD_FINGERPRINTED)

    def __init__(self, **options):
        super(SQLiteDatabase, self).__init__()
        self.cursor = cursor_factory(**options)
        self._options = options

    def after_fork(self):
        # Clear the cursor cache, we don't want any stale connections from
        # the previous process.
        Cursor.clear_cache()

    def setup(self):
        """
        Creates any non-existing tables required for dejavu to function.

        This also removes all songs that have been added but have no
        fingerprints associated with them.
        """
        with self.cursor() as cur:
            cur.execute(self.CREATE_SONGS_TABLE)
            cur.execute(self.CREATE_FINGERPRINTS_TABLE)
            # cur.execute(self.CREATE_LOGGING_TABLE)
            cur.execute(self.DELETE_UNFINGERPRINTED)

    def empty(self):
        """
        Drops tables created by dejavu and then creates them again
        by calling `SQLDatabase.setup`.

        .. warning:
            This will result in a loss of data
        """
        with self.cursor() as cur:
            cur.execute(self.DROP_FINGERPRINTS)
            cur.execute(self.DROP_SONGS)

        self.setup()

    def delete_unfingerprinted_songs(self):
        """
        Removes all songs that have no fingerprints associated with them.
        """
        with self.cursor() as cur:
            cur.execute(self.DELETE_UNFINGERPRINTED)

    def get_num_songs(self):
        """
        Returns number of songs the database has fingerprinted.
        """
        with self.cursor() as cur:
            cur.execute(self.SELECT_UNIQUE_SONG_IDS)

            for count, in cur:
                return count
            return 0

    def get_num_fingerprints(self):
        """
        Returns number of fingerprints the database has fingerprinted.
        """
        with self.cursor() as cur:
            cur.execute(self.SELECT_NUM_FINGERPRINTS)

            for count, in cur:
                return count
            return 0

    def set_song_fingerprinted(self, sid):
        """
        Set the fingerprinted flag to TRUE (1) once a song has been completely
        fingerprinted in the database.
        """
        with self.cursor() as cur:
            cur.execute(self.UPDATE_SONG_FINGERPRINTED, (sid,))

    def get_songs(self):
        """
        Return songs that have the fingerprinted flag set TRUE (1).
        """
        with self.cursor() as cur:
            cur.execute(self.SELECT_SONGS)
            for row in cur:
                yield row

    def get_song_by_id(self, sid):
        """
        Returns song by its ID.
        """
        with self.cursor() as cur:
            cur.execute(self.SELECT_SONG, (sid,))
            return cur.fetchone()

    def insert(self, hash, sid, offset):
        """
        Insert a (sha1, song_id, offset) row into database.
        """
        with self.cursor() as cur:
            cur.execute(self.INSERT_FINGERPRINT, (hash.encode(), sid, offset))

    def insert_log(self, content):
        with self.cursor() as cur:
            cur.execute(self.INSERT_LOG, (content,))

    def insert_song(self, songname, file_hash):
        """
        Inserts song in the database and returns the ID of the inserted record.
        """
        with self.cursor() as cur:
            cur.execute(self.INSERT_SONG, (songname, file_hash))
            return cur.lastrowid

    def query(self, hash):
        """
        Return all tuples associated with hash.

        If hash is None, returns all entries in the
        database (be careful with that one!).
        """
        with self.cursor() as cur:
            if hash is None:
                cur.execute(self.SELECT_ALL)
            else:
                cur.execute(self.SELECT, [hash.encode()])

            for result in cur.fetchall():
                yield (result[Database.FIELD_SONG_ID], result[Database.FIELD_OFFSET])

    def get_iterable_kv_pairs(self):
        """
        Returns all tuples in database.
        """
        return self.query(None)

    def insert_hashes(self, sid, hashes):
        """
        Insert series of hash => song_id, offset
        values into the database.
        """
        values = []
        for ahash, offset in hashes:
            values.append((ahash.encode(), sid, int(offset)))

        with self.cursor() as cur:
            for split_values in grouper(values, 100):
                cur.executemany(self.INSERT_FINGERPRINT, list(split_values))

    def return_matches(self, hashes):
        """
        Return the (song_id, offset_diff) tuples associated with
        a list of (sha1, sample_offset) values.
        """
        mapper = {}        
        for hash, offset in hashes:
            mapper[hash.encode()] = offset

        # Get an iteratable of all the hashes we need
        values = mapper.keys()

        with self.cursor() as cur:
            for split_values in grouper(values, 998):
                split_list = list(split_values)
                # Create our IN part of the query
                query = self.SELECT_MULTIPLE
                query = query % ', '.join(['?'] * len(split_list))

                for result in cur.execute(query, split_list).fetchall():
                    # (sid, db_offset - song_sampled_offset)
                    try:
                        returned_offset = result[Database.FIELD_OFFSET]
                        returned_hash = result[Database.FIELD_HASH]
                        original_offset = mapper[returned_hash]

                        adjusted_offset = returned_offset - original_offset

                        returned_song_id = result[Database.FIELD_SONG_ID]

                        yield (returned_song_id, adjusted_offset)
                    except TypeError:
                        raise Exception("Result: {}\nOffset From Map: {}\nRehashed Hash: {}".format(result, original_offset, hash.encode()))


    def __getstate__(self):
        return (self._options,)

    def __setstate__(self, state):
        self._options, = state
        self.cursor = cursor_factory(**self._options)


def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return (filter(None, values) for values
            in zip_longest(fillvalue=fillvalue, *args))

def cursor_factory(**factory_options):
    def cursor(**options):
        options.update(factory_options)
        return Cursor(**options)
    return cursor

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]

    return d
    
def setup_db(db_path, dict_factory = dict_factory):
    conn = sqlite3.connect(db_path)
    conn.row_factory = dict_factory
    return conn

class Cursor(object):
    """
    Establishes a connection to the database and returns an open cursor.


    ```python
    # Use as context manager
    with Cursor() as cur:
        cur.execute(query)
    ```
    """
    _cache = Queue.Queue(maxsize=5)

    def __init__(self, cursor_type=sqlite3.Cursor, **options):
        super(Cursor, self).__init__()

        try:
            conn = self._cache.get_nowait()
        except Queue.Empty:
            # conn = sqlite3.connect(**options)
            conn = setup_db(**options)
        else:
            nothing = None

        self.conn = conn

    @classmethod
    def clear_cache(cls):
        cls._cache = Queue.Queue(maxsize=5)

    def __enter__(self):
        self.cursor = self.conn.cursor()
        return self.cursor

    def __exit__(self, extype, exvalue, traceback):
        # if we had a SQL related error we try to rollback the cursor.
        if extype is sqlite3.Error:
            self.cursor.rollback()

        self.cursor.close()
        self.conn.commit()

        # Put it back on the queue
        try:
            self._cache.put_nowait(self.conn)
        except Queue.Full:
            self.conn.close()
