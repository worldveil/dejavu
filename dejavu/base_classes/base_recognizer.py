import abc
from time import time
from typing import Dict, List, Tuple

import numpy as np

from dejavu.config.settings import DEFAULT_FS
from dejavu.logic.fingerprint import fingerprint_hash32


class BaseRecognizer(object, metaclass=abc.ABCMeta):
    def __init__(self, dejavu):
        self.dejavu = dejavu
        self.Fs = DEFAULT_FS

    def _recognize(self, *data) -> Tuple[List[Dict[str, any]], int, int, int]:
        if self.dejavu.db.compact:
            return self._recognize_compact(*data)

        fingerprint_times = []
        hashes = set()  # to remove possible duplicated fingerprints we built a set.
        for channel in data:
            fingerprints, fingerprint_time = self.dejavu.generate_fingerprints(channel, Fs=self.Fs)
            fingerprint_times.append(fingerprint_time)
            hashes |= set(fingerprints)

        matches, dedup_hashes, query_time = self.dejavu.find_matches(hashes)

        t = time()
        final_results = self.dejavu.align_matches(matches, dedup_hashes, len(hashes))
        align_time = time() - t

        return final_results, np.sum(fingerprint_times), query_time, align_time

    def _recognize_compact(self, *data) -> Tuple[List[Dict[str, any]], int, int, int]:
        # The compact store finds and aligns matches in one search; its fetch and verification times
        # are reported as the query and align times.
        fingerprint_times = []
        hashes, offsets = [np.empty(0, np.uint32)], [np.empty(0, np.int64)]
        for channel in data:
            t = time()
            channel_hashes, channel_offsets = fingerprint_hash32(channel, Fs=self.Fs)
            fingerprint_times.append(time() - t)
            hashes.append(channel_hashes)
            offsets.append(channel_offsets)

        # duplicated fingerprints across channels are removed by the search
        final_results, stats = self.dejavu.db.search(np.concatenate(hashes), np.concatenate(offsets))

        return (final_results, np.sum(fingerprint_times),
                stats.get("fetch_ms", 0) / 1000, stats.get("verify_ms", 0) / 1000)

    @abc.abstractmethod
    def recognize(self) -> Dict[str, any]:
        pass  # base class does nothing
