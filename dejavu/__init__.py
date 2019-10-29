from dejavu.database import get_database, Database
from dejavu.utils import seconds_to_hms, offsets_to_seconds, seconds_to_offsets
from dejavu import fingerprint, decoder
import multiprocessing
import os
import time
import traceback
import sys


class Dejavu(object):

    SONG_ID = "song_id"
    SONG_NAME = 'song_name'
    CONFIDENCE = 'confidence'
    MATCH_TIME = 'match_time'
    OFFSET = 'offset'
    OFFSET_SECS = 'offset_seconds'

    def __init__(self, config):
        super(Dejavu, self).__init__()

        self.config = config

        # initialize db
        db_cls = get_database(config.get("database_type", None))

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
            song_hash = song[Database.FIELD_FILE_SHA1]
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
                print("%s already fingerprinted, continuing..." % filename)
                continue

            filenames_to_fingerprint.append(filename)

        # Prepare _fingerprint_worker input
        worker_input = zip(filenames_to_fingerprint,
                           [self.limit] * len(filenames_to_fingerprint))

        # Send off our tasks
        iterator = pool.imap_unordered(_fingerprint_worker,
                                       worker_input)

        # Loop till we have all of them
        while True:
            try:
                song_name, hashes, file_hash = iterator.next()
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

    def fingerprint_file(self, filepath, song_name=None, force_reprint=False):
        songname = decoder.path_to_songname(filepath)
        song_hash = decoder.unique_hash(filepath)
        song_name = song_name or songname
        # don't refingerprint already fingerprinted files
        if not force_reprint and song_hash in self.songhashes_set:
            print("%s already fingerprinted, continuing..." % song_name)
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

    def fingerprint_large_file(self, filepath, song_name=None, force_reprint=False, hashes_callback=None):
        songname = decoder.path_to_songname(filepath)
        song_hash = decoder.unique_hash(filepath)
        song_name = song_name or songname
        # don't refingerprint already fingerprinted files
        if not force_reprint and song_hash in self.songhashes_set:
            print("%s already fingerprinted, continuing..." % song_name)
        else:
            custom_configs = self._buildFingerprintingConfig()

            start = time.time()
            sid = self.db.insert_song(song_name, song_hash)
            for hashes in _large_fingerprint_worker(filepath, **custom_configs):
                if hashes_callback:
                    hashes_callback(hashes)
                self.db.insert_hashes(sid, hashes)
            
            self.get_fingerprinted_songs()
            self.db.set_song_fingerprinted(sid)
            stop = time.time()
            print("Song",sid,"added in", round(stop - start,1), "seconds.")

    def _buildFingerprintingConfig(self):
        file_config = self.config
        custom_configs = {}

        CUSTOMIZABLE_SETTINGS = {'CUSTOM_AMP_MIN': 'amp_min',
                                    'CUSTOM_FAN_VALUE': 'fan_value',
                                    'CUSTOM_FS': 'Fs',
                                    'CUSTOM_OVERLAP_RATIO': 'wratio',
                                    'CUSTOM_PEAK_NEIGHBORHOOD_SIZE': 'neighborhood',
                                    'CUSTOM_WINDOW_SIZE': 'wsize',
                                    'CHANNEL_LIMIT':'channel_limit'}

        if file_config.get("CUSTOM_FINGERPRINTING"):
            for key in file_config.get("CUSTOM_FINGERPRINTING"):
                custom_configs[CUSTOMIZABLE_SETTINGS[key]] = file_config["CUSTOM_FINGERPRINTING"][key]
        return custom_configs

    def find_matches(self, samples, Fs=fingerprint.DEFAULT_FS, preserve_offsets=False):
        hashes = fingerprint.fingerprint(samples, Fs=Fs)
        return self.db.return_matches(hashes, preserve_offsets=preserve_offsets)

    def find_matches_from_hashes(self, hashes, preserve_offsets=False):
        return self.db.return_matches(hashes, preserve_offsets=preserve_offsets)

    def find_self_matches(self, song_id, preserve_offsets=True):
        hashes = self.db.self_matches(song_id)
        return self.db.return_matches(hashes, preserve_offsets=preserve_offsets)

    def align_matches(self, matches):
        """
            Finds hash matches that align in time with other matches and finds
            consensus about which hashes are "true" signal from the audio.

            Returns a dictionary with match information.
        """
        # align by diffs
        diff_counter = {}
        largest = 0
        largest_count = 0
        song_id = -1
        for tup in matches:
            sid, diff = tup
            if diff not in diff_counter:
                diff_counter[diff] = {}
            if sid not in diff_counter[diff]:
                diff_counter[diff][sid] = 0
            diff_counter[diff][sid] += 1

            if diff_counter[diff][sid] > largest_count:
                largest = diff
                largest_count = diff_counter[diff][sid]
                song_id = sid

        # extract idenfication
        song = self.db.get_song_by_id(song_id)
        if song:
            # TODO: Clarify what `get_song_by_id` should return.
            songname = song.get(Dejavu.SONG_NAME, None)
        else:
            return None

        # return match info
        nseconds = round(float(largest) / fingerprint.DEFAULT_FS *
                         fingerprint.DEFAULT_WINDOW_SIZE *
                         fingerprint.DEFAULT_OVERLAP_RATIO, 5)
        song = {
            Dejavu.SONG_ID : song_id,
            Dejavu.SONG_NAME : songname,
            Dejavu.CONFIDENCE : largest_count,
            Dejavu.OFFSET : int(largest),
            Dejavu.OFFSET_SECS : nseconds,
            Database.FIELD_FILE_SHA1 : song.get(Database.FIELD_FILE_SHA1, None),}
        return song

    def align_matches_by_overlap(self, matches):
        """
            Finds hash matches that align in time with other matches and finds
            consensus about which hashes are "true" signal from the audio.

            Returns a dictionary with match information.
        """
        # align by diffs
        diff_counter = {}
        largest = 0
        largest_count = 0
        song_id = -1
        for tup in matches:
            sid, diff, source_offset, db_offset = tup
            if diff not in diff_counter:
                diff_counter[diff] = {}
            if sid not in diff_counter[diff]:
                diff_counter[diff][sid] = {'confidence': 0, 'source_max': source_offset, 'source_min': source_offset, 'db_max': db_offset, 'db_min': db_offset}

            current_diff = diff_counter[diff][sid]

            current_diff['confidence'] += 1

            if current_diff['source_max'] < source_offset:
                current_diff['source_max'] = source_offset

            if current_diff['source_min'] > source_offset:
                current_diff['source_min'] = source_offset

            if current_diff['db_max'] < db_offset:
                current_diff['db_max'] = db_offset

            if current_diff['db_min'] > db_offset:
                current_diff['db_min'] = db_offset

        return diff_counter                


    def process_results(self, diff_counter, skip):
        songs = []
        for diff in diff_counter:
            for sid in diff_counter[diff]:
                current_diffs = diff_counter[diff][sid]
                song_id = sid

                song = self.db.get_song_by_id(song_id)
                if song:
                    # TODO: Clarify what `get_song_by_id` should return.
                    songname = song.get(Dejavu.SONG_NAME, None)
                else:
                    print("Breaking")
                    break

                xsong = {
                    'osong':song,
                    Dejavu.SONG_ID : song_id,
                    Dejavu.SONG_NAME : songname,
                    Dejavu.CONFIDENCE : current_diffs['confidence'],
                    Dejavu.OFFSET : int(diff),
                    Dejavu.OFFSET_SECS : current_diffs['confidence'],
                    'source_max': current_diffs['source_max'],
                    'source_min': current_diffs['source_min'],
                    'db_max': current_diffs['db_max'],
                    'db_min': current_diffs['db_min'],

                    'source_max_seconds': offsets_to_seconds(current_diffs['source_max']),
                    'source_min_seconds': offsets_to_seconds(current_diffs['source_min']),
                    'source_range_seconds': offsets_to_seconds(current_diffs['source_max'] - current_diffs['source_min']),
                    'start': seconds_to_hms(offsets_to_seconds(current_diffs['source_min']) + skip),
                    'stop': seconds_to_hms(offsets_to_seconds(current_diffs['source_max']) + skip),
                    'start_seconds': offsets_to_seconds(current_diffs['source_min']) + skip,
                    'stop_seconds': offsets_to_seconds(current_diffs['source_max']) + skip,

                    'db_max_seconds': offsets_to_seconds(current_diffs['db_max']),
                    'db_min_seconds': offsets_to_seconds(current_diffs['db_min']),
                    'db_range_seconds': offsets_to_seconds(current_diffs['db_max'] - current_diffs['db_min']),

                    'oobj':  current_diffs,}

                songs.append(xsong)

        return songs

    def recognize(self, recognizer, *options, **kwoptions):
        r = recognizer(self)
        return r.recognize(*options, **kwoptions)


