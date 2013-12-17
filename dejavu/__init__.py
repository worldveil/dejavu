from dejavu.database import SQLDatabase
from dejavu.convert import Converter
import dejavu.fingerprint as fingerprint
from scipy.io import wavfile
from multiprocessing import Process
import wave, os
import random

DEBUG = False

class Dejavu():

    def __init__(self, config):
    
        self.config = config
        
        # initialize db
        database = SQLDatabase(
            self.config.get(SQLDatabase.CONNECTION, SQLDatabase.KEY_HOSTNAME),
            self.config.get(SQLDatabase.CONNECTION, SQLDatabase.KEY_USERNAME),
            self.config.get(SQLDatabase.CONNECTION, SQLDatabase.KEY_PASSWORD),
            self.config.get(SQLDatabase.CONNECTION, SQLDatabase.KEY_DATABASE))
        self.db = database
        
        # create components
        self.converter = Converter()
        #self.fingerprinter = Fingerprinter(self.config)
        self.db.setup()

        # get songs previously indexed
        self.songs = self.db.get_songs()
        self.songnames_set = set() # to know which ones we've computed before
        if self.songs:
            for song in self.songs:
                song_id = song[SQLDatabase.FIELD_SONG_ID]
                song_name = song[SQLDatabase.FIELD_SONGNAME]
                self.songnames_set.add(song_name)
                print "Added: %s to the set of fingerprinted songs..." % song_name

    def chunkify(self, lst, n):
        """
            Splits a list into roughly n equal parts. 
            http://stackoverflow.com/questions/2130016/splitting-a-list-of-arbitrary-size-into-only-roughly-n-equal-parts
        """
        return [lst[i::n] for i in xrange(n)]

    def fingerprint(self, path, output, extensions, nprocesses):

        # convert files, shuffle order
        files = self.converter.find_files(path, extensions)
        random.shuffle(files)
        files_split = self.chunkify(files, nprocesses)

        # split into processes here
        processes = []
        for i in range(nprocesses):

            # need database instance since mysql connections shouldn't be shared across processes
            sql_connection = SQLDatabase( 
                self.config.get(SQLDatabase.CONNECTION, SQLDatabase.KEY_HOSTNAME),
                self.config.get(SQLDatabase.CONNECTION, SQLDatabase.KEY_USERNAME),
                self.config.get(SQLDatabase.CONNECTION, SQLDatabase.KEY_PASSWORD),
                self.config.get(SQLDatabase.CONNECTION, SQLDatabase.KEY_DATABASE))

            # create process and start it
            p = Process(target=self.fingerprint_worker, args=(files_split[i], sql_connection, output))
            p.start()
            processes.append(p)

        # wait for all processes to complete
        for p in processes:
            p.join()
            
        # delete orphans
        # print "Done fingerprinting. Deleting orphaned fingerprints..."
        # TODO: need a more performant query in database.py for the 
        #self.fingerprinter.db.delete_orphans()

    def fingerprint_worker(self, files, sql_connection, output):

        for filename, extension in files:

            # if there are already fingerprints in database, don't re-fingerprint or convert
            song_name = os.path.basename(filename).split(".")[0]
            if DEBUG and song_name in self.songnames_set: 
                print("-> Already fingerprinted, continuing...")
                continue

            # convert to WAV
            wavout_path = self.converter.convert(filename, extension, Converter.WAV, output, song_name)

            # insert song name into database
            song_id = sql_connection.insert_song(song_name)

            # for each channel perform FFT analysis and fingerprinting
            channels, Fs = self.extract_channels(wavout_path)
            for c in range(len(channels)):
                channel = channels[c]
                print "-> Fingerprinting channel %d of song %s..." % (c+1, song_name)
                hashes = fingerprint.fingerprint(channel, Fs=Fs)
                sql_connection.insert_hashes(song_id, hashes)

            # only after done fingerprinting do confirm
            sql_connection.set_song_fingerprinted(song_id)

    def extract_channels(self, path):
        """
            Reads channels from disk.
            Returns a tuple with (channels, sample_rate)
        """
        channels = []
        Fs, frames = wavfile.read(path)
        wave_object = wave.open(path)
        nchannels, sampwidth, framerate, num_frames, comptype, compname = wave_object.getparams()
        #assert Fs == self.fingerprinter.Fs

        for channel in range(nchannels):
            channels.append(frames[:, channel])
        return (channels, Fs)
    
    def fingerprint(self, filepath, song_name=None):
        # TODO: replace with something that handles all audio formats
        channels, Fs = self.extract_channels(path)
        if not song_name:
            song_name = os.path.basename(filename).split(".")[0]
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

        if DEBUG: 
            print("Diff is %d with %d offset-aligned matches" % (largest, largest_count))
        
        # extract idenfication      
        song = self.db.get_song_by_id(song_id)
        if song:
            songname = song.get(SQLDatabase.FIELD_SONGNAME, None)
        else:
            return None
        
        if DEBUG: 
            print("Song is %s (song ID = %d) identification took %f seconds" % (songname, song_id, elapsed))
        
        # return match info
        song = {
            "song_id" : song_id,
            "song_name" : songname,
            "confidence" : largest_count
        }
            
        return song