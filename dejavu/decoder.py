import os
import fnmatch
import hashlib
import numpy as np
from pydub import AudioSegment


def find_files(path, extensions):
    """ Returns all files in a path that match a certain extentsion.
    For users sake, you can pass in 'mp3' and '.mp3' and get the
    same results. Note, this is a generator.
    """
    for dirpath, dirnames, files in os.walk(path):
        for extension in [e.replace(".", "") for e in extensions]:
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
    Extracts an MD5 from a filepath. This is used to identify which
    songs have already been fingerprinted. Previously, a filepath string
    was used, but MD5 will guarantee the song is unique (if you change
    the name of the file using the old method, you were in a world of
    hurt).
    """
    path = os.path.splitext(os.path.basename(path))[0]
    return hashlib.md5(str(path)).digest()
