import sys
sys.path.append(".")

from dejavu import Dejavu

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

# Fingerprint a file
djv.fingerprint_file("test.mp3")
