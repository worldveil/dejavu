#!/usr/bin/python

import sys
import json
import warnings

from dejavu import Dejavu
from dejavu.recognize import FileRecognizer
from dejavu.recognize import MicrophoneRecognizer
from dejavu.recognize import FileRecognizer

warnings.filterwarnings("ignore")

def init():
    # load config from a JSON file (or anything outputting a python dictionary)
    with open("dejavu.cnf") as f:
        config = json.load(f)

    # create a Dejavu instance
    return Dejavu(config)

def showHelp():
    print ""
    print "------------------------------------------------"
    print "DejaVu audio fingerprinting and recognition tool"
    print "------------------------------------------------"
    print ""
    print "Usage: dejavu.py [command] [arguments]"
    print ""
    print "Available commands:"
    print ""
    print "  Fingerprint a file"
    print "    dejavu.py fingerprint /path/to/file.extension"
    print ""
    print "  Fingerprint all files in a directory"
    print "    dejavu.py fingerprint /path/to/directory extension"
    print ""
    print "  Recognize what is playing through the microphone"
    print "    dejavu.py recognize mic number_of_seconds"
    print ""
    print "  Recognize a file by listening to it"
    print "    dejavu.py recognize file /path/to/file"
    print ""
    print "  Display this help screen"
    print "    dejavu.py help"
    print ""
    exit

if len(sys.argv) > 1:
    command = sys.argv[1]
else:
    showHelp()

if command == 'fingerprint': # Fingerprint all files in a directory

    djv = init()
    

    if len(sys.argv) == 4:

        directory = sys.argv[2]
        extension = sys.argv[3]
        print "Fingerprinting all .%s files in the %s directory" % (extension, directory)

        djv.fingerprint_directory(directory, ["." + extension], 4)

    else:

        filepath = sys.argv[2]
        djv.fingerprint_file(filepath)

elif command == 'recognize': # Recognize audio

    source = sys.argv[2]
    song = None

    if source in ['mic', 'microphone']:

        seconds = int(sys.argv[3])
        djv = init()
        song = djv.recognize(MicrophoneRecognizer, seconds=seconds)

    elif source == 'file':

        djv = init()
        sourceFile = sys.argv[3]
        song = djv.recognize(FileRecognizer, sourceFile)

    else:

        showHelp()

    print song

else:

    showHelp()

