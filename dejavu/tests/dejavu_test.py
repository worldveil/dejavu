import fnmatch
import json
import logging
import random
import re
import subprocess
import traceback
from os import listdir, makedirs, walk
from os.path import basename, exists, isfile, join, splitext

import matplotlib.pyplot as plt
import numpy as np
from pydub import AudioSegment

from dejavu.config.settings import (DEFAULT_FS, DEFAULT_OVERLAP_RATIO,
                                    DEFAULT_WINDOW_SIZE, HASHES_MATCHED,
                                    OFFSET, RESULTS, SONG_NAME, TOTAL_TIME)
from dejavu.logic.decoder import get_audio_name_from_path


class DejavuTest:
    def __init__(self, folder, seconds):
        super().__init__()

        self.test_folder = folder
        self.test_seconds = seconds
        self.test_songs = []

        print("test_seconds", self.test_seconds)

        self.test_files = [
            f for f in listdir(self.test_folder)
            if isfile(join(self.test_folder, f))
            and any([x for x in re.findall("[0-9]sec", f) if x in self.test_seconds])
        ]

        print("test_files", self.test_files)

        self.n_columns = len(self.test_seconds)
        self.n_lines = int(len(self.test_files) / self.n_columns)

        print("columns:", self.n_columns)
        print("length of test files:", len(self.test_files))
        print("lines:", self.n_lines)

        # variable match results (yes, no, invalid)
        self.result_match = [[0 for x in range(self.n_columns)] for x in range(self.n_lines)]

        print("result_match matrix:", self.result_match)

        # variable match precision (if matched in the corrected time)
        self.result_matching_times = [[0 for x in range(self.n_columns)] for x in range(self.n_lines)]

        # variable matching time (query time)
        self.result_query_duration = [[0 for x in range(self.n_columns)] for x in range(self.n_lines)]

        # variable confidence
        self.result_match_confidence = [[0 for x in range(self.n_columns)] for x in range(self.n_lines)]

        self.begin()

    def get_column_id(self, secs):
        for i, sec in enumerate(self.test_seconds):
            if secs == sec:
                return i

    def get_line_id(self, song):
        for i, s in enumerate(self.test_songs):
            if song == s:
                return i
        self.test_songs.append(song)
        return len(self.test_songs) - 1

    def create_plots(self, name, results, results_folder):
        for sec in range(0, len(self.test_seconds)):
            ind = np.arange(self.n_lines)
            width = 0.25       # the width of the bars

            fig = plt.figure()
            ax = fig.add_subplot(111)
            ax.set_xlim([-1 * width, 2 * width])

            means_dvj = [x[0] for x in results[sec]]
            rects1 = ax.bar(ind, means_dvj, width, color='r')

            # add some
            ax.set_ylabel(name)
            ax.set_title(f"{self.test_seconds[sec]} {name} Results")
            ax.set_xticks(ind + width)

            labels = [0 for x in range(0, self.n_lines)]
            for x in range(0, self.n_lines):
                labels[x] = f"song {x+1}"
            ax.set_xticklabels(labels)

            box = ax.get_position()
            ax.set_position([box.x0, box.y0, box.width * 0.75, box.height])

            if name == 'Confidence':
                autolabel(rects1, ax)
            else:
                autolabeldoubles(rects1, ax)

            plt.grid()

            fig_name = join(results_folder, f"{name}_{self.test_seconds[sec]}.png")
            fig.savefig(fig_name)

    def begin(self):
        for f in self.test_files:
            log_msg('--------------------------------------------------')
            log_msg(f'file: {f}')

            # get column
            col = self.get_column_id([x for x in re.findall("[0-9]sec", f) if x in self.test_seconds][0])

            # format: XXXX_offset_length.mp3, we also take into account underscores within XXXX
            splits = get_audio_name_from_path(f).split("_")
            song = "_".join(splits[0:len(get_audio_name_from_path(f).split("_")) - 2])
            line = self.get_line_id(song)
            result = subprocess.check_output([
                "python",
                "dejavu.py",
                '-r',
                'file',
                join(self.test_folder, f)])

            if result.strip() == "None":
                log_msg('No match')
                self.result_match[line][col] = 'no'
                self.result_matching_times[line][col] = 0
                self.result_query_duration[line][col] = 0
                self.result_match_confidence[line][col] = 0

            else:
                result = result.strip()
                # we parse the output song back to a json
                result = json.loads(result.decode('utf-8').replace("'", '"').replace(': b"', ':"'))

                # which song did we predict? We consider only the first match.
                match = result[RESULTS][0]
                song_result = match[SONG_NAME]
                log_msg(f'song: {song}')
                log_msg(f'song_result: {song_result}')

                if song_result != song:
                    log_msg('invalid match')
                    self.result_match[line][col] = 'invalid'
                    self.result_matching_times[line][col] = 0
                    self.result_query_duration[line][col] = 0
                    self.result_match_confidence[line][col] = 0
                else:
                    log_msg('correct match')
                    print(self.result_match)
                    self.result_match[line][col] = 'yes'
                    self.result_query_duration[line][col] = round(result[TOTAL_TIME], 3)
                    self.result_match_confidence[line][col] = match[HASHES_MATCHED]

                    # using replace in f for getting rid of underscores in name
                    song_start_time = re.findall("_[^_]+", f.replace(song, ""))
                    song_start_time = song_start_time[0].lstrip("_ ")

                    result_start_time = round((match[OFFSET] * DEFAULT_WINDOW_SIZE *
                                               DEFAULT_OVERLAP_RATIO) / DEFAULT_FS, 0)

                    self.result_matching_times[line][col] = int(result_start_time) - int(song_start_time)
                    if abs(self.result_matching_times[line][col]) == 1:
                        self.result_matching_times[line][col] = 0

                    log_msg(f'query duration: {round(result[TOTAL_TIME], 3)}')
                    log_msg(f'confidence: {match[HASHES_MATCHED]}')
                    log_msg(f'song start_time: {song_start_time}')
                    log_msg(f'result start time: {result_start_time}')

                    if self.result_matching_times[line][col] == 0:
                        log_msg('accurate match')
                    else:
                        log_msg('inaccurate match')
            log_msg('--------------------------------------------------\n')


