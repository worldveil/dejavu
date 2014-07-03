# result generator for dejavu

# TODO: Don't work very well with musics with special chars.
# use test file on the format below, with no special chars and only one "-" to separate artist from song

import os, subprocess, json, re, sys
import logging, time
from os import listdir
from os.path import isfile, join
import numpy as np
import matplotlib.pyplot as plt
from optparse import OptionParser
from dejavu.decoder import path_to_songname
import ast

#####
### 	Test files are in specific format:
###		'artist_name'-'song_name'_'start_time'_'duration'sec.wav
#####

DEFAULT_FS = 44100
DEFAULT_WINDOW_SIZE = 4096
DEFAULT_OVERLAP_RATIO = 0.5

FIELD_SONG_NAME				= 'song_name'
FIELD_CONFIDENCE			= 'confidence'
FIELD_QUERY_TIME			= 'match_time'
FIELD_OFFSET				= 'offset'

# Parse options 
usage = "usage: %prog [options] DEJAVU_PATH TEST_FOLDER"
parser = OptionParser(usage=usage, version="%prog 1.1")
parser.add_option("--no-log",
				  action="store_false",
                  dest="log",
                  default=True,
                  help='Disables logging')
parser.add_option("--log-file",
                  dest="log_file",
                  default="results-compare.log",
                  metavar="LOG_FILE",
                  help='Set the path and filename of the log file')
parser.add_option("--test-seconds",
				  action="append",
                  dest="test_seconds",
                  default=[],
                  metavar="Xsec",
                  help='Appends seconds to test suit')
parser.add_option("--results-folder",
				  action="store",
                  dest="results_folder",
                  metavar="FOLDER",
                  help='Sets the path where the results are saved')

(options, args) = parser.parse_args()

if len(args) != 2:
	parser.error("wrong number of arguments")

if len(options.test_seconds) == 0:
	options.test_seconds = ['1sec','2sec','3sec','4sec','5sec','6sec','7sec','8sec','9sec','10sec']

if options.log == True:
	logging.basicConfig(filename=options.log_file, level=logging.DEBUG)

if options.results_folder != "" and options.results_folder[len(options.results_folder) - 1] != '/':
	options.results_folder += "/"

# ensure results folder exists
try:
    os.stat(options.results_folder)
except:
    os.mkdir(options.results_folder)  

def log_msg(msg):
	if options.log == True:
		logging.debug(msg)

