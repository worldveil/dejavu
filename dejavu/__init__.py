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

        results = []
        for filename, _ in decoder.find_files(path, extensions):

            # don't refingerprint already fingerprinted files
            if decoder.path_to_songname(filename) in self.songnames_set:
                print "%s already fingerprinted, continuing..." % filename
                continue

            result = pool.apply_async(_fingerprint_worker,
                                      (filename, self.db))
            results.append(result)

        while len(results):
            for result in results[:]:
                # TODO: Handle errors gracefully and return them to the callee
                # in some way.
                try:
                    result.get(timeout=2)
                except multiprocessing.TimeoutError:
                    continue
                except:
                    import traceback, sys
                    traceback.print_exc(file=sys.stdout)
                    results.remove(result)
                else:
                    results.remove(result)

        pool.close()
        pool.join()

    def fingerprint_file(self, filepath, song_name=None):
        channels, Fs = decoder.read(filepath)

        if not song_name:
            print "Song name: %s" % song_name
            song_name = decoder.path_to_songname(filepath)
        song_id = self.db.insert_song(song_name)

        for data in channels:
            hashes = fingerprint.fingerprint(data, Fs=Fs)
            self.db.insert_hashes(song_id, hashes)

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
            "offset" : largest
        }

        return song

    def recognize(self, recognizer, *options, **kwoptions):
        r = recognizer(self)
        return r.recognize(*options, **kwoptions)


def _fingerprint_worker(filename, db):
    song_name, extension = os.path.splitext(os.path.basename(filename))

    channels, Fs = decoder.read(filename)

    # insert song into database
    sid = db.insert_song(song_name)

    channel_amount = len(channels)
    for channeln, channel in enumerate(channels):
        # TODO: Remove prints or change them into optional logging.
        print("Fingerprinting channel %d/%d for %s" % (channeln + 1,
                                                       channel_amount,
                                                       filename))
        hashes = fingerprint.fingerprint(channel, Fs=Fs)
        print("Finished channel %d/%d for %s" % (channeln + 1, channel_amount,
                                                 filename))

        print("Inserting fingerprints for channel %d/%d for %s" %
              (channeln + 1, channel_amount, filename))
        db.insert_hashes(sid, hashes)
        print("Finished inserting for channel %d/%d for  %s" %
              (channeln + 1, channel_amount, filename))

    print("Marking %s finished" % (filename,))
    db.set_song_fingerprinted(sid)
    print("%s finished" % (filename,))


def chunkify(lst, n):
    """
    Splits a list into roughly n equal parts.
    http://stackoverflow.com/questions/2130016/splitting-a-list-of-arbitrary-size-into-only-roughly-n-equal-parts
    """
    return [lst[i::n] for i in xrange(n)]
