import numpy as np
import matplotlib.mlab as mlab
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from scipy.io import wavfile
from scipy.ndimage.filters import maximum_filter
from scipy.ndimage.morphology import generate_binary_structure, iterate_structure, binary_erosion
from dejavu.database import SQLDatabase
import os
import wave
import sys
import time
import hashlib
import pickle

IDX_FREQ_I = 0
IDX_TIME_J = 1

DEFAULT_FS = 44100
DEFAULT_WINDOW_SIZE = 4096
DEFAULT_OVERLAP_RATIO = 0.5
DEFAULT_FAN_VALUE = 15

DEFAULT_AMP_MIN = 10
PEAK_NEIGHBORHOOD_SIZE = 20
MIN_HASH_TIME_DELTA = 0

def fingerprint(channel_samples,
            Fs=DEFAULT_FS, 
            wsize=DEFAULT_WINDOW_SIZE, 
            wratio=DEFAULT_OVERLAP_RATIO, 
            fan_value=DEFAULT_FAN_VALUE, 
            amp_min=DEFAULT_AMP_MIN):
    """
        FFT the channel, log transform output, find local maxima, then return
        locally sensitive hashes. 
    """
    # FFT the signal and extract frequency components
    arr2D = mlab.specgram(
        channel_samples, 
        NFFT=wsize, 
        Fs=Fs,
        window=mlab.window_hanning,
        noverlap=int(wsize * wratio))[0]

    # apply log transform since specgram() returns linear array
    arr2D = 10 * np.log10(arr2D)
    arr2D[arr2D == -np.inf] = 0 # replace infs with zeros
    
    # find local maxima
    local_maxima = get_2D_peaks(arr2D, plot=False, amp_min=amp_min)

    # return hashes
    return generate_hashes(local_maxima, fan_value=fan_value)

def get_2D_peaks(arr2D, plot=False, amp_min=DEFAULT_AMP_MIN):

    # http://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.morphology.iterate_structure.html#scipy.ndimage.morphology.iterate_structure
    struct = generate_binary_structure(2, 1)
    neighborhood = iterate_structure(struct, PEAK_NEIGHBORHOOD_SIZE)

    # find local maxima using our fliter shape
    local_max = maximum_filter(arr2D, footprint=neighborhood) == arr2D 
    background = (arr2D == 0)
    eroded_background = binary_erosion(background, structure=neighborhood, border_value=1)
    detected_peaks = local_max - eroded_background # this is a boolean mask of arr2D with True at peaks

    # extract peaks
    amps = arr2D[detected_peaks]
    j, i = np.where(detected_peaks) 

    # filter peaks
    amps = amps.flatten()
    peaks = zip(i, j, amps)
    peaks_filtered = [x for x in peaks if x[2] > amp_min] # freq, time, amp
    
    # get indices for frequency and time
    frequency_idx = [x[1] for x in peaks_filtered]
    time_idx = [x[0] for x in peaks_filtered]

    if plot:
        # scatter of the peaks
        fig, ax = plt.subplots()
        ax.imshow(arr2D)
        ax.scatter(time_idx, frequency_idx)
        ax.set_xlabel('Time')
        ax.set_ylabel('Frequency')
        ax.set_title("Spectrogram of \"Blurred Lines\" by Robin Thicke");
        plt.gca().invert_yaxis()
        plt.show()

    return zip(frequency_idx, time_idx)

def generate_hashes(peaks, fan_value=DEFAULT_FAN_VALUE):
    """
    Hash list structure:
       sha1-hash[0:20]    time_offset
    [(e05b341a9b77a51fd26, 32), ... ]
    """
    fingerprinted = set() # to avoid rehashing same pairs
    hashes = []

    for i in range(len(peaks)):
        for j in range(fan_value):
            if i+j < len(peaks) and not (i, i+j) in fingerprinted:
                
                freq1 = peaks[i][IDX_FREQ_I]
                freq2 = peaks[i+j][IDX_FREQ_I]
                t1 = peaks[i][IDX_TIME_J]
                t2 = peaks[i+j][IDX_TIME_J]
                t_delta = t2 - t1
                
                if t_delta >= MIN_HASH_TIME_DELTA:
                    h = hashlib.sha1("%s|%s|%s" % (str(freq1), str(freq2), str(t_delta)))
                    hashes.append((h.hexdigest()[0:20], t1))
                
                # ensure we don't repeat hashing
                fingerprinted.add((i, i+j))
    return hashes

