from __future__ import unicode_literals
from __future__ import absolute_import
import Queue

import pymysql
import pymysql.cursors


def cursor_factory(**factory_options):
    def cursor(**options):
        options.update(factory_options)
        return Cursor(**options)
    return cursor


class Cursor(object):
    """
    Establishes a connection to the database and returns an open cursor.


    ```python
    # Use as context manager
    with Cursor() as cur:
        cur.execute(query)
    ```
    """
    _cache = Queue.Queue(maxsize=5)

    def __init__(self, cursor_type=pymysql.cursors.DictCursor, **options):
        super(Cursor, self).__init__()

        try:
            conn = self._cache.get_nowait()
        except Queue.Empty:
            conn = pymysql.connect(**options)

        self.conn = conn
        self.cursor_type = cursor_type

    def __enter__(self):
        self.cursor = self.conn.cursor(self.cursor_type)
        return self.cursor

    def __exit__(self, type, value, traceback):
        self.cursor.close()
        self.conn.commit()

        # Put it back on the queue
        try:
            self._cache.put_nowait(self.conn)
        except Queue.Full:
            self.conn.close()
