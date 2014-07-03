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

# Or recognize audio from your microphone for 10 seconds
from dejavu.recognize import MicrophoneRecognizer
song = djv.recognize(MicrophoneRecognizer, seconds=2)

# Or use a recognizer without the shortcut, in anyway you would like
from dejavu.recognize import FileRecognizer
recognizer = FileRecognizer(djv)
song = recognizer.recognize_file("mp3/Josh-Woodward--I-Want-To-Destroy-Something-Beautiful.mp3")