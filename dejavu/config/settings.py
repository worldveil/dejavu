# Dejavu

# DEJAVU JSON RESPONSE
SONG_ID = "song_id"
SONG_NAME = 'song_name'
RESULTS = 'results'

HASHES_MATCHED = 'hashes_matched_in_input'

# Hashes fingerprinted in the db.
FINGERPRINTED_HASHES = 'fingerprinted_hashes_in_db'
# Percentage regarding hashes matched vs hashes fingerprinted in the db.
FINGERPRINTED_CONFIDENCE = 'fingerprinted_confidence'

# Hashes generated from the input.
INPUT_HASHES = 'input_total_hashes'
# Percentage regarding hashes matched vs hashes from the input.
INPUT_CONFIDENCE = 'input_confidence'

TOTAL_TIME = 'total_time'
FINGERPRINT_TIME = 'fingerprint_time'
QUERY_TIME = 'query_time'
ALIGN_TIME = 'align_time'
OFFSET = 'offset'
OFFSET_SECS = 'offset_seconds'

# DATABASE CLASS INSTANCES:
DATABASES = {
    'mysql': ("dejavu.database_handler.mysql_database", "MySQLDatabase"),
    'postgres': ("dejavu.database_handler.postgres_database", "PostgreSQLDatabase"),
    'postgres_compact': ("dejavu.database_handler.postgres_compact_database", "PostgreSQLCompactDatabase")
}

# TABLE SONGS
SONGS_TABLENAME = "songs"

# SONGS FIELDS
FIELD_SONG_ID = 'song_id'
FIELD_SONGNAME = 'song_name'
FIELD_FINGERPRINTED = "fingerprinted"
FIELD_FILE_SHA1 = 'file_sha1'
FIELD_TOTAL_HASHES = 'total_hashes'

# TABLE FINGERPRINTS
FINGERPRINTS_TABLENAME = "fingerprints"

# FINGERPRINTS FIELDS
FIELD_HASH = 'hash'
FIELD_OFFSET = 'offset'

# FINGERPRINTS CONFIG:
# This is used as connectivity parameter for scipy.generate_binary_structure function. This parameter
# changes the morphology mask when looking for maximum peaks on the spectrogram matrix.
# Possible values are: [1, 2]
# Where 1 sets a diamond morphology which implies that diagonal elements are not considered as neighbors (this
# is the value used in the original dejavu code).
# And 2 sets a square mask, i.e. all elements are considered neighbors.
CONNECTIVITY_MASK = 2

# Sampling rate, related to the Nyquist conditions, which affects
# the range frequencies we can detect.
DEFAULT_FS = 44100

# Size of the FFT window, affects frequency granularity
DEFAULT_WINDOW_SIZE = 4096

# Ratio by which each sequential window overlaps the last and the
# next window. Higher overlap will allow a higher granularity of offset
# matching, but potentially more fingerprints.
DEFAULT_OVERLAP_RATIO = 0.5

# Degree to which a fingerprint can be paired with its neighbors. Higher values will
# cause more fingerprints, but potentially better accuracy.
DEFAULT_FAN_VALUE = 5  # 15 was the original value.

# Minimum amplitude in spectrogram in order to be considered a peak.
# This can be raised to reduce number of fingerprints, but can negatively
# affect accuracy.
DEFAULT_AMP_MIN = 10

# Number of cells around an amplitude peak in the spectrogram in order
# for Dejavu to consider it a spectral peak. Higher values mean less
# fingerprints and faster matching, but can potentially affect accuracy.
PEAK_NEIGHBORHOOD_SIZE = 10  # 20 was the original value.

# Thresholds on how close or far fingerprints can be in time in order
# to be paired as a fingerprint. If your max is too low, higher values of
# DEFAULT_FAN_VALUE may not perform as expected.
MIN_HASH_TIME_DELTA = 0
MAX_HASH_TIME_DELTA = 200

# If True, will sort peaks temporally for fingerprinting;
# not sorting will cut down number of fingerprints, but potentially
# affect performance.
PEAK_SORT = True

# Number of bits to grab from the front of the SHA1 hash in the
# fingerprint calculation. The more you grab, the more memory storage,
# with potentially lesser collisions of matches.
FINGERPRINT_REDUCTION = 20

# Number of results being returned for file recognition
TOPN = 2

# COMPACT FINGERPRINT STORE CONFIG (database_type "postgres_compact", see dejavu/fpstore):
# Block and part sizes are fixed when the store's tables are created; the search settings can change anytime.

# A song's fingerprints are stored in time blocks of this many seconds, and recognition reads only the
# blocks the query aligns with. 5 second blocks stay within one 8 KB database page.
FPSTORE_BLOCK_SECONDS = 5

# Longest posting list held in one row; longer lists are split into parts. 1,000 postings keep a row
# around 3 KB, and with FPSTORE_STOP_DF at the same value every hash the search fetches is a single row.
FPSTORE_PART_POSTINGS = 1000

# Hashes with more postings than this are too common to be worth fetching. They are still used to
# verify the candidate songs.
FPSTORE_STOP_DF = 1000

# Postings fetched, rarest hashes first, before each check whether one song clearly leads; None means
# every remaining usable hash.
FPSTORE_STAGES = (100_000, 500_000, 2_000_000, None)

# A song clearly leads with at least FPSTORE_MIN_VOTES time-aligned votes and FPSTORE_MARGIN times
# the votes of the runner-up.
FPSTORE_MIN_VOTES = 10
FPSTORE_MARGIN = 2.0

# Best offset differences of each candidate song verified against all of its fingerprints in the
# query's time range; more than one helps songs whose sections repeat.
FPSTORE_OFFSETS_PER_SONG = 3
