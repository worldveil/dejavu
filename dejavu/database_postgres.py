""" Class for interacting with Postgres database.
"""
from itertools import izip_longest
import Queue
import sys
import binascii

try:
    import psycopg2
except ImportError as err:
    print "Module not installed", err
    sys.exit(1)

from psycopg2.extras import DictCursor, RealDictCursor
from dejavu.database import Database


class PostgresDatabase(Database):
    """ Class to interact with Postregres databases.

    The queries should be self evident, but they are documented in the event
    that they aren't :)
    """

    type = "postgresql"

    # The number of hashes to insert at a time
    NUM_HASHES = 10000

    # Tables
    FINGERPRINTS_TABLENAME = "fingerprints"
    SONGS_TABLENAME = "songs"

    # Schema
    DEFAULT_SCHEMA = 'public'

    # Fields
    FIELD_HASH = 'hash'
    FIELD_SONG_ID = 'song_id'
    FIELD_OFFSET = 'time_offset'
    FIELD_SONGNAME = 'song_name'
    FIELD_FINGERPRINTED = 'fingerprinted'

    # creates postgres table if it doesn't exist
    CREATE_FINGERPRINTS_TABLE = """
        CREATE TABLE IF NOT EXISTS %s (
             %s bytea NOT NULL,
             %s uuid NOT NULL,
             %s int NOT NULL,
             CONSTRAINT comp_key UNIQUE (%s, %s, %s),
             FOREIGN KEY (%s) REFERENCES %s(%s)
        );""" % (FINGERPRINTS_TABLENAME,
                 FIELD_HASH,  # actual fingerprint itself
                 FIELD_SONG_ID,  # song id (fkey to songs tables)
                 FIELD_OFFSET,   # offset relative to START of song
                 FIELD_SONG_ID, FIELD_OFFSET, FIELD_HASH,  # unique constraint
                 FIELD_SONG_ID, SONGS_TABLENAME, FIELD_SONG_ID  # foreign key
                )

    # Creates an index on fingerprint itself for webscale
    CREATE_FINGERPRINT_INDEX = """
        DO $$
            BEGIN

            IF NOT EXISTS (
                SELECT 1
                FROM   pg_class c
                JOIN   pg_namespace n ON n.oid = c.relnamespace
                WHERE  c.relname = 'fingerprint_index'
                AND    n.nspname = '%s'
            ) THEN

            CREATE INDEX fingerprint_index ON %s.%s (%s);
            END IF;
        END$$;
        """ % (DEFAULT_SCHEMA,
               DEFAULT_SCHEMA,
               FINGERPRINTS_TABLENAME,
               FIELD_HASH
              )

    # Creates the table that stores song information.
    CREATE_SONGS_TABLE = """
        CREATE TABLE IF NOT EXISTS %s (
            %s uuid DEFAULT uuid_generate_v4() NOT NULL,
            %s varchar(250) NOT NULL,
            %s boolean default FALSE,
            PRIMARY KEY (%s),
            CONSTRAINT uni_que UNIQUE (%s)
        );""" % (SONGS_TABLENAME,
                 FIELD_SONG_ID,  # uuid
                 FIELD_SONGNAME,  # songname when we fingerprinted it
                 FIELD_FINGERPRINTED, # whether we processed the song
                 FIELD_SONG_ID,  # pkey on songid
                 FIELD_SONG_ID,  # unique key on song_id
                )

    # Inserts (ignores duplicates)
    INSERT_FINGERPRINT = """
        INSERT INTO %s (%s, %s, %s)
        values (decode(%%s, 'hex'), %%s, %%s);
        """ % (
            FINGERPRINTS_TABLENAME,
            FIELD_HASH,
            FIELD_SONG_ID,
            FIELD_OFFSET,
        )

    # Inserts song information.
    INSERT_SONG = """
        INSERT INTO %s (%s)
        values (%%s)
        RETURNING %s;
        """ % (
            SONGS_TABLENAME,
            FIELD_SONGNAME,
            FIELD_SONG_ID
        )

    # Select a single fingerprint given a hex value.
    SELECT = """
        SELECT %s, %s
        FROM %s
        WHERE %s = decode(%%s, 'hex');
        """ % (
            FIELD_SONG_ID,
            FIELD_OFFSET,
            FINGERPRINTS_TABLENAME,
            FIELD_HASH
        )

    # Selects multiple fingerprints based on hashes
    SELECT_MULTIPLE = """
        SELECT %s, %s, %s
        FROM %s
        WHERE %s IN (%%s);
        """ % (
            FIELD_HASH,
            FIELD_SONG_ID,
            FIELD_OFFSET,
            FINGERPRINTS_TABLENAME,
            FIELD_HASH
        )

    # Selects all fingerprints from the fingerprints table.
    SELECT_ALL = """
        SELECT %s, %s
        FROM %s;
        """ % (
            FIELD_SONG_ID,
            FIELD_OFFSET,
            FINGERPRINTS_TABLENAME
        )

    # Selects a given song.
    SELECT_SONG = """
        SELECT %s
        FROM %s
        WHERE %s = %%s
        """ % (
            FIELD_SONGNAME,
            SONGS_TABLENAME,
            FIELD_SONG_ID
        )

    # Returns the number of fingerprints
    SELECT_NUM_FINGERPRINTS = """
        SELECT COUNT(*) as n
        FROM %s
        """ % (
            FINGERPRINTS_TABLENAME
        )

    # Selects unique song ids
    SELECT_UNIQUE_SONG_IDS = """
        SELECT COUNT(DISTINCT %s) as n
        FROM %s
        WHERE %s = True;
        """ % (
            FIELD_SONG_ID,
            SONGS_TABLENAME,
            FIELD_FINGERPRINTED
        )

    # Selects all FINGERPRINTED songs.
    SELECT_SONGS = """
        SELECT %s, %s
        FROM %s WHERE %s = True;
        """ % (
            FIELD_SONG_ID,
            FIELD_SONGNAME,
            SONGS_TABLENAME,
            FIELD_FINGERPRINTED
        )

    # Drops the fingerprints table (removes EVERYTHING!)
    DROP_FINGERPRINTS = """
        DROP TABLE IF EXISTS %s;""" % (
            FINGERPRINTS_TABLENAME
        )

    # Drops the songs table (removes EVERYTHING!)
    DROP_SONGS = """
        DROP TABLE IF EXISTS %s;
        """ % (
            SONGS_TABLENAME
        )

    # Updates a fingerprinted song
    UPDATE_SONG_FINGERPRINTED = """
        UPDATE %s
        SET %s = True
        WHERE %s = %%s
        """ % (
            SONGS_TABLENAME,
            FIELD_FINGERPRINTED,
            FIELD_SONG_ID
        )

    # Deletes all unfingerprinted songs.
    DELETE_UNFINGERPRINTED = """
        DELETE
        FROM %s
        WHERE %s = False;
        """ % (
            SONGS_TABLENAME,
            FIELD_FINGERPRINTED
        )

    def __init__(self, **options):
        """ Creates the DB layout, creates connection, etc.
        """
        super(PostgresDatabase, self).__init__()
        self.cursor = cursor_factory(**options)
        self._options = options

    def after_fork(self):
        """
        Clear the cursor cache, we don't want any stale connections from
        the previous process.
        """
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
            cur.execute(self.CREATE_FINGERPRINT_INDEX)

    def empty(self):
        """
        Drops tables created by dejavu and then creates them again
        by calling `PostgresDatabase.setup`.

        This will result in a loss of data, so this might not
        be what you want.
        """
        with self.cursor() as cur:
            cur.execute(self.DROP_FINGERPRINTS)
            cur.execute(self.DROP_SONGS)
        self.setup()

    def delete_unfingerprinted_songs(self):
        """
        Removes all songs that have no fingerprints associated with them.
        This might not be applicable either.
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
        Returns number of fingerprints present.
        """
        with self.cursor() as cur:
            cur.execute(self.SELECT_NUM_FINGERPRINTS)

            for count, in cur:
                return count
            return 0

    def set_song_fingerprinted(self, sid):
        """
        Toggles fingerprinted flag to TRUE once a song has been completely
        fingerprinted in the database.
        """
        with self.cursor() as cur:
            cur.execute(self.UPDATE_SONG_FINGERPRINTED, (sid,))

    def get_songs(self):
        """
        Generator to return songs that have the fingerprinted
        flag set TRUE, ie, they are completely processed.
        """
        with self.cursor(cursor_type=RealDictCursor) as cur:
            cur.execute(self.SELECT_SONGS)
            for row in cur:
                yield row

    def get_song_by_id(self, sid):
        """
        Returns song by its ID.
        """
        with self.cursor(cursor_type=RealDictCursor) as cur:
            cur.execute(self.SELECT_SONG, (sid,))
            return cur.fetchone()

    def insert(self, bhash, sid, offset):
        """
        Insert a (sha1, song_id, offset) row into database.
        """
        with self.cursor() as cur:
            cur.execute(self.INSERT_FINGERPRINT, bhash, sid, offset)

    def insert_song(self, songname):
        """
        Inserts song in the database and returns the ID of the inserted record.
        """
        with self.cursor() as cur:
            cur.execute(self.INSERT_SONG, (songname, ))
            return cur.fetchone()[0]

    def query(self, bhash):
        """
        Return all tuples associated with hash.

        If hash is None, returns all entries in the
        database (be careful with that one!).
        """
        query = self.SELECT
        if not bhash:
            query = self.SELECT_ALL

        with self.cursor() as cur:
            cur.execute(query)
            for sid, offset in cur:
                yield (sid, offset)

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
        for bhash, offset in hashes:
            values.append((bhash, sid, offset))

        with self.cursor() as cur:
            for split_values in grouper(values, self.NUM_HASHES):
                cur.executemany(self.INSERT_FINGERPRINT, split_values)

    def return_matches(self, hashes):
        """
        Return the (song_id, offset_diff) tuples associated with
        a list of (sha1, sample_offset) values as a generator.
        """
        # Create a dictionary of hash => offset pairs for later lookups
        mapper = {}
        for bhash, offset in hashes:
            mapper[bhash.upper()] = offset

        # Get an iteratable of all the hashes we need
        values = mapper.keys()

        with self.cursor() as cur:
            for split_values in grouper(values, self.NUM_HASHES):
                # Create our IN part of the query
                query = self.SELECT_MULTIPLE
                query = query % ', '.join(["decode(%s, 'hex')"] * \
                    len(split_values))

                cur.execute(query, split_values)

                for bhash, sid, offset in cur:
                    bhash = binascii.hexlify(bhash).upper()
                    # (sid, db_offset - song_sampled_offset)
                    yield (sid, offset - mapper[bhash])

    def __getstate__(self):
        return (self._options,)

    def __setstate__(self, state):
        self._options, = state
        self.cursor = cursor_factory(**self._options)


