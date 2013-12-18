from dejavu.database import SQLDatabase
from dejavu.convert import Converter
from dejavu.fingerprint import Fingerprinter
from scipy.io import wavfile
from multiprocessing import Process
import wave, os
import random

class Dejavu():

    def __init__(self, config):
    
        self.config = config

        # create components
        self.converter = Converter(config)
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

    def fingerprint(self, path, output, extensions, nprocesses, keep_wav=False):

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
            p = Process(target=self.fingerprint_worker, args=(files_split[i], sql_connection, output, keep_wav))
            p.start()
            processes.append(p)

        # wait for all processes to complete
        try:        
            for p in processes:
                p.join()
        except KeyboardInterrupt:
            print "-> Exiting.."
            for worker in processes:
                worker.terminate()
                worker.join()
            
        # delete orphans
        # print "Done fingerprinting. Deleting orphaned fingerprints..."
        # TODO: need a more performant query in database.py for the 
        #self.fingerprinter.db.delete_orphans()

    def fingerprint_worker(self, files, sql_connection, output, keep_wav):

        for filename, extension in files:
            # if there are already fingerprints in database, don't re-fingerprint or convert
            if filename in self.songnames_set: 
                print "-> Already fingerprinted, continuing..."
                continue

            # convert to WAV
            wavout_path = self.converter.convert(filename, extension, Converter.WAV, output)

            # for each channel perform FFT analysis and fingerprinting
            try:            
                channels = self.extract_channels(wavout_path)
            except AssertionError, e:
                print "-> File not supported, skipping."
                continue

            # insert song name into database
            song_id = sql_connection.insert_song(filename)

            for c in range(len(channels)):
                channel = channels[c]
                print "-> Fingerprinting channel %d of song %s..." % (c+1, filename)
                self.fingerprinter.fingerprint(channel, wavout_path, song_id, c+1)

            # remove wav file if not required
            if not keep_wav:
                os.unlink(wavout_path)            

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
