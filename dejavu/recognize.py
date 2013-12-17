from multiprocessing import Queue, Process
from dejavu.database import SQLDatabase
import dejavu.fingerprint as fingerprint
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
        self.Fs = fingerprint.DEFAULT_FS

    def _recognize(self, *data):
        matches = []
        for d in data:
            matches.extend(self.dejavu.find_matches(d, Fs=self.Fs))
        return self.dejavu.align_matches(matches)

    def recognize(self):
        pass  # base class does nothing

class WaveFileRecognizer(BaseRecognizer):

    def __init__(self, dejavu, filename=None):
        super(WaveFileRecognizer, self).__init__(dejavu)
        self.filename = filename

    def recognize_file(self, filename):
        Fs, frames = wavfile.read(filename)
        self.Fs = Fs

        wave_object = wave.open(filename)
        nchannels, sampwidth, framerate, num_frames, comptype, compname = wave_object.getparams()

        channels = []
        for channel in range(nchannels):
            channels.append(frames[:, channel])

        t = time.time()
        match = self._recognize(*channels)
        t = time.time() - t

        if match:
            match['match_time'] = t

        return match

    def recognize(self):
        return self.recognize_file(self.filename)


class MicrophoneRecognizer(BaseRecognizer):

    CHUNK = 8192 # 44100 is a multiple of 1225
    FORMAT = pyaudio.paInt16
    CHANNELS = 2
    RATE = 44100

    def __init__(self, dejavu, seconds=None):
        super(MicrophoneRecognizer, self).__init__(dejavu)
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.data = []
        self.channels = CHANNELS
        self.chunk_size = CHUNK
        self.rate = RATE
        self.recorded = False

    def start_recording(self, channels=CHANNELS, rate=RATE, chunk=CHUNK):
        self.chunk_size = chunk
        self.channels = channels
        self.recorded = False
        self.rate = rate

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()

        self.stream = self.audio.open(format=FORMAT,
                                channels=channels,
                                rate=rate,
                                input=True,
                                frames_per_buffer=chunk)

        self.data = [[] for i in range(channels)]

    def process_recording(self):
        data = self.stream.read(self.chunk_size)
        nums = np.fromstring(data, np.int16)
        for c in range(self.channels):
            self.data[c].extend(nums[c::c+1])

    def stop_recording(self):
        self.stream.stop_stream()
        self.stream.close()
        self.stream = None
        self.recorded = True

    def recognize_recording(self):
        if not self.recorded:
            raise NoRecordingError("Recording was not complete/begun")
        return self._recognize(*self.data)

    def get_recorded_time(self):
        return len(self.data[0]) / self.rate

    def recognize(self):
        self.start_recording()
        for i in range(0, int(self.rate / self.chunk * self.seconds)):
            self.process_recording()
        self.stop_recording()
        return self.recognize_recording()

class NoRecordingError(Exception):
    pass

