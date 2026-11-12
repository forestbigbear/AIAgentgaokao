from contextlib import contextmanager
from threading import Lock
from typing import Iterator

import pymysql
from dbutils.pooled_db import PooledDB

from app.core.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: PooledDB | None = None
        self._lock = Lock()

    def _get_pool(self) -> PooledDB:
        if self._pool is None:
            with self._lock:
                if self._pool is None:
                    self._pool = PooledDB(
                        creator=pymysql,
                        mincached=0,
                        maxcached=self._settings.db_pool_size,
                        maxconnections=self._settings.db_pool_size,
                        blocking=True,
                        ping=1,
                        host=self._settings.db_host,
                        port=self._settings.db_port,
                        user=self._settings.db_user,
                        password=self._settings.db_password,
                        database=self._settings.db_name,
                        charset="utf8mb4",
                        cursorclass=pymysql.cursors.DictCursor,
                        autocommit=False,
                        connect_timeout=5,
                    )
        return self._pool

    @contextmanager
    def connection(self) -> Iterator:
        connection = self._get_pool().connection()
        try:
            yield connection
        finally:
            connection.close()  # DBUtils returns it to the pool.

    @contextmanager
    def transaction(self) -> Iterator:
        with self.connection() as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def check_connection(self) -> dict:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT %s AS probe, DATABASE() AS database_name", ("ok",))
                return cursor.fetchone()

