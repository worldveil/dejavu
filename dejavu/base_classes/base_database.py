import abc
import importlib
from typing import Dict

from dejavu.config.settings import DATABASES


class BaseDatabase(object, metaclass=abc.ABCMeta):
    # Name of your Database subclass, this is used in configuration
    # to refer to your class
    type = None

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
        pass

    @abc.abstractmethod
    def empty(self):
        """
        Called when the database should be cleared of all data.
        """
        pass

    @abc.abstractmethod
    def delete_unfingerprinted_songs(self):
        """
        Called to remove any song entries that do not have any fingerprints
        associated with them.
        """
        pass

    @abc.abstractmethod
    def get_num_songs(self):
        """
        Returns the amount of songs in the database.
        """
        pass

    @abc.abstractmethod
    def get_num_fingerprints(self):
        """
        Returns the number of fingerprints in the database.
        """
        pass

    @abc.abstractmethod
    def set_song_fingerprinted(self, sid):
        """
        Sets a specific song as having all fingerprints in the database.

        sid: Song identifier
        """
        pass

    @abc.abstractmethod
    def get_songs(self) -> Dict[str, str]:
        """
        Returns all fully fingerprinted songs in the database. Result must be a Dictionary.
        """
        pass

    @abc.abstractmethod
    def get_song_by_id(self, sid) -> Dict[str, str]:
        """
        Return a song by its identifier. Result must be a Dictionary.
        sid: Song identifier
        """
        pass

    @abc.abstractmethod
    def insert(self, hash, sid, offset):
        """
        Inserts a single fingerprint into the database.

          hash: Part of a sha1 hash, in hexadecimal format
           sid: Song identifier this fingerprint is off
        offset: The offset this hash is from
        """
        pass

    @abc.abstractmethod
    def insert_song(self, song_name):
        """
        Inserts a song name into the database, returns the new
        identifier of the song.

        song_name: The name of the song.
        """
        pass

    @abc.abstractmethod
    def query(self, hash):
        """
        Returns all matching fingerprint entries associated with
        the given hash as parameter.

        hash: Part of a sha1 hash, in hexadecimal format
        """
        pass

    @abc.abstractmethod
    def get_iterable_kv_pairs(self):
        """
        Returns all fingerprints in the database.
        """
        pass

    @abc.abstractmethod
    def insert_hashes(self, sid, hashes, batch=1000):
        """
        Insert a multitude of fingerprints.

           sid: Song identifier the fingerprints belong to
        hashes: A sequence of tuples in the format (hash, offset)
        -   hash: Part of a sha1 hash, in hexadecimal format
        - offset: Offset this hash was created from/at.
        """

    @abc.abstractmethod
    def return_matches(self, hashes):
        """
        Searches the database for pairs of (hash, offset) values.

        hashes: A sequence of tuples in the format (hash, offset)
        -   hash: Part of a sha1 hash, in hexadecimal format
        - offset: Offset this hash was created from/at.

        Returns a sequence of (sid, offset_difference) tuples.

                      sid: Song identifier
        offset_difference: (offset - database_offset)
        """
        pass


def get_database(database_type="mysql"):
    try:
        path, db_class_name = DATABASES[database_type]
        db_module = importlib.import_module(path)
        db_class = getattr(db_module, db_class_name)
        return db_class
    except (ImportError, KeyError):
        raise TypeError("Unsupported database type supplied.")
