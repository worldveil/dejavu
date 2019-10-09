import argparse
import json
import sys
from argparse import RawTextHelpFormatter
from os.path import isdir

from dejavu import Dejavu
from dejavu.logic.recognizer.file_recognizer import FileRecognizer
from dejavu.logic.recognizer.microphone_recognizer import MicrophoneRecognizer

DEFAULT_CONFIG_FILE = "dejavu.cnf.SAMPLE"


def init(configpath):
    """
    Load config from a JSON file
    """
    try:
        with open(configpath) as f:
            config = json.load(f)
    except IOError as err:
        print(f"Cannot open configuration: {str(err)}. Exiting")
        sys.exit(1)

    # create a Dejavu instance
    return Dejavu(config)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Dejavu: Audio Fingerprinting library",
        formatter_class=RawTextHelpFormatter)
    parser.add_argument('-c', '--config', nargs='?',
                        help='Path to configuration file\n'
                             'Usages: \n'
                             '--config /path/to/config-file\n')
    parser.add_argument('-f', '--fingerprint', nargs='*',
                        help='Fingerprint files in a directory\n'
                             'Usages: \n'
                             '--fingerprint /path/to/directory extension\n'
                             '--fingerprint /path/to/directory')
    parser.add_argument('-r', '--recognize', nargs=2,
                        help='Recognize what is '
                             'playing through the microphone or in a file.\n'
                             'Usage: \n'
                             '--recognize mic number_of_seconds \n'
                             '--recognize file path/to/file \n')
    args = parser.parse_args()

    if not args.fingerprint and not args.recognize:
        parser.print_help()
        sys.exit(0)

    config_file = args.config
    if config_file is None:
        config_file = DEFAULT_CONFIG_FILE

    djv = init(config_file)
    if args.fingerprint:
        # Fingerprint all files in a directory
        if len(args.fingerprint) == 2:
            directory = args.fingerprint[0]
            extension = args.fingerprint[1]
            print(f"Fingerprinting all .{extension} files in the {directory} directory")
            djv.fingerprint_directory(directory, ["." + extension], 4)

        elif len(args.fingerprint) == 1:
            filepath = args.fingerprint[0]
            if isdir(filepath):
                print("Please specify an extension if you'd like to fingerprint a directory!")
                sys.exit(1)
            djv.fingerprint_file(filepath)

    elif args.recognize:
        # Recognize audio source
        songs = None
        source = args.recognize[0]
        opt_arg = args.recognize[1]

        if source in ('mic', 'microphone'):
            songs = djv.recognize(MicrophoneRecognizer, seconds=opt_arg)
        elif source == 'file':
            songs = djv.recognize(FileRecognizer, opt_arg)
        print(songs)
