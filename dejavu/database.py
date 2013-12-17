from __future__ import absolute_import
from binascii import unhexlify

class Database(object):
    def __init__(self):
        super(Database, self).__init__()


class SQLDatabase(Database):
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

    # config keys
    CONNECTION = "connection"
    KEY_USERNAME = "username"
    KEY_DATABASE = "database"
    KEY_PASSWORD = "password"
    KEY_HOSTNAME = "hostname"

    # tables
    FINGERPRINTS_TABLENAME = "fingerprints"
    SONGS_TABLENAME = "songs"

    # fields
    FIELD_HASH = "hash"
    FIELD_SONG_ID = "song_id"
    FIELD_OFFSET = "offset"
    FIELD_SONGNAME = "song_name"
    FIELD_FINGERPRINTED = "fingerprinted"

    # creates
    CREATE_FINGERPRINTS_TABLE = """
        CREATE TABLE IF NOT EXISTS `%s` (
             `%s` binary(10) not null,
             `%s` mediumint unsigned not null,
             `%s` int unsigned not null,
         INDEX(%s),
         UNIQUE(%s, %s, %s)
    );""" % (
        FINGERPRINTS_TABLENAME, FIELD_HASH,
        FIELD_SONG_ID, FIELD_OFFSET, FIELD_HASH,
        FIELD_SONG_ID, FIELD_OFFSET, FIELD_HASH,
    )

    CREATE_SONGS_TABLE = """
        CREATE TABLE IF NOT EXISTS `%s` (
            `%s` mediumint unsigned not null auto_increment,
            `%s` varchar(250) not null,
            `%s` tinyint default 0,
        PRIMARY KEY (`%s`),
        UNIQUE KEY `%s` (`%s`)
    );""" % (
        SONGS_TABLENAME, FIELD_SONG_ID, FIELD_SONGNAME, FIELD_FINGERPRINTED,
        FIELD_SONG_ID, FIELD_SONG_ID, FIELD_SONG_ID,
    )

    # inserts (ignores duplicates)
    INSERT_FINGERPRINT = """
        INSERT IGNORE INTO %s (%s, %s, %s) VALUES
            (UNHEX(%%s), %%s, %%s);
    """ % (FINGERPRINTS_TABLENAME, FIELD_HASH, FIELD_SONG_ID, FIELD_OFFSET)

    INSERT_SONG = "INSERT INTO %s (%s) VALUES (%%s);" % (
        SONGS_TABLENAME, FIELD_SONGNAME)

    # selects
    SELECT = """
        SELECT %s, %s FROM %s WHERE %s = UNHEX(%%s);
    """ % (FIELD_SONG_ID, FIELD_OFFSET, FINGERPRINTS_TABLENAME, FIELD_HASH)

    SELECT_MULTIPLE = """
        SELECT HEX(%s), %s, %s FROM %s WHERE %s IN (%%s);
    """ % (FIELD_HASH, FIELD_SONG_ID, FIELD_OFFSET,
           FINGERPRINTS_TABLENAME, FIELD_HASH)

    SELECT_ALL = """
        SELECT %s, %s FROM %s;
    """ % (FIELD_SONG_ID, FIELD_OFFSET, FINGERPRINTS_TABLENAME)

    SELECT_SONG = """
        SELECT %s FROM %s WHERE %s = %%s
    """ % (FIELD_SONGNAME, SONGS_TABLENAME, FIELD_SONG_ID)

    SELECT_NUM_FINGERPRINTS = """
        SELECT COUNT(*) as n FROM %s
    """ % (FINGERPRINTS_TABLENAME)

    SELECT_UNIQUE_SONG_IDS = """
        SELECT COUNT(DISTINCT %s) as n FROM %s WHERE %s = 1;
    """ % (FIELD_SONG_ID, SONGS_TABLENAME, FIELD_FINGERPRINTED)

    SELECT_SONGS = """
        SELECT %s, %s FROM %s WHERE %s = 1;
    """ % (FIELD_SONG_ID, FIELD_SONGNAME, SONGS_TABLENAME, FIELD_FINGERPRINTED)

    # drops
    DROP_FINGERPRINTS = "DROP TABLE IF EXISTS %s;" % FINGERPRINTS_TABLENAME
    DROP_SONGS = "DROP TABLE IF EXISTS %s;" % SONGS_TABLENAME

    # update
    UPDATE_SONG_FINGERPRINTED = """
        UPDATE %s SET %s = 1 WHERE %s = %%s
    """ % (SONGS_TABLENAME, FIELD_FINGERPRINTED, FIELD_SONG_ID)

    # delete
    DELETE_UNFINGERPRINTED = """
        DELETE FROM %s WHERE %s = 0;
    """ % (SONGS_TABLENAME, FIELD_FINGERPRINTED)

    DELETE_ORPHANS = """
        delete from fingerprints
        where not exists (
            select * from songs where fingerprints.song_id  = songs.song_id
        );
    """

    def __init__(self, cursor):
        super(SQLDatabase, self).__init__()
        self.cursor = cursor

    def setup(self):
        with self.cursor() as cur:
            cur.execute(self.CREATE_FINGERPRINTS_TABLE)
            cur.execute(self.CREATE_SONGS_TABLE)
            cur.execute(self.DELETE_UNFINGERPRINTED)

    def empty(self):
        """
            Drops all tables and re-adds them. Be carfeul with this!
        """
        with self.cursor() as cur:
            cur.execute(self.DROP_FINGERPRINTS)
            cur.execute(self.DROP_SONGS)

        self.setup()

    def delete_orphans(self):
        # TODO: SQLDatabase.DELETE_ORPHANS is not
        # performant enough, need better query to
        # delete fingerprints for which no song is tied to.

        # with self.cursor() as cur:
        #   cur.execute(self.DELETE_ORPHANS)
        pass

    def delete_unfingerprinted_songs(self):
        with self.cursor() as cur:
            cur.execute(self.DELETE_UNFINGERPRINTED)

    def get_num_songs(self):
        """
        Returns number of songs the database has fingerprinted.
        """
        with self.cursor() as cur:
            cur.execute(self.SELECT_UNIQUE_SONG_IDS)

            for row in cur:
                return row['n']

    def get_num_fingerprints(self):
        """
        Returns number of fingerprints the database has fingerprinted.
        """
        with self.cursor() as cur:
            cur.execute(self.SELECT_NUM_FINGERPRINTS)

            for row in cur:
                return row['n']

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
            cur.execute(self.INSERT_FINGERPRINT, (hash, sid, offset))

    def insert_song(self, songname):
        """
        Inserts song in the database and returns the ID of the inserted record.
        """
        with self.cursor() as cur:
            cur.execute(self.INSERT_SONG, (songname,))
            return cur.lastrowid

    def query(self, hash):
        """
        Return all tuples associated with hash.

        If hash is None, returns all entries in the
        database (be careful with that one!).
        """
        # select all if no key
        query = self.SELECT_ALL if hash is None else self.SELECT

        with self.cursor() as cur:
            cur.execute(query)
            for row in cur:
                yield (row[self.FIELD_SONG_ID], row[self.FIELD_OFFSET])

    def get_iterable_kv_pairs(self):
        """
        Returns all tuples in database.
        """
        return self.query(None)

    def insert_hashes(self, hashes):
        """
        Insert series of hash => song_id, offset
        values into the database.
        """
        # TODO: Fix this when hashes will be a new format.
        values = []
        for hash, (sid, offset) in hashes:
            values.append((hash, sid, offset))

        with self.cursor() as cur:
            cur.executemany(self.INSERT_FINGERPRINT, values)

    def return_matches(self, hashes):
        """
            Return the (song_id, offset_diff) tuples associated with
            a list of

                sha1 => (None, sample_offset)

            values.
        """
        from pymysql.cursors import Cursor
        # Create a dictionary of hash => offset pairs for later lookups
        mapper = {}
        for hash, (_, offset) in hashes:
            mapper[hash.upper()] = offset

        # Get an iteratable of all the hashes we need
        values = mapper.keys()

        with self.cursor(cursor_type=Cursor) as cur:
            for split_values in grouper(values, 1000):
                # Create our IN part of the query
                query = self.SELECT_MULTIPLE
                query = query % ', '.join(['UNHEX(%s)'] * len(split_values))

                cur.execute(query, split_values)

                for hash, sid, offset in cur:
                    # (sid, db_offset - song_sampled_offset)
                    yield (sid, offset - mapper[hash])


from itertools import izip_longest
def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return izip_longest(fillvalue=fillvalue, *args)
