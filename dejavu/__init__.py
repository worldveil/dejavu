from dejavu.database import get_database
import dejavu.decoder as decoder
import fingerprint
import multiprocessing
import os
import traceback
import sys

import shutil
import subprocess
import os.path
from dejavu.decoder import get_duration

class SplitError(Exception):
    def __init__(self, file_path, output_file, error_code):
        Exception.__init__(self)
        self.file_path = file_path
        self.error_code = error_code
        self.output_file = output_file

    def __str__(self):
        return "Spliting of file({0}) failed to ({1}). ffmpeg returned error code: {2}".format(self.file_path, self.output_file, self.error_code)




class Dejavu(object):

    SONG_ID = "song_id"
    SONG_NAME = 'song_name'
    CONFIDENCE = 'confidence'
    MATCH_TIME = 'match_time'
    OFFSET = 'offset'
    OFFSET_SECS = 'offset_seconds'

    SPLIT_DIR = "split_dir"
    OVERWRITE_WHEN_SPLITING = 1

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
        # TODO: should probably use a checksum of the file instead of filename
        self.songs = self.db.get_songs()
        self.songnames_set = set()  # to know which ones we've computed before
        for song in self.songs:
            song_name = song[self.db.FIELD_SONGNAME]
            self.songnames_set.add(song_name)

    def fingerprint_directory(self, path, extensions, nprocesses=None, threat_as_split=False, single_song_name=""):
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
            if decoder.path_to_songname(filename) in self.songnames_set:
                print "%s already fingerprinted, continuing..." % filename
                continue

            filenames_to_fingerprint.append(filename)

        # Prepare _fingerprint_worker input
        worker_input = zip(filenames_to_fingerprint,
                           [self.limit] * len(filenames_to_fingerprint))

        # Send off our tasks
        iterator = pool.imap_unordered(_fingerprint_worker,
                                       worker_input)
        if threat_as_split and single_song_name:
            sid = self.db.insert_song(single_song_name)

        # Loop till we have all of them
        while True:
            try:
                song_name, hashes = iterator.next()
            except multiprocessing.TimeoutError:
                continue
            except StopIteration:
                break
            except:
                print("Failed fingerprinting")
                # Print traceback because we can't reraise it here
                traceback.print_exc(file=sys.stdout)
            else:
                if not threat_as_split:
                    sid = self.db.insert_song(song_name)
                self.db.insert_hashes(sid, hashes)
                self.db.set_song_fingerprinted(sid)
                self.get_fingerprinted_songs()

        pool.close()
        pool.join()

    def fingerprint_file(self, filepath, song_name=None):
        songname = decoder.path_to_songname(filepath)
        song_name = song_name or songname
        # don't refingerprint already fingerprinted files
        if song_name in self.songnames_set:
            print "%s already fingerprinted, continuing..." % song_name
        else:
            song_name, hashes = _fingerprint_worker(filepath,
                                                    self.limit,
                                                    song_name=song_name)

            sid = self.db.insert_song(song_name)

            self.db.insert_hashes(sid, hashes)
            self.db.set_song_fingerprinted(sid)
            self.get_fingerprinted_songs()

    def fingerprint_with_duration_check(self, input_file, minutes=5, song_name=None, processes=None):
        duration = get_duration(input_file)
        split_length =  minutes * 60
        if duration < split_length:
            return self.fingerprint_file(input_file)
        songname, extension = os.path.splitext(os.path.basename(input_file))
        song_name = song_name or songname
        # don't refingerprint already fingerprinted files
        if song_name in self.songnames_set:
            print "%s already fingerprinted, continuing..." % song_name
            return
        file_directory = os.path.dirname(input_file)
        output_split_path = os.path.join(file_directory, self.SPLIT_DIR)
        try:
            os.mkdir(output_split_path)
        except WindowsError:
            pass
        output_path = os.path.join(output_split_path, song_name)
        try:
            os.mkdir(output_path)
        except WindowsError:
            pass

        start_offset = 0
        end_offset = split_length
        retcode = 0
        sid = self.db.insert_song(song_name)
        while start_offset < duration:
            output_file = os.path.join(output_path, "start_sec{0}_end_sec{1}{2}".format(start_offset, end_offset, extension))
            convertion_command = [ 'ffmpeg',
                                    '-i', input_file,
                                    "-acodec", "copy", #fastest convertion possible 1:1 copy
                                    ["-n","-y"][self.OVERWRITE_WHEN_SPLITING],  # always overwrite existing files
                                    "-vn",  # Drop any video streams if there are any
                                    '-ss', str(start_offset),
                                    '-t', str(split_length),
                                    output_file]
            retcode = subprocess.call(convertion_command, stderr=open(os.devnull))
            if retcode != 0:
                raise SplitError(input_file, output_file, retcode)
            start_offset += split_length
            end_offset += split_length
            end_offset = min(end_offset, duration)

        self.db.set_song_fingerprinted(sid)
        self.get_fingerprinted_songs()
        self.fingerprint_directory(output_path, [extension], nprocesses=processes, threat_as_split=True, single_song_name=song_name)
        shutil.rmtree(output_path)

    def find_matches(self, samples, Fs=fingerprint.DEFAULT_FS):
        hashes = fingerprint.fingerprint(samples, Fs=Fs)
        return self.db.return_matches(hashes)

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
            Dejavu.SONG_ID: song_id,
            Dejavu.SONG_NAME: songname,
            Dejavu.CONFIDENCE: largest_count,
            Dejavu.OFFSET: int(largest),
            Dejavu.OFFSET_SECS: nseconds
        }

        return song

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
    channels, Fs = decoder.read(filename, limit)
    result = set()
    channel_amount = len(channels)

    for channeln, channel in enumerate(channels):
        # TODO: Remove prints or change them into optional logging.
        print("Fingerprinting channel %d/%d for %s" % (channeln + 1,
                                                       channel_amount,
                                                       filename))
        hashes = fingerprint.fingerprint(channel, Fs=Fs)
        print("Finished channel %d/%d for %s" % (channeln + 1, channel_amount,
                                                 filename))
        result |= set(hashes)

    return song_name, result


def chunkify(lst, n):
    """
    Splits a list into roughly n equal parts.
    http://stackoverflow.com/questions/2130016/splitting-a-list-of-arbitrary-size-into-only-roughly-n-equal-parts
    """
    return [lst[i::n] for i in xrange(n)]
