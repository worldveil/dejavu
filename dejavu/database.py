import MySQLdb as mysql
import MySQLdb.cursors as cursors
import os

class SQLDatabase():
    """
    Queries:

    1) Find duplicates (shouldn't be any, though):

        select `hash`, `song_id`, `offset`, count(*) cnt 
        from fingerprints 
        group by `hash`, `song_id`, `offset` 
        having cnt > 1
        order by cnt asc;

    2) Get number of hashes by song:

        select song_id, song_name, count(song_id) as num 
        from fingerprints 
        natural join songs
        group by song_id 
        order by count(song_id) desc;

    3) get hashes with highest number of collisions

        select 
            hash, 
            count(distinct song_id) as n 
        from fingerprints 
        group by `hash` 
        order by n DESC;

    => 26 different songs with same fingerprint (392 times):
    
        select songs.song_name, fingerprints.offset 
        from fingerprints natural join songs 
        where fingerprints.hash = "08d3c833b71c60a7b620322ac0c0aba7bf5a3e73";
    """

    # config keys
    CONNECTION = "connection"
    KEY_USERNAME = "username"
    KEY_DATABASE = "database"
    KEY_PASSWORD = "password"
    KEY_HOSTNAME = "hostname"

    # tables
    FINGERPRINTS_TABLENAME = "fingerprints"
    SONGS_TABLENAME = "songs"

    # fields
    FIELD_HASH = "hash"
    FIELD_SONG_ID = "song_id"
    FIELD_OFFSET = "offset"
    FIELD_SONGNAME = "song_name"
    FIELD_FINGERPRINTED = "fingerprinted"

    # creates
    CREATE_FINGERPRINTS_TABLE = """ 
    CREATE TABLE IF NOT EXISTS `%s` ( 
         `%s` binary(10) not null,
         `%s` mediumint unsigned not null, 
         `%s` int unsigned not null, 
         INDEX(%s),
         UNIQUE(%s, %s, %s)
    );""" % (FINGERPRINTS_TABLENAME, FIELD_HASH, 
            FIELD_SONG_ID, FIELD_OFFSET, FIELD_HASH,
            FIELD_SONG_ID, FIELD_OFFSET, FIELD_HASH)
    
    CREATE_SONGS_TABLE = """
    CREATE TABLE IF NOT EXISTS `%s` (
        `%s` mediumint unsigned not null auto_increment, 
        `%s` varchar(250) not null,
        `%s` tinyint default 0,
        PRIMARY KEY (`%s`),
        UNIQUE KEY `%s` (`%s`)
    );""" % (SONGS_TABLENAME, FIELD_SONG_ID, FIELD_SONGNAME, FIELD_FINGERPRINTED,
            FIELD_SONG_ID, FIELD_SONG_ID, FIELD_SONG_ID)

    # inserts
    INSERT_FINGERPRINT = "INSERT IGNORE INTO %s (%s, %s, %s) VALUES (UNHEX(%%s), %%s, %%s)" % (
        FINGERPRINTS_TABLENAME, FIELD_HASH, FIELD_SONG_ID, FIELD_OFFSET) # ignore duplicates and don't insert them
    INSERT_SONG = "INSERT INTO %s (%s) VALUES (%%s);" % (
        SONGS_TABLENAME, FIELD_SONGNAME)

    # selects
    SELECT = "SELECT %s, %s FROM %s WHERE %s = UNHEX(%%s);" % (FIELD_SONG_ID, FIELD_OFFSET, FINGERPRINTS_TABLENAME, FIELD_HASH)
    SELECT_ALL = "SELECT %s, %s FROM %s;" % (FIELD_SONG_ID, FIELD_OFFSET, FINGERPRINTS_TABLENAME)
    SELECT_SONG = "SELECT %s FROM %s WHERE %s = %%s" % (FIELD_SONGNAME, SONGS_TABLENAME, FIELD_SONG_ID)
    SELECT_NUM_FINGERPRINTS = "SELECT COUNT(*) as n FROM %s" % (FINGERPRINTS_TABLENAME)
    
    SELECT_UNIQUE_SONG_IDS = "SELECT COUNT(DISTINCT %s) as n FROM %s WHERE %s = 1;" % (FIELD_SONG_ID, SONGS_TABLENAME, FIELD_FINGERPRINTED)
    SELECT_SONGS = "SELECT %s, %s FROM %s WHERE %s = 1;" % (FIELD_SONG_ID, FIELD_SONGNAME, SONGS_TABLENAME, FIELD_FINGERPRINTED)

    # drops
    DROP_FINGERPRINTS = "DROP TABLE IF EXISTS %s;" % FINGERPRINTS_TABLENAME
    DROP_SONGS = "DROP TABLE IF EXISTS %s;" % SONGS_TABLENAME

    # update
    UPDATE_SONG_FINGERPRINTED = "UPDATE %s SET %s = 1 WHERE %s = %%s" % (SONGS_TABLENAME, FIELD_FINGERPRINTED, FIELD_SONG_ID)

    # delete
    DELETE_UNFINGERPRINTED = "DELETE FROM %s WHERE %s = 0;" % (SONGS_TABLENAME, FIELD_FINGERPRINTED)
    DELETE_ORPHANS = """
    delete from fingerprints 
    where not exists (
        select * from songs where fingerprints.song_id  = songs.song_id
    )"""
    
    def __init__(self, hostname, username, password, database):
        # connect
        self.database = database
        try:
            # http://www.halfcooked.com/mt/archives/000969.html
            self.connection = mysql.connect(
                hostname, username, password, 
                database, cursorclass=cursors.DictCursor)  

            self.connection.autocommit(False) # for fast bulk inserts
            self.cursor = self.connection.cursor()

        except mysql.Error, e:
            print "Connection error %d: %s" % (e.args[0], e.args[1])

    def setup(self):
        try:
            # create fingerprints table
            self.cursor.execute("USE %s;" % self.database)
            self.cursor.execute(SQLDatabase.CREATE_FINGERPRINTS_TABLE)
            self.cursor.execute(SQLDatabase.CREATE_SONGS_TABLE)
            self.delete_unfingerprinted_songs()
            self.connection.commit()
        except mysql.Error, e:
            print "Connection error %d: %s" % (e.args[0], e.args[1])
            self.connection.rollback()

    def empty(self):
        """
            Drops all tables and re-adds them. Be carfeul with this!
        """
        try:
            self.cursor.execute("USE %s;" % self.database)

            # drop tables
            self.cursor.execute(SQLDatabase.DROP_FINGERPRINTS)
            self.cursor.execute(SQLDatabase.DROP_SONGS)

            # recreate
            self.cursor.execute(SQLDatabase.CREATE_FINGERPRINTS_TABLE)
            self.cursor.execute(SQLDatabase.CREATE_SONGS_TABLE)
            self.connection.commit()

        except mysql.Error, e:
            print "Error in empty(), %d: %s" % (e.args[0], e.args[1])
            self.connection.rollback()
            
    def delete_orphans(self):
        try:
            self.cursor = self.connection.cursor()
            ### TODO: SQLDatabase.DELETE_ORPHANS is not performant enough, need better query
            ###     to delete fingerprints for which no song is tied to.
            #self.cursor.execute(SQLDatabase.DELETE_ORPHANS)
            #self.connection.commit()
        except mysql.Error, e:
            print "Error in delete_orphans(), %d: %s" % (e.args[0], e.args[1])
            self.connection.rollback()
    
    def delete_unfingerprinted_songs(self):
        try:
            self.cursor = self.connection.cursor()
            self.cursor.execute(SQLDatabase.DELETE_UNFINGERPRINTED)
            self.connection.commit()
        except mysql.Error, e:
            print "Error in delete_unfingerprinted_songs(), %d: %s" % (e.args[0], e.args[1])
            self.connection.rollback()

    def get_num_songs(self):
        """
            Returns number of songs the database has fingerprinted.
        """
        try:
            self.cursor = self.connection.cursor()
            self.cursor.execute(SQLDatabase.SELECT_UNIQUE_SONG_IDS)
            record = self.cursor.fetchone()
            return int(record['n'])
        except mysql.Error, e:
            print "Error in get_num_songs(), %d: %s" % (e.args[0], e.args[1])
            
    def get_num_fingerprints(self):
        """
            Returns number of fingerprints the database has fingerprinted.
        """
        try:
            self.cursor = self.connection.cursor()
            self.cursor.execute(SQLDatabase.SELECT_NUM_FINGERPRINTS)
            record = self.cursor.fetchone()
            return int(record['n'])
        except mysql.Error, e:
            print "Error in get_num_songs(), %d: %s" % (e.args[0], e.args[1])
    

    def set_song_fingerprinted(self, song_id):
        """
            Set the fingerprinted flag to TRUE (1) once a song has been completely
            fingerprinted in the database. 
        """
        try:
            self.cursor = self.connection.cursor()
            self.cursor.execute(SQLDatabase.UPDATE_SONG_FINGERPRINTED, song_id)
            self.connection.commit()
        except mysql.Error, e:
            print "Error in  set_song_fingerprinted(), %d: %s" % (e.args[0], e.args[1])
            self.connection.rollback()

    def get_songs(self):
        """
            Return songs that have the fingerprinted flag set TRUE (1). 
        """
        try:
            self.cursor.execute(SQLDatabase.SELECT_SONGS)
            return self.cursor.fetchall()
        except mysql.Error, e:
            print "Error in get_songs(), %d: %s" % (e.args[0], e.args[1])
            return None
            
    def get_song_by_id(self, sid):
        """
            Returns song by its ID.
        """
        try:
            self.cursor.execute(SQLDatabase.SELECT_SONG, (sid,))
            return self.cursor.fetchone()
        except mysql.Error, e:
            print "Error in get_songs(), %d: %s" % (e.args[0], e.args[1])
            return None 
    

    def insert(self, key, value):
        """
            Insert a (sha1, song_id, offset) row into database. 

            key is a sha1 hash, value = (song_id, offset)
        """
        try:
            args = (key, value[0], value[1])
            self.cursor.execute(SQLDatabase.INSERT_FINGERPRINT, args)
        except mysql.Error, e:
            print "Error in insert(), %d: %s" % (e.args[0], e.args[1])
            self.connection.rollback()

    def insert_song(self, songname):
        """
            Inserts song in the database and returns the ID of the inserted record.
        """
        try:
            self.cursor.execute(SQLDatabase.INSERT_SONG, (songname,))
            self.connection.commit()
            return int(self.cursor.lastrowid)
        except mysql.Error, e:
            print "Error in insert_song(), %d: %s" % (e.args[0], e.args[1])
            self.connection.rollback()
            return None

    def query(self, key):
        """
            Return all tuples associated with hash. 

            If hash is None, returns all entries in the 
            database (be careful with that one!).
        """
        # select all if no key
        if key is not None:
            sql = SQLDatabase.SELECT
        else:
            sql = SQLDatabase.SELECT_ALL

        matches = []
        try:
            self.cursor.execute(sql, (key,))

            # collect all matches
            records = self.cursor.fetchall()
            for record in records:
                matches.append((record[SQLDatabase.FIELD_SONG_ID], record[SQLDatabase.FIELD_OFFSET]))

        except mysql.Error, e:
            print "Error in query(), %d: %s" % (e.args[0], e.args[1])

        return matches

    def get_iterable_kv_pairs(self):
        """
            Returns all tuples in database. 
        """
        return self.query(None)

    def insert_hashes(self, hashes):
        """
            Insert series of hash => song_id, offset
            values into the database. 
        """
        for h in hashes:
            sha1, val = h
            self.insert(sha1, val)
        self.connection.commit()

    def return_matches(self, hashes):
        """
            Return the (song_id, offset_diff) tuples associated with 
            a list of 

                sha1 => (None, sample_offset)

            values.
        """
        matches = []
        for h in hashes:
            sha1, val = h
            list_of_tups = self.query(sha1)
            if list_of_tups:
                for t in list_of_tups:
                    # (song_id, db_offset, song_sampled_offset)
                    matches.append((t[0], t[1] - val[1]))
        return matches
