from dejavu import Dejavu
import warnings
import json
warnings.filterwarnings("ignore")

# load config from a JSON file (or anything outputting a python dictionary)
with open("dejavu.cnf") as f:
    config = json.load(f)

# create a Dejavu instance
djv = Dejavu(config)
# Fingerprint all the mp3's in the directory we give it
djv.fingerprint_directory("va_us_top_40/mp3", [".mp3"], 5)


# Recognize audio from a file
from dejavu.recognize import FileRecognizer
song = djv.recognize(FileRecognizer, "va_us_top_40/wav/17_-_#Beautiful_-_Mariah_Carey_ft.wav")


# Or recognize audio from your microphone for 10 seconds
from dejavu.recognize import MicrophoneRecognizer
song = djv.recognize(MicrophoneRecognizer, seconds=10)


# Or use a recognizer without the shortcut, in anyway you would like
from dejavu.recognize import FileRecognizer
recognizer = FileRecognizer(djv)
song = recognizer.recognize_file("va_us_top_40/wav/17_-_#Beautiful_-_Mariah_Carey_ft.wav")
