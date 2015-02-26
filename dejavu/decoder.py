import os
import fnmatch
import numpy as np
from pydub import AudioSegment
import wavio

def find_files(path, extensions):
    # Allow both with ".mp3" and without "mp3" to be used for extensions
    extensions = [e.replace(".", "") for e in extensions]

    for dirpath, dirnames, files in os.walk(path):
        for extension in extensions:
            for f in fnmatch.filter(files, "*.%s" % extension):
                p = os.path.join(dirpath, f)
                yield (p, extension)


def read(filename, limit=None):
    """
    Reads any file supported by pydub (ffmpeg) and returns the data contained
    within.

    Can be optionally limited to a certain amount of seconds from the start
    of the file by specifying the `limit` parameter. This is the amount of
    seconds from the start of the file.

    returns: (channels, samplerate)
    """
    audiofile = AudioSegment.from_file(filename)

    if limit:
        audiofile = audiofile[:limit * 1000]

    data = np.fromstring(audiofile._data, np.int16)

    channels = []
    for chn in xrange(audiofile.channels):
        channels.append(data[chn::audiofile.channels])

    return channels, audiofile.frame_rate


def path_to_songname(path):
    """
    Extracts song name from a filepath. Used to identify which songs
    have already been fingerprinted on disk.
    """
    return os.path.splitext(os.path.basename(path))[0]
