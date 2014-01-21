import os
import unittest

from dejavu import Dejavu
from dejavu.recognize import FileRecognizer

config_orm = {
    "database_backend" : "orm",
     "database_uri": "sqlite:///"
}

config_plain = {
    "database_backend" : "plain",
    "database": {
        "host": "127.0.0.1",
        "user": "dejavu",
        "passwd": "dejavu_tests",
        "db": "dejavu",
    }
}


class DejavuORMTestCases(unittest.TestCase):

    def setUp(self):
        self.djv = Dejavu(config_orm)

    def tearDown(self):
        self.djv.db.empty()

    def test_fingerprint_1_file(self):
        self.djv.fingerprint_file("tests/test1.mp3")
        # should be the only fingerprinted file
        self.assertEqual(1, self.djv.db.get_num_songs())

        self.assertEqual(5279, self.djv.db.get_num_fingerprints())

    def test_fingerprint_directory(self):
        list_dir = [f for f in os.listdir("tests") if f[-4:] == ".mp3"]
        self.djv.fingerprint_directory("tests", [".mp3"])
        self.assertEqual(len(list_dir), self.djv.db.get_num_songs())
#
    def test_fingerprint_1_file_10secs(self):
        self.djv.limit = 10
        self.djv.fingerprint_file("tests/test1.mp3")
        # should be the only fingerprinted file
        self.assertEqual(1, self.djv.db.get_num_songs())
        # fingerprinting the first 10 secs of this test file,
        # shouldn't get more than 3000 hashes.
        self.assertEqual(2554, self.djv.db.get_num_fingerprints())

    def test_recognize_1_file(self):
        self.djv.fingerprint_file("tests/test1.mp3")
        self.djv.fingerprint_file("tests/test2.mp3")
        song = self.djv.recognize(FileRecognizer, "tests/test2.mp3")
        self.assertEqual(song["song_name"], "tests/test2.mp3")


class DejavuPlainDBTestCases(unittest.TestCase):

    def setUp(self):
        self.djv = Dejavu(config_plain)

    def tearDown(self):
        del self.djv
        self.djv = None

    def test_fingerprint_1_file(self):
        self.djv.fingerprint_file("tests/test1.mp3")
        # should be the only fingerprinted file
        self.assertEqual(1, self.djv.db.get_num_songs())

        self.assertEqual(5279, self.djv.db.get_num_fingerprints())

    def test_fingerprint_directory(self):
        list_dir = [f for f in os.listdir("tests") if f[-4:] == ".mp3"]
        self.djv.fingerprint_directory("tests", [".mp3"])
        self.assertEqual(len(list_dir), self.djv.db.get_num_songs())

    def test_fingerprint_1_file_10secs(self):
        self.djv.limit = 10
        self.djv.fingerprint_file("tests/test1.mp3")
        # should be the only fingerprinted file
        self.assertEqual(1, self.djv.db.get_num_songs())
        # fingerprinting the first 10 secs of this test file,
        # shouldn't get more than 3000 hashes.
        self.assertEqual(2554, self.djv.db.get_num_fingerprints())

    def test_recognize_1_file(self):
        self.djv.fingerprint_file("tests/test1.mp3")
        self.djv.fingerprint_file("tests/test2.mp3")
        song = self.djv.recognize(FileRecognizer, "tests/test2.mp3")
        self.assertEqual(song["song_name"], "tests/test2.mp3")

