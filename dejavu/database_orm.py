
from dejavu.database import Database, grouper

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.sql.schema import ForeignKey

Base = declarative_base()


class Song(Base):
    __tablename__ = "songs"
    id = Column(Integer, primary_key=True)
    song_name = Column(String(255))
    fingerprinted = Column(Integer, default=0)

class Fingerprint(Base):
    __tablename__ = "fingerprints"
    id = Column(Integer, primary_key=True)
    fingerprint_hash = Column(String(100))
    song_id = Column(Integer, ForeignKey('songs.id'))
    offset = Column(Integer)


def row2dict(row):
    d = {}
    for column in row.__table__.columns:
        d[column.name] = getattr(row, column.name)

    return d

class ORMDatabase(Database):

    type = "orm"
    FIELD_SONGNAME = "song_name"

    def __init__(self, **options):
        super(ORMDatabase, self).__init__()
        dburi = options.get("database_uri")
        self._engine = create_engine(dburi, echo=False)
        self._DBSession = scoped_session(sessionmaker())
        self._DBSession.remove()
        self._DBSession.configure(bind=self._engine, autoflush=False,
                                  expire_on_commit=False)

    def after_fork(self):
        # Clear the cursor cache, we don't want any stale connections from
        # the previous process.
        pass

    def setup(self):
        """
        Creates any non-existing tables required for dejavu to function.

        This also removes all songs that have been added but have no
        fingerprints associated with them.
        """
        Base.metadata.create_all(self._engine)

    def empty(self):
        """
        Drops tables created by dejavu and then creates them again
        by calling `SQLDatabase.setup`.

        .. warning:
            This will result in a loss of data
        """
        Base.metadata.drop_all(self._engine)

    def delete_unfingerprinted_songs(self):
        """
        Removes all songs that have no fingerprints associated with them.
        """
        return self._DBSession.query(Song).filter_by(fingerprinted=0).all()

    def get_num_songs(self):
        """
        Returns number of songs the database has fingerprinted.
        """
        return self._DBSession.query(Song).filter_by(fingerprinted=1).count()

    def get_num_fingerprints(self):
        """
        Returns number of fingerprints the database has fingerprinted.
        """
        return self._DBSession.query(Fingerprint.id).count()

    def set_song_fingerprinted(self, sid):
        """
        Set the fingerprinted flag to TRUE (1) once a song has been completely
        fingerprinted in the database.
        """
        song = self._DBSession.query(Song).get(sid)
        song.fingerprinted = 1
        self._DBSession.commit()

    def get_songs(self):
        """
        Return songs that have the fingerprinted flag set TRUE (1).
        """
        return [row2dict(r) for r in self._DBSession.query(Song).filter(Song.fingerprinted == 1).all()]

    def get_song_by_id(self, sid):
        """
        Returns song by its ID.
        """
        return row2dict(self._DBSession.query(Song).get(sid))

    def insert(self, hash, sid, offset):
        """
        Insert a (sha1, song_id, offset) row into database.
        """
        new_fingerprint = Fingerprint(fingerprint_hash=hash, song_id=sid,
                                      offset=offset)
        self._DBSession.add(new_fingerprint)
        self._DBSession.commit()

    def insert_song(self, songname):
        """
        Inserts song in the database and returns the ID of the inserted record.
        """
        new_song = Song(song_name=songname, fingerprinted=0)
        self._DBSession.add(new_song)
        self._DBSession.commit()
        return new_song.id

    def query(self, hash):
        """
        Return all tuples associated with hash.

        If hash is None, returns all entries in the
        database (be careful with that one!).
        """
        return self._DBSession.query(Fingerprint).filter(Fingerprint.hash == hash).all()

    def get_iterable_kv_pairs(self):
        """
        Returns all tuples in database.
        """
        return self._DBSession.query(Fingerprint).all()

    def insert_hashes(self, sid, hashes):
        """
        Insert series of hash => song_id, offset
        values into the database.
        """
        for hash, offset in hashes:
            new_fingerprint = Fingerprint(fingerprint_hash=hash,
                                          song_id=sid,
                                          offset=offset)
            self._DBSession.add(new_fingerprint)
        self._DBSession.commit()

    def return_matches(self, hashes):
        """
        Return the (song_id, offset_diff) tuples associated with
        a list of (sha1, sample_offset) values.
        """
        # Create a dictionary of hash => offset pairs for later lookups
        mapper = {}
        for hash, offset in hashes:
            mapper[hash] = offset

        # Get an iteratable of all the hashes we need
        values = mapper.keys()
        for split_values in grouper(values, 900):
            results = self._DBSession.query(Fingerprint.fingerprint_hash, Fingerprint.song_id,
                                  Fingerprint.offset).filter(Fingerprint.fingerprint_hash.in_(split_values))
            for hash, sid, offset in results:
                # (sid, db_offset - song_sampled_offset)
                yield (sid, offset - mapper[hash])