def set_seed(seed=None):
    """
    `seed` as None means that the sampling will be random.

    Setting your own seed means that you can produce the
    same experiment over and over.
    """
    if seed is not None:
        random.seed(seed)


def get_files_recursive(src, fmt):
    """
    `src` is the source directory.
    `fmt` is the extension, ie ".mp3" or "mp3", etc.
    """
    files = []
    for root, dirnames, filenames in walk(src):
        for filename in fnmatch.filter(filenames, '*' + fmt):
            files.append(join(root, filename))

    return files


def get_length_audio(audiopath, extension):
    """
    Returns length of audio in seconds.
    Returns None if format isn't supported or in case of error.
    """
    try:
        audio = AudioSegment.from_file(audiopath, extension.replace(".", ""))
    except Exception:
        print(f"Error in get_length_audio(): {traceback.format_exc()}")
        return None
    return int(len(audio) / 1000.0)


def get_starttime(length, nseconds, padding):
    """
    `length` is total audio length in seconds
    `nseconds` is amount of time to sample in seconds
    `padding` is off-limits seconds at beginning and ending
    """
    maximum = length - padding - nseconds
    if padding > maximum:
        return 0
    return random.randint(padding, maximum)


def generate_test_files(src, dest, nseconds, fmts=[".mp3", ".wav"], padding=10):
    """
    Generates a test file for each file recursively in `src` directory
    of given format using `nseconds` sampled from the audio file.

    Results are written to `dest` directory.

    `padding` is the number of off-limit seconds and the beginning and
    end of a track that won't be sampled in testing. Often you want to
    avoid silence, etc.
    """
    # create directories if necessary
    if not exists(dest):
        makedirs(dest)

    # find files recursively of a given file format
    for fmt in fmts:
        testsources = get_files_recursive(src, fmt)
        for audiosource in testsources:

            print("audiosource:", audiosource)

            filename, extension = splitext(basename(audiosource))
            length = get_length_audio(audiosource, extension)
            starttime = get_starttime(length, nseconds, padding)

            test_file_name = f"{join(dest, filename)}_{starttime}_{nseconds}sec.{extension.replace('.', '')}"

            subprocess.check_output([
                "ffmpeg", "-y",
                "-ss", f"{starttime}",
                '-t', f"{nseconds}",
                "-i", audiosource,
                test_file_name])


def log_msg(msg, log=True, silent=False):
    if log:
        logging.debug(msg)
    if not silent:
        print(msg)


def autolabel(rects, ax):
    # attach some text labels
    for rect in rects:
        height = rect.get_height()
        ax.text(rect.get_x() + rect.get_width() / 2., 1.05 * height, f'{int(height)}', ha='center', va='bottom')


def autolabeldoubles(rects, ax):
    # attach some text labels
    for rect in rects:
        height = rect.get_height()
        ax.text(rect.get_x() + rect.get_width() / 2., 1.05 * height, f'{round(float(height), 3)}',
                ha='center', va='bottom')
