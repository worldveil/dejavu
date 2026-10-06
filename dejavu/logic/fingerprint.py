import hashlib
from operator import itemgetter
from typing import List, Tuple

import matplotlib.mlab as mlab
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage.filters import maximum_filter
from scipy.ndimage.morphology import (binary_erosion,
                                      generate_binary_structure,
                                      iterate_structure)

from dejavu.config.settings import (CONNECTIVITY_MASK, DEFAULT_AMP_MIN,
                                    DEFAULT_FAN_VALUE, DEFAULT_FS,
                                    DEFAULT_OVERLAP_RATIO, DEFAULT_WINDOW_SIZE,
                                    FINGERPRINT_REDUCTION, MAX_HASH_TIME_DELTA,
                                    MIN_HASH_TIME_DELTA,
                                    PEAK_NEIGHBORHOOD_SIZE, PEAK_SORT)


def fingerprint(channel_samples: List[int],
                Fs: int = DEFAULT_FS,
                wsize: int = DEFAULT_WINDOW_SIZE,
                wratio: float = DEFAULT_OVERLAP_RATIO,
                fan_value: int = DEFAULT_FAN_VALUE,
                amp_min: int = DEFAULT_AMP_MIN) -> List[Tuple[str, int]]:
    """
    FFT the channel, log transform output, find local maxima, then return locally sensitive hashes.

    :param channel_samples: channel samples to fingerprint.
    :param Fs: audio sampling rate.
    :param wsize: FFT windows size.
    :param wratio: ratio by which each sequential window overlaps the last and the next window.
    :param fan_value: degree to which a fingerprint can be paired with its neighbors.
    :param amp_min: minimum amplitude in spectrogram in order to be considered a peak.
    :return: a list of hashes with their corresponding offsets.
    """
    # FFT the signal and extract frequency components
    arr2D = mlab.specgram(
        channel_samples,
        NFFT=wsize,
        Fs=Fs,
        window=mlab.window_hanning,
        noverlap=int(wsize * wratio))[0]

    # Apply log transform since specgram function returns linear array. 0s are excluded to avoid np warning.
    arr2D = 10 * np.log10(arr2D, out=np.zeros_like(arr2D), where=(arr2D != 0))

    local_maxima = get_2D_peaks(arr2D, plot=False, amp_min=amp_min)

    # return hashes
    return generate_hashes(local_maxima, fan_value=fan_value)


def fingerprint_hash32(channel_samples: List[int],
                       Fs: int = DEFAULT_FS,
                       wsize: int = DEFAULT_WINDOW_SIZE,
                       wratio: float = DEFAULT_OVERLAP_RATIO,
                       fan_value: int = DEFAULT_FAN_VALUE,
                       amp_min: int = DEFAULT_AMP_MIN) -> Tuple[np.ndarray, np.ndarray]:
    """
    Same as fingerprint, but with every peak pair packed losslessly into 32 bits instead of hashed with sha1:
    hash32 = (freq1 << 20) | (freq2 << 8) | t_delta. This is what the compact store (dejavu.fpstore) keeps.

    :param channel_samples: channel samples to fingerprint.
    :param Fs: audio sampling rate.
    :param wsize: FFT windows size.
    :param wratio: ratio by which each sequential window overlaps the last and the next window.
    :param fan_value: degree to which a fingerprint can be paired with its neighbors.
    :param amp_min: minimum amplitude in spectrogram in order to be considered a peak.
    :return: an array of uint32 hashes and an array of their corresponding offsets.
    """
    if wsize // 2 + 1 > 1 << 12 or not 0 <= MIN_HASH_TIME_DELTA <= MAX_HASH_TIME_DELTA < 1 << 8:
        raise ValueError("hash32 holds frequency bins in 12 bits and time deltas in 8 bits")

    arr2D = mlab.specgram(
        channel_samples,
        NFFT=wsize,
        Fs=Fs,
        window=mlab.window_hanning,
        noverlap=int(wsize * wratio))[0]

    arr2D = 10 * np.log10(arr2D, out=np.zeros_like(arr2D), where=(arr2D != 0))

    local_maxima = get_2D_peaks(arr2D, plot=False, amp_min=amp_min)

    return generate_hashes32(local_maxima, fan_value=fan_value)


