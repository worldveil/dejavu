from dejavu.database import get_database
import dejavu.decoder as decoder
import fingerprint
import multiprocessing
import os
import traceback
import sys

DEBUG = False


class Dejavu(object):

    SONG_ID = "song_id"
    SONG_NAME = 'song_name'
    CONFIDENCE = 'confidence'
    MATCH_TIME = 'match_time'
    OFFSET = 'offset'
    OFFSET_SECS = 'offset_seconds'

    def __init__(self, config):
        """
        Creates a Dejavu instance, kicks of DB setup, etc.
        """
        super(Dejavu, self).__init__()

        self.config = config

        # initialize db
        db_cls = get_database(config.get("database_type", None))
        self.db = db_cls(**config.get("database", {}))
        self.db.setup()

        # If we should limit seconds fingerprinted, ie only
        # fingerprint 10 seconds of a file. (None/-1 == use full)
        self.limit = self.config.get("fingerprint_limit", None)
        if self.limit == -1:  # for JSON compatibility
            self.limit = None
        self.get_fingerprinted_songs()

    def get_fingerprinted_songs(self):
        """ Gets files previously indexed.
        """
        self.songs = self.db.get_songs()
        self.songnames_set = set()  # to know which ones we've computed before
        for song in self.songs:
            song_name = song[self.db.FIELD_SONGNAME]
            self.songnames_set.add(song_name)

    def fingerprint_directory(self, path, extensions, nprocesses=None):
        """
        Fingerprints a directory, does so by trying to use the maximum
        amount of processes (if not given).
        """
        try:
            nprocesses = nprocesses or multiprocessing.cpu_count()
        except NotImplementedError:
            nprocesses = 1
        else:
            nprocesses = 1 if nprocesses <= 0 else nprocesses

        pool = multiprocessing.Pool(nprocesses)

        filenames_to_fingerprint = []
        for filename, _ in decoder.find_files(path, extensions):
            # Avoid re-fingerprinting files.
            if decoder.path_to_songname(filename) in self.songnames_set:
                print "%s already fingerprinted, continuing..." % filename
                continue
            filenames_to_fingerprint.append(filename)

        # Prepare _fingerprint_worker input
        worker_input = zip(filenames_to_fingerprint,
                           [self.limit] * len(filenames_to_fingerprint))
        iterator = pool.imap_unordered(_fingerprint_worker,
                                       worker_input)

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
                # If we can can fingerprint the song, create
                # an entry in the DB, insert hashes (bulk)

                # modify this to include md5
                sid = self.db.insert_song(song_name)
                self.db.insert_hashes(sid, hashes)
                self.db.set_song_fingerprinted(sid)
                self.get_fingerprinted_songs()

        pool.close()
        pool.join()

    def fingerprint_file(self, filepath, song_name=None):
        """ Given a filepath, generates a songname and
        then fingerprints it if it has been already.
        """
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

    def find_matches(self, samples, Fs=fingerprint.DEFAULT_FS):
        """ Returns all matches for a sample compared to the DB.
        """
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

        # Get information for the given song.
        if song_id == -1:
            return None
        song = self.db.get_song_by_id(song_id)
        if not song:
            return None

        # TODO: Clarify what `get_song_by_id` should return.
        # Probably add metadata here.
        songname = song.get(Dejavu.SONG_NAME, None)

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
        """ Identify a song.
        """
        r = recognizer(self)
        return r.recognize(*options, **kwoptions)


def _fingerprint_worker(filename, limit=None, song_name=None):
    """  Worker to fingerprint a file.
    Pool.imap sends arguments as tuples so we have to unpack
    them ourself.
    """
    try:
        filename, limit = filename
    except ValueError as err:
        print "Error unpacking filename and limit", err
        pass

    songname, extension = os.path.splitext(os.path.basename(filename))
    song_name = song_name or songname
    channels, Fs = decoder.read(filename, limit)
    result = set()
    channel_amount = len(channels)

    for channeln, channel in enumerate(channels):
        if DEBUG:
            print("Fingerprinting channel %d/%d for %s" % (
                channeln + 1,
                channel_amount,
                filename)
            )
        hashes = fingerprint.fingerprint(channel, Fs=Fs)

        if DEBUG:
            print("Finished channel %d/%d for %s" % (
                channeln + 1,
                channel_amount,
                filename)
            )
        result |= set(hashes)

    return song_name, result


def chunkify(lst, n):
    """
    Splits a list into roughly n equal parts.
    Taken from stackoverflow: http://stackoverflow.com/questions/2130016/
    """
    return [lst[i::n] for i in xrange(n)]
