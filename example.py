import warnings
import json
import os
warnings.filterwarnings("ignore")

from dejavu import Dejavu
from dejavu.recognize import FileRecognizer, MicrophoneRecognizer

# checking to see if running in Docker container
env_is_docker = os.getenv('DOCKER_ENV', False)
if env_is_docker:
	print "You are running Dejavu in Docker! :)"
config_file_name = "dejavu.cnf.DOCKER" if env_is_docker else "dejavu.cnf.SAMPLE"

# load config from a JSON file (or anything outputting a python dictionary)
with open(config_file_name) as f:
    config = json.load(f)

if __name__ == '__main__':

	# create a Dejavu instance
	djv = Dejavu(config)

	# Fingerprint all the mp3's in the directory we give it
	djv.fingerprint_directory("mp3", [".mp3"])

	# Recognize audio from a file
	song = djv.recognize(FileRecognizer, "mp3/Sean-Fournier--Falling-For-You.mp3")
	print "From file we recognized: %s\n" % song

	# Or recognize audio from your microphone for `secs` seconds
	if not env_is_docker:
		secs = 5
		song = djv.recognize(MicrophoneRecognizer, seconds=secs)
		if song is None:
			print "Nothing recognized -- did you play the song out loud so your mic could hear it? :)"
		else:
			print "From mic with %d seconds we recognized: %s\n" % (secs, song)
	else:
		print "Microphone input isn't support using Docker. Skipping microphone recognition..."

	# Or use a recognizer without the shortcut, in anyway you would like
	recognizer = FileRecognizer(djv)
	song = recognizer.recognize_file("mp3/Josh-Woodward--I-Want-To-Destroy-Something-Beautiful.mp3")
	print "No shortcut, we recognized: %s\n" % song