def get_2D_peaks(arr2D: np.array, plot: bool = False, amp_min: int = DEFAULT_AMP_MIN)\
        -> List[Tuple[List[int], List[int]]]:
    """
    Extract maximum peaks from the spectogram matrix (arr2D).

    :param arr2D: matrix representing the spectogram.
    :param plot: for plotting the results.
    :param amp_min: minimum amplitude in spectrogram in order to be considered a peak.
    :return: a list composed by a list of frequencies and times.
    """
    # Original code from the repo is using a morphology mask that does not consider diagonal elements
    # as neighbors (basically a diamond figure) and then applies a dilation over it, so what I'm proposing
    # is to change from the current diamond figure to a just a normal square one:
    #       F   T   F           T   T   T
    #       T   T   T   ==>     T   T   T
    #       F   T   F           T   T   T
    # In my local tests time performance of the square mask was ~3 times faster
    # respect to the diamond one, without hurting accuracy of the predictions.
    # I've made now the mask shape configurable in order to allow both ways of find maximum peaks.
    # That being said, we generate the mask by using the following function
    # https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.generate_binary_structure.html
    struct = generate_binary_structure(2, CONNECTIVITY_MASK)

    #  And then we apply dilation using the following function
    #  http://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.iterate_structure.html
    #  Take into account that if PEAK_NEIGHBORHOOD_SIZE is 2 you can avoid the use of the scipy functions and just
    #  change it by the following code:
    #  neighborhood = np.ones((PEAK_NEIGHBORHOOD_SIZE * 2 + 1, PEAK_NEIGHBORHOOD_SIZE * 2 + 1), dtype=bool)
    neighborhood = iterate_structure(struct, PEAK_NEIGHBORHOOD_SIZE)

    # find local maxima using our filter mask
    local_max = maximum_filter(arr2D, footprint=neighborhood) == arr2D

    # Applying erosion, the dejavu documentation does not talk about this step.
    background = (arr2D == 0)
    eroded_background = binary_erosion(background, structure=neighborhood, border_value=1)

    # Boolean mask of arr2D with True at peaks (applying XOR on both matrices).
    detected_peaks = local_max != eroded_background

    # extract peaks
    amps = arr2D[detected_peaks]
    freqs, times = np.where(detected_peaks)

    # filter peaks
    amps = amps.flatten()

    # get indices for frequency and time
    filter_idxs = np.where(amps > amp_min)

    freqs_filter = freqs[filter_idxs]
    times_filter = times[filter_idxs]

    if plot:
        # scatter of the peaks
        fig, ax = plt.subplots()
        ax.imshow(arr2D)
        ax.scatter(times_filter, freqs_filter)
        ax.set_xlabel('Time')
        ax.set_ylabel('Frequency')
        ax.set_title("Spectrogram")
        plt.gca().invert_yaxis()
        plt.show()

    return list(zip(freqs_filter, times_filter))


def generate_hashes(peaks: List[Tuple[int, int]], fan_value: int = DEFAULT_FAN_VALUE) -> List[Tuple[str, int]]:
    """
    Hash list structure:
       sha1_hash[0:FINGERPRINT_REDUCTION]    time_offset
        [(e05b341a9b77a51fd26, 32), ... ]

    :param peaks: list of peak frequencies and times.
    :param fan_value: degree to which a fingerprint can be paired with its neighbors.
    :return: a list of hashes with their corresponding offsets.
    """
    # frequencies are in the first position of the tuples
    idx_freq = 0
    # times are in the second position of the tuples
    idx_time = 1

    if PEAK_SORT:
        peaks.sort(key=itemgetter(1))

    hashes = []
    for i in range(len(peaks)):
        for j in range(1, fan_value):
            if (i + j) < len(peaks):

                freq1 = peaks[i][idx_freq]
                freq2 = peaks[i + j][idx_freq]
                t1 = peaks[i][idx_time]
                t2 = peaks[i + j][idx_time]
                t_delta = t2 - t1

                if MIN_HASH_TIME_DELTA <= t_delta <= MAX_HASH_TIME_DELTA:
                    h = hashlib.sha1(f"{str(freq1)}|{str(freq2)}|{str(t_delta)}".encode('utf-8'))

                    hashes.append((h.hexdigest()[0:FINGERPRINT_REDUCTION], t1))

    return hashes


def generate_hashes32(peaks: List[Tuple[int, int]], fan_value: int = DEFAULT_FAN_VALUE) \
        -> Tuple[np.ndarray, np.ndarray]:
    """
    The peak pairs of generate_hashes, each packed as hash32 = (freq1 << 20) | (freq2 << 8) | t_delta.
    Computed with numpy, and in a different order, but the same (pair, time_offset) set.

    :param peaks: list of peak frequencies and times.
    :param fan_value: degree to which a fingerprint can be paired with its neighbors.
    :return: an array of uint32 hashes and an array of their corresponding offsets.
    """
    freqs = np.array([p[0] for p in peaks], np.int64)
    times = np.array([p[1] for p in peaks], np.int64)

    if PEAK_SORT:
        # peaks.sort(key=itemgetter(1)) is stable
        order = np.argsort(times, kind="stable")
        freqs, times = freqs[order], times[order]

    hashes, offsets = [], []
    for j in range(1, fan_value):
        if j >= len(freqs):
            break
        t_delta = times[j:] - times[:-j]
        keep = (MIN_HASH_TIME_DELTA <= t_delta) & (t_delta <= MAX_HASH_TIME_DELTA)
        hashes.append((freqs[:-j][keep] << 20) | (freqs[j:][keep] << 8) | t_delta[keep])
        offsets.append(times[:-j][keep])

    if not hashes:
        return np.empty(0, np.uint32), np.empty(0, np.int64)
    return np.concatenate(hashes).astype(np.uint32), np.concatenate(offsets)


def unique_pairs(hashes: np.ndarray, offsets: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    The distinct (hash32, offset) pairs, sorted: what set() does for the sha1 fingerprints, e.g. to take the
    union of several channels.

    :param hashes: hash32 values, as generate_hashes32 returns them.
    :param offsets: their corresponding offsets.
    :return: the distinct hashes and offsets, as a uint32 and an int64 array.
    """
    key = np.unique(hashes.astype(np.uint64) << np.uint64(32) | offsets.astype(np.uint64))
    return (key >> np.uint64(32)).astype(np.uint32), (key & np.uint64(0xFFFFFFFF)).astype(np.int64)
