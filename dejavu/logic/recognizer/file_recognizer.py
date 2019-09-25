import time

import dejavu.logic.decoder as decoder
from dejavu.base_classes.base_recognizer import BaseRecognizer


class FileRecognizer(BaseRecognizer):
    def __init__(self, dejavu):
        super().__init__(dejavu)

    def recognize_file(self, filename):
        frames, self.Fs, file_hash = decoder.read(filename, self.dejavu.limit)

        t = time.time()
        matches = self._recognize(*frames)
        t = time.time() - t

        for match in matches:
            match['match_time'] = t

        return matches

    def recognize(self, filename):
        return self.recognize_file(filename)
