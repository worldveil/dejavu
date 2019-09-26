import abc

from dejavu.base_classes.base_database import BaseDatabase


class CommonDatabase(BaseDatabase, metaclass=abc.ABCMeta):
    # Since several methods across different databases are actually just the same
    # I've built this class with the idea to reuse that logic instead of copy pasting
    # over and over the same code.

    def __init__(self):
        super().__init__()

    def before_fork(self):
        """
        Called before the database instance is given to the new process
        """
        pass

    def after_fork(self):
        """
        Called after the database instance has been given to the new process

        This will be called in the new process.
        """
        pass

    def setup(self):
        """
        Called on creation or shortly afterwards.
        """
        with self.cursor() as cur:
            cur.execute(self.CREATE_SONGS_TABLE)
            cur.execute(self.CREATE_FINGERPRINTS_TABLE)
            cur.execute(self.DELETE_UNFINGERPRINTED)

    def empty(self):
        """
        Called when the database should be cleared of all data.
        """
        with self.cursor() as cur:
            cur.execute(self.DROP_FINGERPRINTS)
            cur.execute(self.DROP_SONGS)

        self.setup()

    def delete_unfingerprinted_songs(self):
        """
        Called to remove any song entries that do not have any fingerprints
        associated with them.
        """
        with self.cursor() as cur:
            cur.execute(self.DELETE_UNFINGERPRINTED)

    def get_num_songs(self):
        """
        Returns the amount of songs in the database.
        """
        with self.cursor() as cur:
            cur.execute(self.SELECT_UNIQUE_SONG_IDS)
            count = cur.fetchone()[0] if cur.rowcount != 0 else 0

        return count

    def get_num_fingerprints(self):
        """
        Returns the number of fingerprints in the database.
        """
        with self.cursor() as cur:
            cur.execute(self.SELECT_NUM_FINGERPRINTS)
            count = cur.fetchone()[0] if cur.rowcount != 0 else 0

        return count

    def set_song_fingerprinted(self, sid):
        """
        Sets a specific song as having all fingerprints in the database.

        sid: Song identifier
        """
        with self.cursor() as cur:
            cur.execute(self.UPDATE_SONG_FINGERPRINTED, (sid,))

    def get_songs(self):
        """
        Returns all fully fingerprinted songs in the database. Result must be a Dictionary.
        """
        with self.cursor(dictionary=True) as cur:
            cur.execute(self.SELECT_SONGS)
            for row in cur:
                yield row

    def get_song_by_id(self, sid):
        """
        Return a song by its identifier. Result must be a Dictionary.
        sid: Song identifier
        """
        with self.cursor(dictionary=True) as cur:
            cur.execute(self.SELECT_SONG, (sid,))
            return cur.fetchone()

    def insert(self, fingerprint, sid, offset):
        """
        Inserts a single fingerprint into the database.

          fingerprint: Part of a sha1 hash, in hexadecimal format
           sid: Song identifier this fingerprint is off
        offset: The offset this fingerprint is from
        """
        with self.cursor() as cur:
            cur.execute(self.INSERT_FINGERPRINT, (fingerprint, sid, offset))

    @abc.abstractmethod
    def insert_song(self, song_name):
        """
        Inserts a song name into the database, returns the new
        identifier of the song.

        song_name: The name of the song.
        """
        pass

    def query(self, fingerprint):
        """
        Returns all matching fingerprint entries associated with
        the given fingerprint as parameter.

        fingerprint: Part of a sha1 hash, in hexadecimal format
        """
        if fingerprint:
            with self.cursor() as cur:
                cur.execute(self.SELECT, (fingerprint,))
                for sid, offset in cur:
                    yield (sid, offset)
        else:  # select all if no key
            with self.cursor() as cur:
                cur.execute(self.SELECT_ALL)
                for sid, offset in cur:
                    yield (sid, offset)

    def get_iterable_kv_pairs(self):
        """
        Returns all fingerprints in the database.
        """
        return self.query(None)

    def insert_hashes(self, sid, hashes, batch=1000):
        """
        Insert a multitude of fingerprints.

           sid: Song identifier the fingerprints belong to
        hashes: A sequence of tuples in the format (hash, offset)
        -   hash: Part of a sha1 hash, in hexadecimal format
        - offset: Offset this hash was created from/at.
        """
        values = [(sid, hsh, int(offset)) for hsh, offset in hashes]

        with self.cursor() as cur:
            for index in range(0, len(hashes), batch):
                cur.executemany(self.INSERT_FINGERPRINT, values[index: index + batch])

    def return_matches(self, hashes, batch=1000):
        """
        Searches the database for pairs of (hash, offset) values.

        hashes: A sequence of tuples in the format (hash, offset)
        -   hash: Part of a sha1 hash, in hexadecimal format
        - offset: Offset this hash was created from/at.

        Returns a sequence of (sid, offset_difference) tuples.

                      sid: Song identifier
        offset_difference: (offset - database_offset)
        """
        # Create a dictionary of hash => offset pairs for later lookups
        mapper = {}
        for hsh, offset in hashes:
            mapper[hsh.upper()] = offset

        # Get an iterable of all the hashes we need
        values = list(mapper.keys())

        with self.cursor() as cur:
            for index in range(0, len(values), batch):
                # Create our IN part of the query
                query = self.SELECT_MULTIPLE
                query = query % ', '.join([self.IN_MATCH] * len(values[index: index + batch]))

                cur.execute(query, values[index: index + batch])

                for hsh, sid, offset in cur:
                    # (sid, db_offset - song_sampled_offset)
                    yield (sid, offset - mapper[hsh])