def _fingerprint_worker(filename, limit=float('inf'), song_name=None, channel_limit=10, skip=0):
    # Pool.imap sends arguments as tuples so we have to unpack
    # them ourself.
    try:
        filename, limit, channel_limit = filename
    except ValueError:
        pass

    songname, _extension = os.path.splitext(os.path.basename(filename))
    song_name = song_name or songname
    channels, Fs, file_hash = decoder.read(filename, limit, skip=skip)
    result = set()
    channel_amount = len(channels)

    for channeln, channel in enumerate(channels[:channel_limit]):
        # TODO: Remove prints or change them into optional logging.
        print("Fingerprinting channel %d/%d for %s" % (channeln + 1,
                                                       channel_amount,
                                                       filename))
        hashes = fingerprint.fingerprint(channel, Fs=Fs)
        print("Finished channel %d/%d for %s" % (channeln + 1, channel_amount,
                                                 filename))
        result |= set(hashes)

    return song_name, result, file_hash

def _large_fingerprint_worker(filename, channel_limit, **kwargs):
    # Pool.imap sends arguments as tuples so we have to unpack
    # them ourself.
    try:
        filename, channel_limit = filename
    except ValueError:
        pass

    chunk_size = 1 * 60 * 1000 # One minute
    chunk_adjustment = chunk_size / 1000
    audio_file_chunks = decoder.read_as_memory_chuncks(filename, chunk_size=chunk_size)

    for chunk_number, chunk in enumerate(audio_file_chunks):
        print("Working on chunk number", chunk_number)
        channels, Fs = decoder.read_chunk(chunk)

        result = set()
        channel_amount = len(channels)

        for channeln, channel in enumerate(channels[:channel_limit]):
            # TODO: Remove prints or change them into optional logging.
            print("Fingerprinting channel %d/%d for %s" % (channeln + 1,
                                                           min(channel_amount, channel_limit),
                                                           filename))
            print("Starting at {}".format(seconds_to_hms(chunk_number * chunk_adjustment)))
            offset_adjustment = seconds_to_offsets(chunk_number * chunk_adjustment)
            hashes = fingerprint.fingerprint(channel, Fs=Fs, offset_adjustment=offset_adjustment, **kwargs)
            print("Finished channel %d/%d for %s" % (channeln + 1, min(channel_amount, channel_limit),
                                                     filename))
            result |= set(hashes)

        yield result


def chunkify(lst, n):
    """
    Splits a list into roughly n equal parts.
    http://stackoverflow.com/questions/2130016/splitting-a-list-of-arbitrary-size-into-only-roughly-n-equal-parts
    """
    return [lst[i::n] for i in range(n)]
