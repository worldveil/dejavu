import dejavu.fingerprint as fingerprint
import dejavu.decoder as decoder
import numpy as np
import pyaudio
import time


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


class FileRecognizer(BaseRecognizer):
    def __init__(self, dejavu):
        super(FileRecognizer, self).__init__(dejavu)

    def recognize_file(self, filename):
        frames, self.Fs, file_hash = decoder.read(filename, self.dejavu.limit)

        t = time.time()
        match = self._recognize(*frames)
        t = time.time() - t

        if match:
            match['match_time'] = t

        return match

    def recognize(self, filename):
        return self.recognize_file(filename)

class RadioRecognizer(BaseRecognizer):
    def __init__(self, dejavu):
        super(RadioRecognizer, self).__init__(dejavu)

    def recognize_file(self, filename, limit, offset):
        l = time.time()
        frames, self.Fs, file_hash = decoder.read(filename, limit=limit, skip=offset)
        l = time.time() - l

        t = time.time()
        match = self._recognize(*frames)
        t = time.time() - t

        if match:
            matches = self.dejavu.process_results(match, offset)

            return matches, {'load_time': l, 'recognize_time': t}

    def recognize(self, filename, limit, skip):
        return self.recognize_file(filename, limit, skip)

    def _recognize(self, *data):
        matches = []
        for i, d in enumerate(data):
            print("Starting channel ", i)
            matches.extend(self.dejavu.find_matches(d, Fs=self.Fs, preserve_offsets=True))
            print("Finished channel ", i)            
        return self.dejavu.align_matches_by_overlap(matches)

class HybridRadioRecognizer(BaseRecognizer):
    def __init__(self, dejavu):
        super(HybridRadioRecognizer, self).__init__(dejavu)

    def recognize_file(self, filename, limit=float('inf'), offset=0):
        matches = []

        self.seek_time = 0
        
        hashes_callback=lambda hashes:self._recognize(matches, *hashes)
        
        p = time.time()
        self.dejavu.fingerprint_large_file(filename, hashes_callback=hashes_callback)
        p = time.time() - p

        t = time.time()
        match_data = self.dejavu.align_matches_by_overlap(matches)
        t = time.time() - t

        if match_data:
            matches = self.dejavu.process_results(match_data, skip=0)

            return matches, {'process_time': p, 'recognize_time': t, 'seek_time': self.seek_time}

    def recognize(self, filename, limit=float('inf'), offset=0):
        return self.recognize_file(filename, limit, offset)

    def _recognize(self, matches=[], *data):
        print("Seeking Hashes")
        r = time.time()
        matches.extend(self.dejavu.find_matches_from_hashes(data, preserve_offsets=True))
        r = time.time() - r
        print("Matching hashes added.")
        self.seek_time += r
        # return self.dejavu.align_matches_by_overlap(matches)
        # The callback does not do anything with a return value so rendering one seems waistful.

class SelfRecognizer(BaseRecognizer):
    def __init__(self, dejavu):
        super(SelfRecognizer, self).__init__(dejavu)

    def recognize_file(self, song_id):
        t = time.time()
        match_data = self._recognize(song_id)
        t = time.time() - t

        if match_data:
            matches = self.dejavu.process_results(match_data, skip=0)

            return matches, {'load_time': '-', 'recognize_time': t}

    def recognize(self, song_id):
        return self.recognize_file(song_id)

    def _recognize(self, song_id):
        matches = []
        matches.extend(self.dejavu.find_self_matches(song_id, preserve_offsets=True))
        return self.dejavu.align_matches_by_overlap(matches)

class MicrophoneRecognizer(BaseRecognizer):
    default_chunksize   = 8192
    default_format      = pyaudio.paInt16
    default_channels    = 2
    default_samplerate  = 44100

    def __init__(self, dejavu):
        super(MicrophoneRecognizer, self).__init__(dejavu)
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.data = []
        self.channels = MicrophoneRecognizer.default_channels
        self.chunksize = MicrophoneRecognizer.default_chunksize
        self.samplerate = MicrophoneRecognizer.default_samplerate
        self.recorded = False

    def start_recording(self, channels=default_channels,
                        samplerate=default_samplerate,
                        chunksize=default_chunksize):
        self.chunksize = chunksize
        self.channels = channels
        self.recorded = False
        self.samplerate = samplerate

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()

        self.stream = self.audio.open(
            format=self.default_format,
            channels=channels,
            rate=samplerate,
            input=True,
            frames_per_buffer=chunksize,
        )

        self.data = [[] for i in range(channels)]

    def process_recording(self):
        data = self.stream.read(self.chunksize)
        nums = np.fromstring(data, np.int16)
        for c in range(self.channels):
            self.data[c].extend(nums[c::self.channels])

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

    def recognize(self, seconds=10):
        self.start_recording()
        for i in range(0, int(self.samplerate / self.chunksize
                              * seconds)):
            self.process_recording()
        self.stop_recording()
        return self.recognize_recording()


class NoRecordingError(Exception):
    pass
