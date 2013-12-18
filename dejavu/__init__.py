from dejavu.database import SQLDatabase
import dejavu.decoder as decoder
import fingerprint
from multiprocessing import Process, cpu_count
import os
import random


class Dejavu(object):
    def __init__(self, config):
        super(Dejavu, self).__init__()

        self.config = config

        # initialize db
        self.db = SQLDatabase(**config.get("database", {}))

        self.db.setup()

        # get songs previously indexed
        self.songs = self.db.get_songs()
        self.songnames_set = set()  # to know which ones we've computed before

        for song in self.songs:
            song_name = song[self.db.FIELD_SONGNAME]

            self.songnames_set.add(song_name)
            print "Added: %s to the set of fingerprinted songs..." % song_name

    def fingerprint_directory(self, path, extensions, nprocesses=None):
        # Try to use the maximum amount of processes if not given.
        if nprocesses is None:
            try:
                nprocesses = cpu_count()
            except NotImplementedError:
                nprocesses = 1

        # convert files, shuffle order
        files = list(decoder.find_files(path, extensions))
        random.shuffle(files)

        files_split = chunkify(files, nprocesses)

        # split into processes here
        processes = []
        for i in range(nprocesses):

            # create process and start it
            p = Process(target=self._fingerprint_worker,
                        args=(files_split[i], self.db))
            p.start()
            processes.append(p)

        # wait for all processes to complete
        for p in processes:
            p.join()

    def _fingerprint_worker(self, files, db):
        for filename, extension in files:

            # if there are already fingerprints in database,
            # don't re-fingerprint
            song_name = os.path.basename(filename).split(".")[0]
            if song_name in self.songnames_set:
                print("-> Already fingerprinted, continuing...")
                continue

            channels, Fs = decoder.read(filename)

            # insert song name into database
            song_id = db.insert_song(song_name)

            for c in range(len(channels)):
                channel = channels[c]
                print "-> Fingerprinting channel %d of song %s..." % (c+1, song_name)

                hashes = fingerprint.fingerprint(channel, Fs=Fs)

                db.insert_hashes(song_id, hashes)

            # only after done fingerprinting do confirm
            db.set_song_fingerprinted(song_id)

    def fingerprint_file(self, filepath, song_name=None):
        channels, Fs = decoder.read(filepath)

        if not song_name:
            song_name = os.path.basename(filepath).split(".")[0]
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

        print("Diff is %d with %d offset-aligned matches" % (largest, largest_count))

        # extract idenfication
        song = self.db.get_song_by_id(song_id)
        if song:
            songname = song.get(SQLDatabase.FIELD_SONGNAME, None)
        else:
            return None

        # return match info
        song = {
            "song_id": song_id,
            "song_name": songname,
            "confidence": largest_count
        }

        return song

    def recognize(self, recognizer, *options, **kwoptions):
        r = recognizer(self)
        return r.recognize(*options, **kwoptions)


def chunkify(lst, n):
    """
    Splits a list into roughly n equal parts.
    http://stackoverflow.com/questions/2130016/splitting-a-list-of-arbitrary-size-into-only-roughly-n-equal-parts
    """
    return [lst[i::n] for i in xrange(n)]
