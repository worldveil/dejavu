import argparse
import logging
import time
from os import makedirs
from os.path import exists, join
from shutil import rmtree

import matplotlib.pyplot as plt
import numpy as np

from dejavu.tests.dejavu_test import (DejavuTest, autolabeldoubles,
                                      generate_test_files, log_msg, set_seed)


def main(seconds: int, results_folder: str, temp_folder: str, log: bool, silent: bool,
         log_file: str, padding: int, seed: int, src: str):

    # set random seed if set by user
    set_seed(seed)

    # ensure results folder exists
    if not exists(results_folder):
        makedirs(results_folder)

    # set logging
    if log:
        logging.basicConfig(filename=log_file, level=logging.DEBUG)

    # set test seconds
    test_seconds = [f'{i}sec' for i in range(1, seconds + 1, 1)]

    # generate testing files
    for i in range(1, seconds + 1, 1):
        generate_test_files(src, temp_folder, i, padding=padding)

    # scan files
    log_msg(f"Running Dejavu fingerprinter on files in {src}...", log=log, silent=silent)

    tm = time.time()
    djv = DejavuTest(temp_folder, test_seconds)
    log_msg(f"finished obtaining results from dejavu in {(time.time() - tm)}", log=log, silent=silent)

    tests = 1  # djv
    n_secs = len(test_seconds)

    # set result variables -> 4d variables
    all_match_counter = [[[0 for x in range(tests)] for x in range(3)] for x in range(n_secs)]
    all_matching_times_counter = [[[0 for x in range(tests)] for x in range(2)] for x in range(n_secs)]
    all_query_duration = [[[0 for x in range(tests)] for x in range(djv.n_lines)] for x in range(n_secs)]
    all_match_confidence = [[[0 for x in range(tests)] for x in range(djv.n_lines)] for x in range(n_secs)]

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
    djv.create_plots('Confidence', all_match_confidence, results_folder)
    djv.create_plots('Query duration', all_query_duration, results_folder)

    for sec in range(0, n_secs):
        ind = np.arange(3)
        width = 0.25  # the width of the bars

        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.set_xlim([-1 * width, 2.75])

        means_dvj = [round(x[0] * 100 / djv.n_lines, 1) for x in all_match_counter[sec]]
        rects1 = ax.bar(ind, means_dvj, width, color='r')

        # add some
        ax.set_ylabel('Matching Percentage')
        ax.set_title(f'{test_seconds[sec]} Matching Percentage')
        ax.set_xticks(ind + width)

        labels = ['yes', 'no', 'invalid']
        ax.set_xticklabels(labels)

        box = ax.get_position()
        ax.set_position([box.x0, box.y0, box.width * 0.75, box.height])
        autolabeldoubles(rects1, ax)
        plt.grid()

        fig_name = join(results_folder, f"matching_perc_{test_seconds[sec]}.png")
        fig.savefig(fig_name)

    for sec in range(0, n_secs):
        ind = np.arange(2)
        width = 0.25  # the width of the bars

        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.set_xlim([-1 * width, 1.75])

        div = all_match_counter[sec][0][0]
        if div == 0:
            div = 1000000

        means_dvj = [round(x[0] * 100 / div, 1) for x in all_matching_times_counter[sec]]
        rects1 = ax.bar(ind, means_dvj, width, color='r')

        # add some
        ax.set_ylabel('Matching Accuracy')
        ax.set_title(f'{test_seconds[sec]} Matching Times Accuracy')
        ax.set_xticks(ind + width)

        labels = ['yes', 'no']
        ax.set_xticklabels(labels)

        box = ax.get_position()
        ax.set_position([box.x0, box.y0, box.width * 0.75, box.height])
        autolabeldoubles(rects1, ax)

        plt.grid()

        fig_name = join(results_folder, f"matching_acc_{test_seconds[sec]}.png")
        fig.savefig(fig_name)

    # remove temporary folder
    rmtree(temp_folder)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'Runs a few tests for dejavu to evaluate '
                                                 f'its configuration performance. '
                                                 f'Usage: %(prog).py [options] TESTING_AUDIOFOLDER'
                                     )

    parser.add_argument("-sec", "--seconds", action="store", default=5, type=int,
                        help='Number of seconds starting from zero to test.')
    parser.add_argument("-res", "--results-folder", action="store", default="./dejavu_test_results",
                        help='Sets the path where the results are saved.')
    parser.add_argument("-temp", "--temp-folder", action="store", default="./dejavu_temp_testing_files",
                        help='Sets the path where the temp files are saved.')
    parser.add_argument("-l", "--log", action="store_true", default=False, help='Enables logging.')
    parser.add_argument("-sl", "--silent", action="store_false", default=False, help='Disables printing.')
    parser.add_argument("-lf", "--log-file", default="results-compare.log",
                        help='Set the path and filename of the log file.')
    parser.add_argument("-pad", "--padding", action="store", default=10, type=int,
                        help='Number of seconds to pad choice of place to test from.')
    parser.add_argument("-sd", "--seed", action="store", default=None, type=int, help='Random seed.')
    parser.add_argument("src", type=str, help='Source folder for audios to use as tests.')

    args = parser.parse_args()

    main(args.seconds, args.results_folder, args.temp_folder, args.log, args.silent, args.log_file, args.padding,
         args.seed, args.src)
