import os
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import groupby
from time import time
from typing import Dict, List, Tuple

import dejavu.logic.decoder as decoder
from dejavu.base_classes.base_database import get_database
from dejavu.config.settings import (DEFAULT_FS, DEFAULT_OVERLAP_RATIO,
                                    DEFAULT_WINDOW_SIZE, FIELD_FILE_SHA1,
                                    FIELD_TOTAL_HASHES,
                                    FINGERPRINTED_CONFIDENCE,
                                    FINGERPRINTED_HASHES, HASHES_MATCHED,
                                    INPUT_CONFIDENCE, INPUT_HASHES, OFFSET,
                                    OFFSET_SECS, SONG_ID, SONG_NAME, TOPN)
from dejavu.logic.fingerprint import fingerprint


class Dejavu:
    def __init__(self, config):
        self.config = config

        # initialize db
        db_cls = get_database(config.get("database_type", "mysql").lower())

        self.db = db_cls(**config.get("database", {}))
        self.db.setup()

        # if we should limit seconds fingerprinted,
        # None|-1 means use entire track
        self.limit = self.config.get("fingerprint_limit", None)
        if self.limit == -1:  # for JSON compatibility
            self.limit = None
        self.songs = None
        self.songhashes_set = set()  # to know which ones we've computed before
        self.__load_fingerprinted_audio_hashes()

    def __load_fingerprinted_audio_hashes(self) -> None:
        """
        Keeps a dictionary with the hashes of the fingerprinted songs, in that way is possible to check
        whether or not an audio file was already processed.
        """
        # get songs previously indexed
        self.songs = self.db.get_songs()
        self.songhashes_set = set()  # to know which ones we've computed before
        for song in self.songs:
            self.songhashes_set.add(song[FIELD_FILE_SHA1])

    def get_fingerprinted_songs(self) -> List[Dict[str, any]]:
        """
        To pull all fingerprinted songs from the database.

        :return: a list of fingerprinted audios from the database.
        """
        return self.db.get_songs()

    def delete_songs_by_id(self, song_ids: List[int]) -> None:
        """
        Deletes all audios given their ids.

        :param song_ids: song ids to delete from the database.
        """
        self.db.delete_songs_by_id(song_ids)

    def fingerprint_directory(self, path: str, extensions: str, nprocesses: int = None) -> None:
        """
        Given a directory and a set of extensions it fingerprints all files that match each extension specified.

        :param path: path to the directory.
        :param extensions: list of file extensions to consider.
        :param nprocesses: amount of processes to fingerprint the files within the directory.
        """
        nprocesses = int(nprocesses) if nprocesses is not None else None

        with ProcessPoolExecutor(max_workers=nprocesses) as executor:
            futures = []
            for filename, _ in decoder.find_files_g(path, extensions):
                # don't refingerprint already fingerprinted files
                if decoder.unique_hash(filename) in self.songhashes_set:
                    print(f"{filename} already fingerprinted, continuing...")
                else:
                    futures.append(
                        executor.submit(
                            self._fingerprint_worker,
                            filename,
                            self.limit,
                        )
                    )
            for future in as_completed(futures):
                try:
                    song_name, hashes, file_hash = future.result()
                except StopIteration:
                    break
                except Exception:
                    print("Failed fingerprinting")
                    # Print traceback because we can't reraise it here
                    traceback.print_exc(file=sys.stdout)
                else:
                    sid = self.db.insert_song(song_name, file_hash, len(hashes))
                    self.db.insert_hashes(sid, hashes)
                    self.db.set_song_fingerprinted(sid)
        # Wait until all songs are processed to reload hashes
        self.__load_fingerprinted_audio_hashes()

    def fingerprint_file(self, file_path: str, song_name: str = None) -> None:
        """
        Given a path to a file the method generates hashes for it and stores them in the database
        for later be queried.

        :param file_path: path to the file.
        :param song_name: song name associated to the audio file.
        """
        song_name_from_path = decoder.get_audio_name_from_path(file_path)
        song_hash = decoder.unique_hash(file_path)
        song_name = song_name or song_name_from_path
        # don't refingerprint already fingerprinted files
        if song_hash in self.songhashes_set:
            print(f"{song_name} already fingerprinted, continuing...")
        else:
            song_name, hashes, file_hash = Dejavu._fingerprint_worker(
                file_path,
                self.limit,
                song_name=song_name
            )
            sid = self.db.insert_song(song_name, file_hash)

            self.db.insert_hashes(sid, hashes)
            self.db.set_song_fingerprinted(sid)
            self.__load_fingerprinted_audio_hashes()

    def generate_fingerprints(self, samples: List[int], Fs=DEFAULT_FS) -> Tuple[List[Tuple[str, int]], float]:
        f"""
        Generate the fingerprints for the given sample data (channel).

        :param samples: list of ints which represents the channel info of the given audio file.
        :param Fs: sampling rate which defaults to {DEFAULT_FS}.
        :return: a list of tuples for hash and its corresponding offset, together with the generation time.
        """
        t = time()
        hashes = fingerprint(samples, Fs=Fs)
        fingerprint_time = time() - t
        return hashes, fingerprint_time

    def find_matches(self, hashes: List[Tuple[str, int]]) -> Tuple[List[Tuple[int, int]], Dict[str, int], float]:
        """
        Finds the corresponding matches on the fingerprinted audios for the given hashes.

        :param hashes: list of tuples for hashes and their corresponding offsets
        :return: a tuple containing the matches found against the db, a dictionary which counts the different
         hashes matched for each song (with the song id as key), and the time that the query took.

        """
        t = time()
        matches, dedup_hashes = self.db.return_matches(hashes)
        query_time = time() - t

        return matches, dedup_hashes, query_time

    def align_matches(self, matches: List[Tuple[int, int]], dedup_hashes: Dict[str, int], queried_hashes: int,
                      topn: int = TOPN) -> List[Dict[str, any]]:
        """
        Finds hash matches that align in time with other matches and finds
        consensus about which hashes are "true" signal from the audio.

        :param matches: matches from the database
        :param dedup_hashes: dictionary containing the hashes matched without duplicates for each song
        (key is the song id).
        :param queried_hashes: amount of hashes sent for matching against the db
        :param topn: number of results being returned back.
        :return: a list of dictionaries (based on topn) with match information.
        """
        # count offset occurrences per song and keep only the maximum ones.
        sorted_matches = sorted(matches, key=lambda m: (m[0], m[1]))
        counts = ((*key, len(list(group))) for key, group in groupby(sorted_matches, key=lambda m: (m[0], m[1])))
        songs_matches = sorted(
            (max(group, key=lambda g: g[2]) for key, group in groupby(counts, key=lambda count: count[0])),
            key=lambda count: count[2], reverse=True
        )

        songs_result = []
        for song_id, offset, _ in songs_matches[0:topn]:  # consider topn elements in the result
            song = self.db.get_song_by_id(song_id)

            song_name = song.get(SONG_NAME, None)
            song_hashes = song.get(FIELD_TOTAL_HASHES, None)
            nseconds = round(float(offset) / DEFAULT_FS * DEFAULT_WINDOW_SIZE * DEFAULT_OVERLAP_RATIO, 5)
            hashes_matched = dedup_hashes[song_id]

            song = {
                SONG_ID: song_id,
                SONG_NAME: song_name.encode("utf8"),
                INPUT_HASHES: queried_hashes,
                FINGERPRINTED_HASHES: song_hashes,
                HASHES_MATCHED: hashes_matched,
                # Percentage regarding hashes matched vs hashes from the input.
                INPUT_CONFIDENCE: round(hashes_matched / queried_hashes, 2),
                # Percentage regarding hashes matched vs hashes fingerprinted in the db.
                FINGERPRINTED_CONFIDENCE: round(hashes_matched / song_hashes, 2),
                OFFSET: offset,
                OFFSET_SECS: nseconds,
                FIELD_FILE_SHA1: song.get(FIELD_FILE_SHA1, None).encode("utf8")
            }

            songs_result.append(song)

        return songs_result

    def recognize(self, recognizer, *options, **kwoptions) -> Dict[str, any]:
        r = recognizer(self)
        return r.recognize(*options, **kwoptions)

    @staticmethod
    def _fingerprint_worker(file_name, limit):
        song_name = os.path.splitext(os.path.basename(file_name))[0]
        # Suppressing print_output because MP will step all over itself
        # while printing to stdout
        fingerprints, file_hash = Dejavu.get_file_fingerprints(
            file_name, limit, print_output=False
        )
        return song_name, fingerprints, file_hash

    @staticmethod
    def get_file_fingerprints(file_name: str, limit: int, print_output: bool = False):
        channels, fs, file_hash = decoder.read(file_name, limit)
        fingerprints = set()
        channel_amount = len(channels)
        for channeln, channel in enumerate(channels, start=1):
            if print_output:
                print(f"Fingerprinting channel {channeln}/{channel_amount} for {file_name}")

            hashes = fingerprint(channel, Fs=fs)

            if print_output:
                print(f"Finished channel {channeln}/{channel_amount} for {file_name}")

            fingerprints |= set(hashes)

        return fingerprints, file_hash