def grouper(iterable, num, fillvalue=None):
    """ Groups values.
    """
    args = [iter(iterable)] * num
    return (filter(None, values) for values
            in izip_longest(fillvalue=fillvalue, *args))


def cursor_factory(**factory_options):
    """ Initializes the cursor, ex passes hostname, port,
    etc.
    """
    def cursor(**options):
        """ Builds a cursor.
        """
        options.update(factory_options)
        return Cursor(**options)
    return cursor


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

    def __init__(self, cursor_type=DictCursor, **options):
        super(Cursor, self).__init__()

        try:
            conn = self._cache.get_nowait()
        except Queue.Empty:
            conn = psycopg2.connect(**options)
        else:
            # Ping the connection before using it from the cache.
            conn.cursor().execute('SELECT 1')

        self.conn = conn
        self.cursor_type = cursor_type

    @classmethod
    def clear_cache(cls):
        """ Clears the cache.
        """
        cls._cache = Queue.Queue(maxsize=5)

    def __enter__(self):
        self.cursor = self.conn.cursor(cursor_factory=self.cursor_type)
        return self.cursor

    def __exit__(self, extype, exvalue, traceback):
        # if we had a Postgres related error we try to rollback the cursor.
        if extype in [psycopg2.DatabaseError, psycopg2.InternalError]:
            self.conn.rollback()

        self.cursor.close()
        self.conn.commit()

        # Put it back on the queue
        try:
            self._cache.put_nowait(self.conn)
        except Queue.Full:
            self.conn.close()
