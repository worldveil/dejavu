import pymongo
from dejavu.base_classes.base_database import BaseDatabase
from typing import Dict, List, Tuple

class MongoDatabase(BaseDatabase):
    def __init__(self, **options):
        super().__init__()
        self.options = options

    def setup(self):
        self.client = pymongo.MongoClient(self.options.get('uri', 'mongodb://mongodb:27017/'))
        self.db = self.client[self.options.get('database', 'dejavu')]

    def empty(self):
        self.client.drop_database(self.options.get('database', 'dejavu'))

    def delete_unfingerprinted_songs(self):
        self.db['songs'].delete_many({'isFingerprinted': False})

    def get_num_songs(self):
        return self.db['songs'].count_documents()

    def get_num_fingerprints(self):
        return self.db['fingerprints'].count_documents()

    def set_song_fingerprinted(self, song_id):
        self.db['songs'].update_one({'_id': song_id}, {'$set': {'isFingerPrinted': True}})

    def get_songs(self):
        t = self.db['songs'].find()
        return list(t)

    def get_song_by_id(self, song_id):
        return self.db['songs'].find_one({'_id': song_id})

    def insert(self, fingerprint, song_id, offset):
        self.db['fingerprints'].insert_one({'hash': fingerprint, 'song_id': song_id, 'offset': offset})

    def insert_song(self, song_name, file_hash, total_hashes):
        result = self.db['songs'].insert_one({'song_name': song_name, 'file_sha1': file_hash, 'total_hashes': total_hashes})
        return result.inserted_id

    def query(self, fingerprint):
        return self.db['fingerprints'].find({'fingerprint': fingerprint})

    def get_iterable_kv_pairs(self):
        return self.db['fingerprints'].find({})

    def insert_hashes(self, song_id: int, hashes: List[Tuple[str, int]], batch_size = 1000):
        to_be_inserted = []
        for (hash, offset) in hashes:
            to_be_inserted.append({'song_id': song_id, 'hash': hash, 'offset': int(offset)})
        self.db['fingerprints'].insert_many(to_be_inserted)

    def return_matches(self, hashes: List[Tuple[str, int]], batch_size: int = 1000) \
            -> Tuple[List[Tuple[int, int]], Dict[int, int]]:
        """
        Searches the database for pairs of (hash, offset) values.

        :param hashes: A sequence of tuples in the format (hash, offset)
            - hash: Part of a sha1 hash, in hexadecimal format
            - offset: Offset this hash was created from/at.
        :param batch_size: number of query's batches.
        :return: a list of (sid, offset_difference) tuples and a
        dictionary with the amount of hashes matched (not considering
        duplicated hashes) in each song.
            - song id: Song identifier
            - offset_difference: (database_offset - sampled_offset)
        """
        mapper = {}
        for hsh, offset in hashes:
            if hsh in mapper.keys():
                mapper[hsh].append(offset)
            else:
                mapper[hsh] = [offset]

        

        values = list(mapper.keys())
        dedup_hashes = {}

        return_value = []
        results = self.db['fingerprints'].find({'hash': {'$in': values}})
        for result in results:
            hsh = result.get('hash')
            sid = result.get('song_id')
            offset = result.get('offset')
            if sid not in dedup_hashes.keys():
                dedup_hashes[sid] = 1
            else:
                dedup_hashes[sid] += 1
            #  we now evaluate all offset for each  hash matched
            for song_sampled_offset in mapper[hsh]:
                return_value.append((sid, offset - song_sampled_offset))
        return return_value, dedup_hashes

    def delete_songs_by_id(self, song_ids: List[int], batch_size: int = 1000) -> None:
        self.db['fingerprints'].delete({'song_id': {'$in': song_ids}})
        self.db['songs'].delete({'_id': {'$in': song_ids}})