class DejavuTest (object):
	def __init__(self, folder, seconds):
		super(DejavuTest, self).__init__()

		self.test_folder = folder
		self.test_seconds = seconds
		self.test_songs = []
		self.test_files = [ f for f in listdir(self.test_folder) if isfile(join(self.test_folder,f)) 
			and re.findall("[0-9]*sec",f)[0] in self.test_seconds ]
		self.n_columns = len(self.test_seconds)
		self.n_lines = len(self.test_files) / self.n_columns 

		# variable match results (yes, no, invalid)
		self.result_match = [[0 for x in xrange(self.n_columns)] for x in xrange(self.n_lines)] 

		print "columns:", self.n_columns
		print "length of test files:", len(self.test_files)
		print "lines:", self.n_lines
		print "result_match matrix:", self.result_match 

		# variable match precision (if matched in the corrected time)
		self.result_matching_times = [[0 for x in xrange(self.n_columns)] for x in xrange(self.n_lines)] 

		# variable mahing time (query time) 
		self.result_query_duration = [[0 for x in xrange(self.n_columns)] for x in xrange(self.n_lines)] 

		# variable confidence
		self.result_match_confidence = [[0 for x in xrange(self.n_columns)] for x in xrange(self.n_lines)] 

		self.begin()

	def get_column_id (self, secs):
		for i, sec in enumerate(self.test_seconds):
			if secs == sec:
				return i

	def get_line_id (self, song):
		for i, s in enumerate(self.test_songs):
			if song == s:
				return i
		self.test_songs.append(song)
		return len(self.test_songs) - 1

	def begin(self):
		for f in self.test_files:
			log_msg('--------------------------------------------------')
			log_msg('file: %s' % f)

			# get column 
			col = self.get_column_id(re.findall("[0-9]*sec",f)[0])
			song = path_to_songname(f).split("_")[0]  # format: XXXX_offset_length.mp3
			line = self.get_line_id (song)
			result = subprocess.check_output(["python", args[0] + "/dejavu.py", 'recognize', 'file', self.test_folder+"/"+f])
			log_msg('RESULT: %s' % result.strip() )

			if result.strip() == "None":
				log_msg('No match')
				self.result_match[line][col] = 'no'
				self.result_matching_times[line][col] = 0
				self.result_query_duration[line][col] = 0
				self.result_match_confidence[line][col] = 0
			
			else:
				result = result.strip()
				result = result.replace(" \'", ' "')
				result = result.replace("{\'", '{"')
				result = result.replace("\':", '":')
				result = result.replace("\',", '",')

				# which song did we predict?
				result = ast.literal_eval(result)
				print "result", result
				song_result = result["song_name"]
				log_msg('song: %s' % song)
				log_msg('song_result: %s' % song_result)

				if song_result != song:
					log_msg('invalid match')
					self.result_match[line][col] = 'invalid'
					self.result_matching_times[line][col] = 0
					self.result_query_duration[line][col] = 0
					self.result_match_confidence[line][col] = 0
				else:
					log_msg('correct match')
					print self.result_match
					self.result_match[line][col] = 'yes'
					self.result_query_duration[line][col] = round(result[FIELD_QUERY_TIME],3)
					self.result_match_confidence[line][col] = result[FIELD_CONFIDENCE]

					song_start_time = re.findall("\_[^\_]+",f)
					song_start_time = song_start_time[0].lstrip("_ ")

					#result_start_time = round((result[FIELD_SONG_DURATION] * result[FIELD_OFFSET]) / float(result[FIELD_SONG_SPEC_DURATION]), 0)
					result_start_time = round((result[FIELD_OFFSET] * DEFAULT_WINDOW_SIZE * DEFAULT_OVERLAP_RATIO) / (DEFAULT_FS),0)

					self.result_matching_times[line][col] = int(result_start_time) - int(song_start_time)
					if (abs(self.result_matching_times[line][col]) == 1):
						self.result_matching_times[line][col] = 0

					log_msg('query duration: %s' % round(result[FIELD_QUERY_TIME],3))
					log_msg('confidence: %s' % result[FIELD_CONFIDENCE])
					log_msg('song start_time: %s' % song_start_time)
					log_msg('result start time: %s' % result_start_time)
					if (self.result_matching_times[line][col] == 0):
						log_msg('accurate match')
					else:
						log_msg('inaccurate match')
			log_msg('--------------------------------------------------\n')

print "obtaining results from dejavu"
log_msg('obtaining results from dejavu')
tm = time.time()
djv = DejavuTest(args[1], options.test_seconds)
print "finished obtaining results from dejavu in %s" % (time.time() - tm)
log_msg("finished obtaining results from dejavu in %s" % (time.time() - tm))

tests_n_lines = djv.n_lines
tests_n_columns = djv.n_columns # len(options.test_seconds)
tests = 1 # djv
n_secs = len(options.test_seconds) # = tests.n_columns

# set result variables -> 4d variables
all_match_counter = [[[0 for x in xrange(tests)] for x in xrange(3)] for x in xrange(n_secs)]
all_matching_times_counter = [[[0 for x in xrange(tests)] for x in xrange(2)] for x in xrange(n_secs)]
all_query_duration = [[[0 for x in xrange(tests)] for x in xrange(tests_n_lines)] for x in xrange(n_secs)]
all_match_confidence = [[[0 for x in xrange(tests)] for x in xrange(tests_n_lines)] for x in xrange(n_secs)]

# agroup results by seconds
for line in range(0, tests_n_lines):
	for col in range(0, tests_n_columns):
		# for dejavu
		all_query_duration[col][line][0] = djv.result_query_duration[line][col]
		all_match_confidence[col][line][0] = djv.result_match_confidence[line][col]

		djv_match_result = djv.result_match[line][col]

		if djv_match_result == 'yes':
			all_match_counter[col][0][0] += 1
		elif djv_match_result == 'no':
			all_match_counter[col][1][0] += 1
		else:
			all_match_counter[col][2][0] += 1

		djv_match_acc = djv.result_matching_times[line][col]

		if djv_match_acc == 0 and djv_match_result == 'yes':
			all_matching_times_counter[col][0][0] += 1
		elif djv_match_acc != 0:
			all_matching_times_counter[col][1][0] += 1

