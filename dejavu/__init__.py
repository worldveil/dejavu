import multiprocessing
import os
import sys
import traceback

import dejavu.decoder as decoder
from dejavu.config.config import (CONFIDENCE, DEFAULT_FS,
                                  DEFAULT_OVERLAP_RATIO, DEFAULT_WINDOW_SIZE,
                                  FIELD_FILE_SHA1, OFFSET, OFFSET_SECS,
                                  SONG_ID, SONG_NAME, TOPN)
from dejavu.database import get_database
from dejavu.fingerprint import fingerprint


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
        self.get_fingerprinted_songs()

    def get_fingerprinted_songs(self):
        # get songs previously indexed
        self.songs = self.db.get_songs()
        self.songhashes_set = set()  # to know which ones we've computed before
        for song in self.songs:
            song_hash = song[FIELD_FILE_SHA1]
            self.songhashes_set.add(song_hash)

    def fingerprint_directory(self, path, extensions, nprocesses=None):
        # Try to use the maximum amount of processes if not given.
        try:
            nprocesses = nprocesses or multiprocessing.cpu_count()
        except NotImplementedError:
            nprocesses = 1
        else:
            nprocesses = 1 if nprocesses <= 0 else nprocesses

        pool = multiprocessing.Pool(nprocesses)

        filenames_to_fingerprint = []
        for filename, _ in decoder.find_files(path, extensions):
            # don't refingerprint already fingerprinted files
            if decoder.unique_hash(filename) in self.songhashes_set:
                print(f"{filename} already fingerprinted, continuing...")
                continue

            filenames_to_fingerprint.append(filename)

        # Prepare _fingerprint_worker input
        worker_input = list(zip(filenames_to_fingerprint, [self.limit] * len(filenames_to_fingerprint)))

        # Send off our tasks
        iterator = pool.imap_unordered(_fingerprint_worker, worker_input)

        # Loop till we have all of them
        while True:
            try:
                song_name, hashes, file_hash = next(iterator)
            except multiprocessing.TimeoutError:
                continue
            except StopIteration:
                break
            except:
                print("Failed fingerprinting")
                # Print traceback because we can't reraise it here
                traceback.print_exc(file=sys.stdout)
            else:
                sid = self.db.insert_song(song_name, file_hash)

                self.db.insert_hashes(sid, hashes)
                self.db.set_song_fingerprinted(sid)
                self.get_fingerprinted_songs()

        pool.close()
        pool.join()

    def fingerprint_file(self, filepath, song_name=None):
        songname = decoder.path_to_songname(filepath)
        song_hash = decoder.unique_hash(filepath)
        song_name = song_name or songname
        # don't refingerprint already fingerprinted files
        if song_hash in self.songhashes_set:
            print(f"{song_name} already fingerprinted, continuing...")
        else:
            song_name, hashes, file_hash = _fingerprint_worker(
                filepath,
                self.limit,
                song_name=song_name
            )
            sid = self.db.insert_song(song_name, file_hash)

            self.db.insert_hashes(sid, hashes)
            self.db.set_song_fingerprinted(sid)
            self.get_fingerprinted_songs()

    def find_matches(self, samples, Fs=DEFAULT_FS):
        hashes = fingerprint(samples, Fs=Fs)
        return self.db.return_matches(hashes)

    def align_matches(self, matches, topn=TOPN):
        """
            Finds hash matches that align in time with other matches and finds
            consensus about which hashes are "true" signal from the audio.

            Returns a list of dictionaries (based on topn) with match information.
        """
        # align by diffs
        diff_counter = {}
        largest_count = 0

        for tup in matches:
            sid, diff = tup
            if diff not in diff_counter:
                diff_counter[diff] = {}
            if sid not in diff_counter[diff]:
                diff_counter[diff][sid] = 0
            diff_counter[diff][sid] += 1

            if diff_counter[diff][sid] > largest_count:
                largest_count = diff_counter[diff][sid]

        # create dic where key are songs ids
        songs_num_matches = {}
        for dc in diff_counter:
            for sid in diff_counter[dc]:
                match_val = diff_counter[dc][sid]
                if (sid not in songs_num_matches) or (match_val > songs_num_matches[sid]['value']):
                    songs_num_matches[sid] = {
                        'sid': sid,
                        'value': match_val,
                        'largest': dc
                    }

        # use dicc of songs to create an ordered (descending) list using the match value property assigned to each song
        songs_num_matches_list = []
        for s in songs_num_matches:
            songs_num_matches_list.append({
                'sid': s,
                'object': songs_num_matches[s]
            })

        songs_num_matches_list_ordered = sorted(songs_num_matches_list, key=lambda x: x['object']['value'],
                                                reverse=True)

        # iterate the ordered list and fill results
        songs_result = []
        for s in songs_num_matches_list_ordered:

            # get expected variable by the original code
            song_id = s['object']['sid']
            largest = s['object']['largest']
            largest_count = s['object']['value']

            # extract identification
            song = self.db.get_song_by_id(song_id)
            if song:
                # TODO: Clarify what `get_song_by_id` should return.
                songname = song.get(SONG_NAME, None)

                # return match info
                nseconds = round(float(largest) / DEFAULT_FS *
                                 DEFAULT_WINDOW_SIZE *
                                 DEFAULT_OVERLAP_RATIO, 5)
                song = {
                    SONG_ID: song_id,
                    SONG_NAME: songname.encode("utf8"),
                    CONFIDENCE: largest_count,
                    OFFSET: int(largest),
                    OFFSET_SECS: nseconds,
                    FIELD_FILE_SHA1: song.get(FIELD_FILE_SHA1, None).encode("utf8")
                }

                songs_result.append(song)

                # only consider up to topn elements in the result
                if len(songs_result) > topn:
                    break
        return songs_result

    def recognize(self, recognizer, *options, **kwoptions):
        r = recognizer(self)
        return r.recognize(*options, **kwoptions)


def _fingerprint_worker(filename, limit=None, song_name=None):
    # Pool.imap sends arguments as tuples so we have to unpack
    # them ourself.
    try:
        filename, limit = filename
    except ValueError:
        pass

    songname, extension = os.path.splitext(os.path.basename(filename))
    song_name = song_name or songname
    channels, fs, file_hash = decoder.read(filename, limit)
    result = set()
    channel_amount = len(channels)

    for channeln, channel in enumerate(channels):
        # TODO: Remove prints or change them into optional logging.
        print(f"Fingerprinting channel {channeln + 1}/{channel_amount} for {filename}")
        hashes = fingerprint(channel, Fs=fs)
        print(f"Finished channel {channeln + 1}/{channel_amount} for {filename}")
        result |= set(hashes)

    return song_name, result, file_hash
