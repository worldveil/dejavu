from dejavu import Dejavu
import warnings
import json
warnings.filterwarnings("ignore")

# load config from a JSON file (or anything outputting a python dictionary)
with open("dejavu.cnf.SAMPLE") as f:
    config = json.load(f)

# create a Dejavu instance
djv = Dejavu(config)

# Fingerprint all the mp3's in the directory we give it
djv.fingerprint_directory("mp3", [".mp3"])

# Recognize audio from a file
from dejavu.recognize import FileRecognizer
song = djv.recognize(FileRecognizer, "mp3/Sean-Fournier--Falling-For-You.mp3")
print "From file we recognized: %s\n" % song

# Or recognize audio from your microphone for `secs` seconds
from dejavu.recognize import MicrophoneRecognizer
secs = 5
song = djv.recognize(MicrophoneRecognizer, seconds=secs)
if song is None:
	print "Nothing recognized -- did you play the song out loud so your mic could hear it? :)"
else:
	print "From mic with %d seconds we recognized: %s\n" % (secs, song)

# Or use a recognizer without the shortcut, in anyway you would like
from dejavu.recognize import FileRecognizer
recognizer = FileRecognizer(djv)
song = recognizer.recognize_file("mp3/Josh-Woodward--I-Want-To-Destroy-Something-Beautiful.mp3")
print "No shortcut, we recognized: %s\n" % song