def autolabel(rects,ax):
    # attach some text labels
    for rect in rects:
        height = rect.get_height()
        ax.text(rect.get_x()+rect.get_width()/2., 1.05*height, '%d'%int(height),
                ha='center', va='bottom')

def autolabeldoubles(rects,ax):
    # attach some text labels
    for rect in rects:
        height = rect.get_height()
        ax.text(rect.get_x()+rect.get_width()/2., 1.05*height, '%s'%round(float(height),3),
                ha='center', va='bottom')

def create_plots(name,results):
	for sec in range(0,n_secs):
		ind = np.arange(tests_n_lines) #
		width = 0.25       # the width of the bars

		fig = plt.figure()
		ax = fig.add_subplot(111)
		ax.set_xlim([-1*width, 2*width])

		means_dvj = [x[0] for x in results[sec]]
		rects1 = ax.bar(ind, means_dvj, width, color='r')

		# add some
		ax.set_ylabel(name)
		ax.set_title("%s %s Results" % (options.test_seconds[sec],name)) 
		ax.set_xticks(ind+width)

		labels = [0 for x in range(0,tests_n_lines)]
		for x in range(0,tests_n_lines):
			labels[x] = "song %s" % (x+1)
		ax.set_xticklabels( labels )

		box = ax.get_position()
		ax.set_position([box.x0, box.y0, box.width * 0.75, box.height])

		#ax.legend( (rects1[0]), ('Dejavu'), loc='center left', bbox_to_anchor=(1, 0.5))

		if name == 'Confidence':
			autolabel(rects1,ax)
		else:
			autolabeldoubles(rects1,ax)

		plt.grid()

		fig_name = "%s%s_%s.png" % (options.results_folder,name,options.test_seconds[sec])
		fig.savefig(fig_name)

create_plots('Confidence',all_match_confidence)
create_plots('Query duration',all_query_duration)

for sec in range(0,n_secs):
	ind = np.arange(3) #
	width = 0.25       # the width of the bars

	fig = plt.figure()
	ax = fig.add_subplot(111)
	ax.set_xlim([-1*width, 2.75])

	means_dvj = [round(x[0]*100/tests_n_lines,1) for x in all_match_counter[sec]]
	rects1 = ax.bar(ind, means_dvj, width, color='r')

	# add some
	ax.set_ylabel('Matching Percentage')
	ax.set_title('%s Matching Percentage' % options.test_seconds[sec])
	ax.set_xticks(ind+width)

	labels = ['yes','no','invalid']
	ax.set_xticklabels( labels )

	box = ax.get_position()
	ax.set_position([box.x0, box.y0, box.width * 0.75, box.height])

	#ax.legend( (rects1[0]), ('Dejavu'), loc='center left', bbox_to_anchor=(1, 0.5))
	autolabeldoubles(rects1,ax)

	plt.grid()

 	fig_name = "%smatching_perc_%s.png" % (options.results_folder,options.test_seconds[sec])
 	fig.savefig(fig_name)

for sec in range(0,n_secs):
	ind = np.arange(2) #
	width = 0.25       # the width of the bars

	fig = plt.figure()
	ax = fig.add_subplot(111)
	ax.set_xlim([-1*width, 1.75])

	div = all_match_counter[sec][0][0]
	if div == 0 :
		div = 1000000

	means_dvj = [round(x[0]*100/div,1) for x in all_matching_times_counter[sec]]
	rects1 = ax.bar(ind, means_dvj, width, color='r')

	# add some
	ax.set_ylabel('Matching Accuracy')
	ax.set_title('%s Matching Times Accuracy' % options.test_seconds[sec])
	ax.set_xticks(ind+width)

	labels = ['yes','no']
	ax.set_xticklabels( labels )

	box = ax.get_position()
	ax.set_position([box.x0, box.y0, box.width * 0.75, box.height])

	#ax.legend( (rects1[0]), ('Dejavu'), loc='center left', bbox_to_anchor=(1, 0.5))
	autolabeldoubles(rects1,ax)

	plt.grid()

 	fig_name = "%smatching_acc_%s.png" % (options.results_folder,options.test_seconds[sec])
 	fig.savefig(fig_name)
