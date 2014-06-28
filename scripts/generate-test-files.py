import os, subprocess
from os import listdir
from os.path import isfile, join
from optparse import OptionParser

usage = "usage: %prog [options] SONGS_PATH DESTINATION_FOLDER"
parser = OptionParser(usage=usage, version="%prog 1.1")

parser.add_option("-s", "--start",
                  action="store",
                  dest="start_time",
                  type=int,
                  default=10,
                  metavar="X",
                  help='Test files begin on X sec of the original song'
                  )

parser.add_option("--test-seconds",
                  action="append",
                  dest="test_seconds",
                  type=int,
                  default=[],
                  metavar="X",
                  help='Sets the seconds of the test files'
                  )

parser.add_option("--audio-format",
                  action="append",
                  dest="audio_formats",
                  default=[],
                  metavar="FORMAT",
                  help='Sets audio formats of files to read'
                  )


(options, args) = parser.parse_args()

if len(args) != 2:
    parser.error("wrong number of arguments")

if args[0][len(args[0])-1] != "/":
    args[0] += "/"

if args[1][len(args[1])-1] != "/":
    args[1] += "/"

print "coisa : ", args[1]

if len(options.test_seconds) == 0:
    options.test_seconds = [1,2,3,4,5,6,7,8,9,10]

if len(options.audio_formats) == 0:
    options.audio_formats = ['wav','mp3']

test_files = [ f for f in listdir(args[0]) if isfile(join(args[0],f)) and 
    os.path.splitext(f)[len(os.path.splitext(f))-1][1:] in options.audio_formats ]

for file in test_files:

    filename = os.path.basename(file)
    filename,extension = os.path.splitext(filename)
    
    for i in options.test_seconds:

        test_file_name = "%s%s_%s_%ssec%s" % (args[1],filename,options.start_time,i,extension)
        subprocess.check_output(["ffmpeg", "-ss", "%s" % options.start_time, '-t' , "%s" % i, "-i", args[0]+file, test_file_name])
