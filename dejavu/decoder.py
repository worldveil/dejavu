import os
import fnmatch
import numpy as np
from math import ceil
from pydub import AudioSegment
from pydub.utils import audioop
from dejavu import wavio
from hashlib import sha1

def unique_hash(filepath, blocksize=2**20):
    """ Small function to generate a hash to uniquely generate
    a file. Inspired by MD5 version here:
    http://stackoverflow.com/a/1131255/712997

    Works with large files. 
    """
    s = sha1()
    with open(filepath , "rb") as f:
        while True:
            buf = f.read(blocksize)
            if not buf:
                break
            s.update(buf)
    return s.hexdigest().upper()


def find_files(path, extensions):
    # Allow both with ".mp3" and without "mp3" to be used for extensions
    extensions = [e.replace(".", "") for e in extensions]

    for dirpath, dirnames, files in os.walk(path):
        for extension in extensions:
            for f in fnmatch.filter(files, "*.%s" % extension):
                p = os.path.join(dirpath, f)
                yield (p, extension)


def read(filename, limit=float('inf'), skip=0):
    """
    Reads any file supported by pydub (ffmpeg) and returns the data contained
    within. If file reading fails due to input being a 24-bit wav file,
    wavio is used as a backup.

    Can be optionally limited to a certain amount of seconds from the start
    of the file by specifying the `limit` parameter. This is the amount of
    seconds from the start of the file.

    returns: (channels, samplerate)
    """
    # pydub does not support 24-bit wav files, use wavio when this occurs
    try:
        audiofile = AudioSegment.from_file(filename)

        limit = float('inf') if limit is None else limit

        print("Length", len(audiofile), " = ", skip + limit, " + ", (skip + limit) * 1000)

        if limit and len(audiofile) > (skip + limit) * 1000:
            print("Option 1")
            audiofile = audiofile[skip * 1000:(skip + limit) * 1000]
        else:
            print("Option 2")
            audiofile = audiofile[skip * 1000:]

        data = np.fromstring(audiofile._data, np.int16)

        channels = []
        for chn in range(audiofile.channels):
            channels.append(data[chn::audiofile.channels])

        fs = audiofile.frame_rate
    except audioop.error:
        fs, _, audiofile = wavio.readwav(filename)

        if limit:
            audiofile = audiofile[:limit * 1000]

        audiofile = audiofile.T
        audiofile = audiofile.astype(np.int16)

        channels = []
        for chn in audiofile:
            channels.append(chn)

    return channels, audiofile.frame_rate, unique_hash(filename)

def read_as_memory_chuncks(filename, chunk_size = 4 * 60 * 1000):
    """
    Reads any file supported by pydub (ffmpeg) and returns the data contained
    within. If file reading fails due to input being a 24-bit wav file,
    wavio is used as a backup.

    Can be optionally limited to a certain amount of seconds from the start
    of the file by specifying the `limit` parameter. This is the amount of
    seconds from the start of the file.

    returns: (channels, samplerate)
    """

    audiofile = AudioSegment.from_file(filename)    

    chunks_needed = ceil( len(audiofile) / chunk_size )

    print("Length", len(audiofile), " (", seconds_to_hms(len(audiofile)//1000),") -", chunks_needed, "chunks")
    
    audio_file_chunks = []
    for chunk_number in range(chunks_needed):
        yield audiofile[chunk_size * chunk_number : chunk_size * (chunk_number + 1)]

def read_chunk(audiofile):
    try:
        data = np.fromstring(audiofile._data, np.int16)

        channels = []
        for chn in range(audiofile.channels):
            channels.append(data[chn::audiofile.channels])

        fs = audiofile.frame_rate
    except audioop.error:
        fs, _, audiofile = wavio.readwav(filename)

        if limit:
            audiofile = audiofile

        audiofile = audiofile.T
        audiofile = audiofile.astype(np.int16)

        channels = []
        for chn in audiofile:
            channels.append(chn)

    return channels, audiofile.frame_rate

def length(filename, audiofile=None):
    """
    Uses pydub to figure out the length of an audio file in milliseconds.
    """
    # pydub does not support 24-bit wav files, use wavio when this occurs
    try:
        audiofile = AudioSegment.from_file(filename) if audiofile is None else audiofile

    except audioop.error:
        fs, _, audiofile = wavio.readwav(filename)

        if limit:
            audiofile = audiofile[:limit * 1000]

        audiofile = audiofile.T
        audiofile = audiofile.astype(np.int16)


    return len(audiofile)


def path_to_songname(path):
    """
    Extracts song name from a filepath. Used to identify which songs
    have already been fingerprinted on disk.
    """
    return os.path.splitext(os.path.basename(path))[0]

def seconds_to_hms(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)

    if h > 0:
        return "%d:%02d:%02d" % (h, m, s) 
    elif m > 0 and m < 10:
        return "%01d:%02d" % (m, s)
    elif m > 0:
        return "%02d:%02d" % (m, s)
    elif s > 0 and s < 90:
        return ":%02d" % (s,)
    else:
        return "%i" % (s,)
    