from dejavu.testing import *
from dejavu import Dejavu
from optparse import OptionParser
import matplotlib.pyplot as plt
import time
import shutil

usage = "usage: %prog [options] TESTING_AUDIOFOLDER"
parser = OptionParser(usage=usage, version="%prog 1.1")
parser.add_option("--secs",
                  action="store",
                  dest="secs",
                  default=5,
                  type=int,
                  help='Number of seconds starting from zero to test')
parser.add_option("--results",
                  action="store",
                  dest="results_folder",
                  default="./dejavu_test_results",
                  help='Sets the path where the results are saved')
parser.add_option("--temp",
                  action="store",
                  dest="temp_folder",
                  default="./dejavu_temp_testing_files",
                  help='Sets the path where the temp files are saved')
parser.add_option("--log",
                  action="store_true",
                  dest="log",
                  default=True,
                  help='Enables logging')
parser.add_option("--silent",
                  action="store_false",
                  dest="silent",
                  default=False,
                  help='Disables printing')
parser.add_option("--log-file",
                  dest="log_file",
                  default="results-compare.log",
                  help='Set the path and filename of the log file')
parser.add_option("--padding",
                  action="store",
                  dest="padding",
                  default=10,
                  type=int,
                  help='Number of seconds to pad choice of place to test from')
parser.add_option("--seed",
                  action="store",
                  dest="seed",
                  default=None,
                  type=int,
                  help='Random seed')
options, args = parser.parse_args()
test_folder = args[0]

# set random seed if set by user
set_seed(options.seed)

# ensure results folder exists
try:
    os.stat(options.results_folder)
except:
    os.mkdir(options.results_folder)

# set logging 
if options.log:
    logging.basicConfig(filename=options.log_file, level=logging.DEBUG)

# set test seconds
test_seconds = ['%dsec' % i for i in range(1, options.secs + 1, 1)]

# generate testing files
for i in range(1, options.secs + 1, 1):
    generate_test_files(test_folder, options.temp_folder, 
                        i, padding=options.padding)

# scan files
log_msg("Running Dejavu fingerprinter on files in %s..." % test_folder, 
        log=options.log, silent=options.silent)

tm = time.time()
djv = DejavuTest(options.temp_folder, test_seconds)
log_msg("finished obtaining results from dejavu in %s" % (time.time() - tm),
        log=options.log, silent=options.silent)

tests = 1  # djv
n_secs = len(test_seconds) 

# set result variables -> 4d variables
all_match_counter = [[[0 for x in xrange(tests)] for x in xrange(3)] for x in xrange(n_secs)]
all_matching_times_counter = [[[0 for x in xrange(tests)] for x in xrange(2)] for x in xrange(n_secs)]
all_query_duration = [[[0 for x in xrange(tests)] for x in xrange(djv.n_lines)] for x in xrange(n_secs)]
all_match_confidence = [[[0 for x in xrange(tests)] for x in xrange(djv.n_lines)] for x in xrange(n_secs)]

# group results by seconds
for line in range(0, djv.n_lines):
	for col in range(0, djv.n_columns):
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

# create plots
djv.create_plots('Confidence', all_match_confidence, options.results_folder)
djv.create_plots('Query duration', all_query_duration, options.results_folder)

for sec in range(0, n_secs):
	ind = np.arange(3) #
	width = 0.25       # the width of the bars

	fig = plt.figure()
	ax = fig.add_subplot(111)
	ax.set_xlim([-1 * width, 2.75])

	means_dvj = [round(x[0] * 100 / djv.n_lines, 1) for x in all_match_counter[sec]]
	rects1 = ax.bar(ind, means_dvj, width, color='r')

	# add some
	ax.set_ylabel('Matching Percentage')
	ax.set_title('%s Matching Percentage' % test_seconds[sec])
	ax.set_xticks(ind + width)

	labels = ['yes','no','invalid']
	ax.set_xticklabels( labels )

	box = ax.get_position()
	ax.set_position([box.x0, box.y0, box.width * 0.75, box.height])
	#ax.legend((rects1[0]), ('Dejavu'), loc='center left', bbox_to_anchor=(1, 0.5))
	autolabeldoubles(rects1,ax)
	plt.grid()

 	fig_name = os.path.join(options.results_folder, "matching_perc_%s.png" % test_seconds[sec])
 	fig.savefig(fig_name)

for sec in range(0, n_secs):
	ind = np.arange(2) #
	width = 0.25       # the width of the bars

	fig = plt.figure()
	ax = fig.add_subplot(111)
	ax.set_xlim([-1*width, 1.75])

	div = all_match_counter[sec][0][0]
	if div == 0 :
		div = 1000000

	means_dvj = [round(x[0] * 100 / div, 1) for x in all_matching_times_counter[sec]]
	rects1 = ax.bar(ind, means_dvj, width, color='r')

	# add some
	ax.set_ylabel('Matching Accuracy')
	ax.set_title('%s Matching Times Accuracy' % test_seconds[sec])
	ax.set_xticks(ind + width)

	labels = ['yes','no']
	ax.set_xticklabels( labels )

	box = ax.get_position()
	ax.set_position([box.x0, box.y0, box.width * 0.75, box.height])

	#ax.legend( (rects1[0]), ('Dejavu'), loc='center left', bbox_to_anchor=(1, 0.5))
	autolabeldoubles(rects1,ax)

	plt.grid()

 	fig_name = os.path.join(options.results_folder, "matching_acc_%s.png" % test_seconds[sec])
 	fig.savefig(fig_name)

# remove temporary folder
shutil.rmtree(options.temp_folder)
