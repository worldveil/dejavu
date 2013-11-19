from dejavu.database import SQLDatabase
from dejavu.converter import Converter
from dejavu.fingerprint import Fingerprinter
from scipy.io import wavfile
from multiprocessing import Process
import wave, os
import random

class Dejavu():

    def __init__(self, config):
    
        self.config = config

        # create components
        self.converter = Converter()
        self.fingerprinter = Fingerprinter(self.config)
        self.fingerprinter.db.setup()

        # get songs previously indexed
        self.songs = self.fingerprinter.db.get_songs()
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
        print "Done fingerprinting. Deleting orphaned fingerprints..."
        self.fingerprinter.db.delete_orphans()

    def fingerprint_worker(self, files, sql_connection, output):

        for filename, extension in files:

            # if there are already fingerprints in database, don't re-fingerprint or convert
            song_name = os.path.basename(filename).split(".")[0]
            if song_name in self.songnames_set: 
                print "-> Already fingerprinted, continuing..."
                continue

            # convert to WAV
            wavout_path = self.converter.convert(filename, extension, Converter.WAV, output, song_name)

            # insert song name into database
            song_id = sql_connection.insert_song(song_name)

            # for each channel perform FFT analysis and fingerprinting
            channels = self.extract_channels(wavout_path)
            for c in range(len(channels)):
                channel = channels[c]
                print "-> Fingerprinting channel %d of song %s..." % (c+1, song_name)
                self.fingerprinter.fingerprint(channel, wavout_path, song_id, c+1)

            # only after done fingerprinting do confirm
            sql_connection.set_song_fingerprinted(song_id)

    def extract_channels(self, path):
        """
            Reads channels from disk.
        """
        channels = []
        Fs, frames = wavfile.read(path)
        wave_object = wave.open(path)
        nchannels, sampwidth, framerate, num_frames, comptype, compname = wave_object.getparams()
        assert Fs == self.fingerprinter.Fs

        for channel in range(nchannels):
            channels.append(frames[:, channel])
        return channels