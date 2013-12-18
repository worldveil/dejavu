import os, fnmatch
from pydub import AudioSegment

class Converter():

    WAV = "wav"
    MP3 = "mp3"
    FORMATS = [
        WAV,
        MP3]

    def __init__(self, config):
        self.config = config
        if self.config.has_section("input") and self.config.has_option("input", "lenght"):
            self.max_input_len = int(self.config.get("input", "lenght"))
        else:        
            self.max_input_len = None

    def ensure_folder(self, extension):
        if not os.path.exists(extension):
            os.makedirs(extension)

    def find_files(self, path, extensions):
        filepaths = []
        extensions = [e.replace(".", "") for e in extensions if e.replace(".", "") in Converter.FORMATS]
        print "Supported formats: %s" % extensions
        for dirpath, dirnames, files in os.walk(path):
            for extension in extensions:
                for f in fnmatch.filter(files, "*.%s" % extension):
                    p = os.path.join(dirpath, f)
                    #print "Found file: %s with extension %s" % (renamed, extension)
                    filepaths.append((p, extension))
        return filepaths

    def convert(self, orig_path, from_format, to_format, output_folder):
        path, song_name = os.path.split(orig_path)
        # start conversion
        self.ensure_folder(output_folder)
        print "-> Now converting: %s from %s format to %s format..." % (song_name, from_format, to_format)
        # MP3 --> WAV
        if from_format == Converter.MP3 and to_format == Converter.WAV:

            newpath = os.path.join(output_folder, "%s.%s" % (song_name, Converter.WAV))
            if os.path.isfile(newpath):
                print "-> Already converted, skipping..."
            else:
                mp3file = AudioSegment.from_mp3(orig_path)
                if self.max_input_len:
                    print "-> Reading input seconds: ", self.max_input_len
                    mp3file = mp3file[:self.max_input_len * 1000]
                mp3file.export(newpath, format=Converter.WAV)

        # unsupported
        else:
            print "CONVERSION ERROR:\nThe conversion from %s to %s is not supported!" % (from_format, to_format)

        print "-> Conversion complete."
        return newpath
