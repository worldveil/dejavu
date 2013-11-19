from multiprocessing import Queue, Process
from dejavu.database import SQLDatabase
from scipy.io import wavfile
import wave
import numpy as np
import pyaudio
import sys
import time
import array

class Recognizer(object):

    CHUNK = 8192 # 44100 is a multiple of 1225
    FORMAT = pyaudio.paInt16
    CHANNELS = 2
    RATE = 44100

    def __init__(self, fingerprinter, config):

        self.fingerprinter = fingerprinter
        self.config = config
        self.audio = pyaudio.PyAudio()
        
    def read(self, filename, verbose=False):
        
        # read file into channels            
        channels = []
        Fs, frames = wavfile.read(filename)
        wave_object = wave.open(filename)
        nchannels, sampwidth, framerate, num_frames, comptype, compname = wave_object.getparams()
        for channel in range(nchannels):
            channels.append(frames[:, channel])    
        
        # get matches
        starttime = time.time()
        matches = []
        for channel in channels:
            matches.extend(self.fingerprinter.match(channel))
        
        return self.fingerprinter.align_matches(matches, starttime, verbose=verbose)
    
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