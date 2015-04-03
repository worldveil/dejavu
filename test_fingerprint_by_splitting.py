from dejavu import Dejavu
import warnings
import json
import os, subprocess
warnings.filterwarnings("ignore")

# load config from a JSON file (or anything outputting a python dictionary)
with open("dejavu.cnf.SAMPLE") as f:
    config = json.load(f)

class ConcatError(Exception):
    def __init__(self, list_file, output_file, error_code):
        Exception.__init__(self)
        self.list_file = list_file
        self.error_code = error_code
        self.output_file = output_file

    def __str__(self):
        return "Problem with list file({0}). Failed to create({1}). ffmpeg returned error code: {2}".format(self.list_file, self.output_file, self.error_code)


if __name__ == '__main__':
    '''
    Concatenates ./mp3/*.mp3
    Test fingerprinting the long concatenated file
    '''
    list_file = "mp3/concatenation_list.txt"
    long_song = "mp3/concatenated.mp3"

    concat_mp3_file_for_test = "ffmpeg -f concat -i {0} -y -c copy {1}".format(list_file, long_song)
    retcode = subprocess.call(concat_mp3_file_for_test, stderr=open(os.devnull))
    if retcode != 0:
        raise ConcatError(list_file, long_song, retcode)

    # create a Dejavu instance
    djv = Dejavu(config)

    try:
        djv.fingerprint_file(long_song)
    except Exception as err:
        err = str(err) or "Memory Error" # Memory Errors does not have a string representation (as tested in Windows)
        print "Exception raised during common fingerprint_file():({0}) so will split the file".format(err)
    else:
        raise "This file was successfully ingerprinted and splitting was not needed"

    djv.fingerprint_with_duration_check(long_song, song_name="Concatenates12345",processes=3)


