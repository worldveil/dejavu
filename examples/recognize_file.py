from dejavu import Dejavu
from dejavu.recognize import FileRecognizer

# database uris examples:
# mysql: 'mysql+mysqldb://scott:tiger@localhost/foo'
# postgresql: 'postgresql://scott:tiger@localhost/mydatabase'
# sqlite: 'sqlite:///foo.db'
# in memory sqlite:  'sqlite://'

config = {
    "database_backend" : "orm",
    "database_uri": "sqlite:///fingerprints.sqlite",
    "fingerprint_limit" : 10,
}

# previous backend can still be used:
# config = {
#     "database_backend" : "plain",
#     "database": {
#         "host": "127.0.0.1",
#         "user": "",
#         "passwd": "",
#         "db": "",
#     },
#     "fingerprint_limit": 10,
# }


# create a Dejavu instance
djv = Dejavu(config)

# Recognize audio from a file
song = djv.recognize(FileRecognizer, "test2.mp3")
print song
