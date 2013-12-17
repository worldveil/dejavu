from multiprocessing import Queue, Process
from dejavu.database import SQLDatabase
import dejavu.fingerprint
from dejavu import Dejavu
from scipy.io import wavfile
import wave
import numpy as np
import pyaudio
import sys
import time
import array


class BaseRecognizer(object):
    
    def __init__(self, dejavu):
        self.dejavu = dejavu
        self.Fs = dejavu.fingerprint.DEFAULT_FS
    
    def recognize(self, *data):
        matches = []
        for d in data:
            matches.extend(self.dejavu.find_matches(data, Fs=self.Fs))
        return self.dejavu.align_matches(matches)


class WaveFileRecognizer(BaseRecognizer):
    
    def __init__(self, dejavu):
        super(BaseRecognizer, self).__init__(dejavu)
    
    def recognize_file(self, filepath):
        Fs, frames = wavfile.read(filename)
        self.Fs = Fs
        
        wave_object = wave.open(filename)
        nchannels, sampwidth, framerate, num_frames, comptype, compname = wave_object.getparams()
        
        channels = []
        for channel in range(nchannels):
            channels.append(frames[:, channel])
        
        t = time.time()
        match = self.recognize(*channels)
        t = time.time() - t
        
        if match:
            match['match_time'] = t
        
        return match


class MicrophoneRecognizer(BaseRecognizer):
    pass
    
    


class Recognizer(object):

    CHUNK = 8192 # 44100 is a multiple of 1225
    FORMAT = pyaudio.paInt16
    CHANNELS = 2
    RATE = 44100

    def __init__(self, fingerprinter, config):

        self.fingerprinter = fingerprinter
        self.config = config
        self.audio = pyaudio.PyAudio()
    
    def listen(self, seconds=10, verbose=False):

        # open stream
        stream = self.audio.open(format=Recognizer.FORMAT,
                        channels=Recognizer.CHANNELS,
                        rate=Recognizer.RATE,
                        input=True,
                        frames_per_buffer=Recognizer.CHUNK)
        
        # record
        if verbose: print("* recording")
        left, right = [], []
        for i in range(0, int(Recognizer.RATE / Recognizer.CHUNK * seconds)):
            data = stream.read(Recognizer.CHUNK)
            nums = np.fromstring(data, np.int16)
            left.extend(nums[1::2])
            right.extend(nums[0::2])
        if verbose: print("* done recording")
        
        # close and stop the stream
        stream.stop_stream()
        stream.close()
        
        # match both channels
        starttime = time.time()
        matches = []
        matches.extend(self.fingerprinter.match(left))
        matches.extend(self.fingerprinter.match(right))
        
        # align and return
        return self.fingerprinter.align_matches(matches, starttime, record_seconds=seconds, verbose=verbose)