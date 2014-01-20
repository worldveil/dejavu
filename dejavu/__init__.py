from dejavu.database import get_database
import dejavu.decoder as decoder
import fingerprint
import multiprocessing
import os


class Dejavu(object):
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
        if self.limit == -1: # for JSON compatibility
            self.limit = None

        # get songs previously indexed
        # TODO: should probably use a checksum of the file instead of filename
        self.songs = self.db.get_songs()
        self.songnames_set = set()  # to know which ones we've computed before
        for song in self.songs:
            song_name = song[self.db.FIELD_SONGNAME]
            self.songnames_set.add(song_name)
            print "Added: %s to the set of fingerprinted songs..." % song_name

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
                import traceback, sys
                traceback.print_exc(file=sys.stdout)
            else:
                sid = self.db.insert_song(song_name)

                self.db.insert_hashes(sid, hashes)

        pool.close()
        pool.join()

    def fingerprint_file(self, filepath, song_name=None):
        song_name, hashes = _fingerprint_worker(filepath,
                                                self.limit,
                                                song_name=song_name)

        sid = self.db.insert_song(song_name)

        self.db.insert_hashes(sid, hashes)

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
            if not diff in diff_counter:
                diff_counter[diff] = {}
            if not sid in diff_counter[diff]:
                diff_counter[diff][sid] = 0
            diff_counter[diff][sid] += 1

            if diff_counter[diff][sid] > largest_count:
                largest = diff
                largest_count = diff_counter[diff][sid]
                song_id = sid

        print("Diff is %d with %d offset-aligned matches" % (largest,
                                                             largest_count))

        # extract idenfication
        song = self.db.get_song_by_id(song_id)
        if song:
            # TODO: Clarifey what `get_song_by_id` should return.
            songname = song.get("song_name", None)
        else:
            return None

        # return match info
        song = {
            "song_id": song_id,
            "song_name": songname,
            "confidence": largest_count,
            "offset": largest
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
