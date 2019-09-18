from dejavu.config.config import (FIELD_FILE_SHA1, FIELD_FINGERPRINTED,
                                  FIELD_HASH, FIELD_OFFSET, FIELD_SONG_ID,
                                  FIELD_SONGNAME, FINGERPRINTS_TABLENAME,
                                  SONGS_TABLENAME)

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

# creates
CREATE_SONGS_TABLE = f"""
    CREATE TABLE IF NOT EXISTS `{SONGS_TABLENAME}` (
        `{FIELD_SONG_ID}` mediumint unsigned not null auto_increment,
        `{FIELD_SONGNAME}` varchar(250) not null,
        `{FIELD_FINGERPRINTED}` tinyint default 0,
        `{FIELD_FILE_SHA1}` binary(20) not null,
    PRIMARY KEY (`{FIELD_SONG_ID}`),
    UNIQUE KEY `{FIELD_SONG_ID}` (`{FIELD_SONG_ID}`)
) ENGINE=INNODB;"""

CREATE_FINGERPRINTS_TABLE = f"""
    CREATE TABLE IF NOT EXISTS `{FINGERPRINTS_TABLENAME}` (
         `{FIELD_HASH}` binary(10) not null,
         `{FIELD_SONG_ID}` mediumint unsigned not null,
         `{FIELD_OFFSET}` int unsigned not null,
     INDEX ({FIELD_HASH}),
     UNIQUE KEY `unique_constraint` ({FIELD_SONG_ID}, {FIELD_OFFSET}, {FIELD_HASH}),
     FOREIGN KEY ({FIELD_SONG_ID}) REFERENCES {SONGS_TABLENAME}({FIELD_SONG_ID}) ON DELETE CASCADE
) ENGINE=INNODB;"""

# inserts (ignores duplicates)
INSERT_FINGERPRINT = f"""
    INSERT IGNORE INTO `{FINGERPRINTS_TABLENAME}` (
            `{FIELD_SONG_ID}`
        ,   `{FIELD_HASH}`
        , `{FIELD_OFFSET}`) 
    VALUES (%s, UNHEX(%s), %s);
"""

INSERT_SONG = f"""
    INSERT INTO `{SONGS_TABLENAME}` (`{FIELD_SONGNAME}`,`{FIELD_FILE_SHA1}`) 
    VALUES (%s, UNHEX(%s));
"""

# selects
SELECT = f"""
    SELECT `{FIELD_SONG_ID}`, `{FIELD_OFFSET}` 
    FROM `{FINGERPRINTS_TABLENAME}` 
    WHERE `{FIELD_HASH}` = UNHEX(%s);
"""

SELECT_MULTIPLE = f"""
    SELECT HEX(`{FIELD_HASH}`), `{FIELD_SONG_ID}`, `{FIELD_OFFSET}` 
    FROM `{FINGERPRINTS_TABLENAME}` 
    WHERE `{FIELD_HASH}` IN (%s);
"""

SELECT_ALL = f"SELECT `{FIELD_SONG_ID}`, `{FIELD_OFFSET}` FROM `{FINGERPRINTS_TABLENAME}`;"

SELECT_SONG = f"""
    SELECT `{FIELD_SONGNAME}`, HEX(`{FIELD_FILE_SHA1}`) AS `{FIELD_FILE_SHA1}` 
    FROM `{SONGS_TABLENAME}` 
    WHERE `{FIELD_SONG_ID}` = %s;
"""

SELECT_NUM_FINGERPRINTS = f"SELECT COUNT(*) AS n FROM `{FINGERPRINTS_TABLENAME}`;"

SELECT_UNIQUE_SONG_IDS = f"""
    SELECT COUNT(`{FIELD_SONG_ID}`) AS n 
    FROM `{SONGS_TABLENAME}` 
    WHERE `{FIELD_FINGERPRINTED}` = 1;
"""

SELECT_SONGS = f"""
    SELECT 
        `{FIELD_SONG_ID}`
    ,   `{FIELD_SONGNAME}`
    ,   HEX(`{FIELD_FILE_SHA1}`) AS `{FIELD_FILE_SHA1}` 
    FROM `{SONGS_TABLENAME}` 
    WHERE `{FIELD_FINGERPRINTED}` = 1;
"""

# drops
DROP_FINGERPRINTS = f"DROP TABLE IF EXISTS `{FINGERPRINTS_TABLENAME}`;"
DROP_SONGS = f"DROP TABLE IF EXISTS `{SONGS_TABLENAME}`;"

# update
UPDATE_SONG_FINGERPRINTED = f"""
    UPDATE `{SONGS_TABLENAME}` SET `{FIELD_FINGERPRINTED}` = 1 WHERE `{FIELD_SONG_ID}` = %s;
"""

# delete
DELETE_UNFINGERPRINTED = f"""
    DELETE FROM `{SONGS_TABLENAME}` WHERE `{FIELD_FINGERPRINTED}` = 0;
"""
