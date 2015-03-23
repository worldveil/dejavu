from dejavu import Dejavu
import warnings
import json
warnings.filterwarnings("ignore")

# load config from a JSON file (or anything outputting a python dictionary)
with open("dejavu.cnf.SAMPLE") as f:
    config = json.load(f)


if __name__ == '__main__':
    '''
    This will audio files that are too long into sections.
    There are probably better libs to do this. 
    '''

    # create a Dejavu instance
    djv = Dejavu(config)

    # Fingerprint all the mp3's in the directory we give it
    # short_song = "./iskoTest/Josh-Woodward--I-Want-To-Destroy-Something-Beautiful.mp3"
    # djv.fingerprint_with_duration_check(short_song, minutes=3)

    long_song = "./iskoTest/Roger Penrose - Forbidden crystal symmetry in mathematics and architecture.mp3"
    djv.fingerprint_with_duration_check(long_song, minutes=3)