# TODO: move all of the below to a class with DB access


class Fingerprinter():



    def __init__(self, config, 
            Fs=DEFAULT_FS, 
            wsize=DEFAULT_WINDOW_SIZE, 
            wratio=DEFAULT_OVERLAP_RATIO, 
            fan_value=DEFAULT_FAN_VALUE, 
            amp_min=DEFAULT_AMP_MIN):

        self.config = config
        database = SQLDatabase(
            self.config.get(SQLDatabase.CONNECTION, SQLDatabase.KEY_HOSTNAME),
            self.config.get(SQLDatabase.CONNECTION, SQLDatabase.KEY_USERNAME),
            self.config.get(SQLDatabase.CONNECTION, SQLDatabase.KEY_PASSWORD),
            self.config.get(SQLDatabase.CONNECTION, SQLDatabase.KEY_DATABASE))
        self.db = database

        self.Fs = Fs
        self.dt = 1.0 / self.Fs
        self.window_size = wsize
        self.window_overlap_ratio = wratio
        self.fan_value = fan_value
        self.noverlap = int(self.window_size * self.window_overlap_ratio)
        self.amp_min = amp_min

    def fingerprint(self, samples, path, sid, cid):
        """Used for learning known songs"""
        hashes = self.process_channel(samples, song_id=sid)
        print "Generated %d hashes" % len(hashes)
        self.db.insert_hashes(hashes)
    
    # TODO: put this in another module
    def match(self, samples):
        """Used for matching unknown songs"""
        hashes = self.process_channel(samples)
        matches = self.db.return_matches(hashes)
        return matches

    # TODO: this function has nothing to do with fingerprinting. is it needed?
    def print_stats(self):

        iterable = self.db.get_iterable_kv_pairs()

        counter = {}
        for t in iterable:
            sid, toff = t
            if not sid in counter:
                counter[sid] = 1
            else:
                counter[sid] += 1

        for song_id, count in counter.iteritems():
            song_name = self.song_names[song_id]
            print "%s has %d spectrogram peaks" % (song_name, count)
    
    # this does... what? this seems to only be used for the above function
    def set_song_names(self, wpaths):
        self.song_names = wpaths
    
    # TODO: put this in another module
    def align_matches(self, matches, starttime, record_seconds=0, verbose=False):
        """
            Finds hash matches that align in time with other matches and finds
            consensus about which hashes are "true" signal from the audio.
            
            Returns a dictionary with match information.
        """
        # align by diffs
        diff_counter = {}
        largest = 0
        largest_count = 0
        song_id = -1
        for tup in matches:
            sid, diff = tup
            if not diff in diff_counter:
                diff_counter[diff] = {}
            if not sid in diff_counter[diff]:
                diff_counter[diff][sid] = 0
            diff_counter[diff][sid] += 1

            if diff_counter[diff][sid] > largest_count:
                largest = diff
                largest_count = diff_counter[diff][sid]
                song_id = sid

        if verbose: 
            print "Diff is %d with %d offset-aligned matches" % (largest, largest_count)
        
        # extract idenfication      
        song = self.db.get_song_by_id(song_id)
        if song:
            songname = song.get(SQLDatabase.FIELD_SONGNAME, None)
        else:
            return None
        songname = songname.replace("_", " ")
        elapsed = time.time() - starttime
        
        if verbose: 
            print "Song is %s (song ID = %d) identification took %f seconds" % (songname, song_id, elapsed)
        
        # return match info
        song = {
            "song_id" : song_id,
            "song_name" : songname,
            "match_time" : elapsed,
            "confidence" : largest_count
        }
        
        if record_seconds: 
            song['record_time'] = record_seconds
            
        return song
