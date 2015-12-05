import warnings
import json
warnings.filterwarnings("ignore")

from dejavu import Dejavu
from dejavu.recognize import FileRecognizer, MicrophoneRecognizer

# load config from a JSON file (or anything outputting a python dictionary)
with open("dejavu.cnf.SAMPLE") as f:
    config = json.load(f)

if __name__ == '__main__':

	# create a Dejavu instance
	djv = Dejavu(config)

	# Or recognize audio from your microphone for `secs` seconds
	secs = 8
	song = djv.recognize(MicrophoneRecognizer, seconds=secs)
	if song is None:
		print "Nothing recognized -- did you play the song out loud so your mic could hear it? :)"
	else:
		print "From mic with %d seconds we recognized: %s\n" % (secs, song)
