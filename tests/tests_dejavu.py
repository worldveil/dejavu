import unittest
import os

from dejavu import Dejavu
from dejavu.recognize import FileRecognizer

config = {
    "database_backend" : "orm",
    "database_uri": "sqlite:///"
}


class DejavuTestCases(unittest.TestCase):

    def setUp(self):
        self.djv = Dejavu(config)

    def tearDown(self):
        del self.djv
        self.djv = None

    def test_fingerprint_1_file(self):
        self.djv.fingerprint_file("tests/test1.mp3")
        # should be the only fingerprinted file
        self.assertEqual(1, self.djv.db.get_num_songs())

        self.assertEqual(6457, self.djv.db.get_num_fingerprints())

    def test_fingerprint_directory(self):
        list_dir = [f for f in os.listdir("tests") if f[-4:] == ".mp3"]
        self.djv.fingerprint_directory("tests", [".mp3"])
        self.assertEqual(len(list_dir), self.djv.db.get_num_songs())

    def test_fingerprint_1_file_10secs(self):
        del self.djv
        config = {
            "database_backend" : "orm",
            "database_uri": "sqlite:///",
            "fingerprint_limit" : 10,
        }
        self.djv = Dejavu(config)
        self.djv.fingerprint_file("tests/test1.mp3")
        # should be the only fingerprinted file
        self.assertEqual(1, self.djv.db.get_num_songs())
        # fingerprinting the first 10 secs of this test file,
        # shouldn't get more than 3000 hashes.
        self.assertEqual(3053, self.djv.db.get_num_fingerprints())

    def test_recognize_1_file(self):
        self.djv.fingerprint_file("tests/test1.mp3")
        self.djv.fingerprint_file("tests/test2.mp3")
        song = self.djv.recognize(FileRecognizer, "tests/test2.mp3")
        self.assertEqual(song["song_name"], "tests/test2.mp3")

