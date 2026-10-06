from typing import Dict, List, Tuple

import numpy as np

from dejavu.database_handler.postgres_database import PostgreSQLDatabase
from dejavu.fpstore import FpStore


class PostgreSQLCompactDatabase(PostgreSQLDatabase):
    """
    PostgreSQL with the fingerprints kept in the compact store (dejavu.fpstore) instead of the fingerprints
    table. The songs table is the same as PostgreSQLDatabase's.

    Fingerprints are hash32 values (fingerprint.fingerprint_hash32) rather than sha1 strings, so songs
    fingerprinted with the "postgres" type have to be fingerprinted again to be found here.
    """
    type = "postgres_compact"
    compact = True

    def __init__(self, **options):
        super().__init__(**options)
        self.store = FpStore(self.cursor)

    def setup(self) -> None:
        """
        Called on creation or shortly afterwards.
        """
        with self.cursor() as cur:
            cur.execute(self.CREATE_SONGS_TABLE)
            cur.execute(self.DELETE_UNFINGERPRINTED)
        self.store.setup()

    def empty(self) -> None:
        """
        Called when the database should be cleared of all data.
        """
        self.store.drop()
        with self.cursor() as cur:
            cur.execute(self.DROP_SONGS)

        self.setup()

    def get_num_fingerprints(self) -> int:
        """
        Returns the fingerprints' count stored.

        :return: the number of fingerprints in the database.
        """
        return self.store.num_postings()

    def insert_hashes(self, song_id: int, hashes, batch_size: int = 1000) -> None:
        """
        Insert a song's fingerprints into the compact store, and flag the song fingerprinted in the same
        transaction.

        :param song_id: Song identifier the fingerprints belong to
        :param hashes: (hash32, offset) pairs, as a sequence or an (n, 2) array.
        :param batch_size: unused, a song is written in one transaction.
        """
        pairs = np.asarray(hashes, dtype=np.int64).reshape(-1, 2)
        if len(pairs):
            self.store.add_songs([(song_id, pairs[:, 0], pairs[:, 1])])

    def delete_songs_by_id(self, song_ids: List[int], batch_size: int = 1000) -> None:
        """
        Given a list of song ids it deletes all songs specified and their corresponding fingerprints.

        :param song_ids: song ids to be deleted from the database.
        :param batch_size: number of query's batches.
        """
        # Postings first: a songs row left without postings never matches, postings left without a
        # songs row would.
        self.store.remove_songs(song_ids)
        super().delete_songs_by_id(song_ids, batch_size)

    def search(self, hashes: np.ndarray, offsets: np.ndarray) -> Tuple[List[Dict[str, any]], Dict[str, any]]:
        """
        Recognizes a query from its fingerprints.

        :param hashes: hash32 values of the query, as fingerprint_hash32 returns them.
        :param offsets: offsets the hashes were created at.
        :return: the results, with the same keys as Dejavu.align_matches, and search statistics.
        """
        return self.store.search(hashes, offsets)

    def return_matches(self, hashes, batch_size: int = 1000):
        raise NotImplementedError("the compact store is searched with search(), which also aligns the matches")

    def insert(self, fingerprint, song_id: int, offset: int):
        raise NotImplementedError("the compact store writes a song's fingerprints together, use insert_hashes()")

    def query(self, fingerprint=None):
        raise NotImplementedError("the compact store keeps fingerprints in blobs, not one row each")

    def __setstate__(self, state):
        super().__setstate__(state)
        self.store = FpStore(self.cursor)
