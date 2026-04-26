"""
database.py — Database connection pooling and query execution.

Manages a pool of connections to a PostgreSQL-compatible database,
with health checking, connection reuse, and query result caching.
"""

import logging
import queue
import threading
import time
from contextlib import contextmanager
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)


# ── Connection Pool ───────────────────────────────────────────────────────────

class Connection:
    """Represents a single database connection (stub)."""

    def __init__(self, dsn: str, conn_id: int):
        self.dsn     = dsn
        self.conn_id = conn_id
        self._open   = True
        self.created_at = time.monotonic()
        logger.debug("Opened connection #%d to %s", conn_id, dsn)

    def execute(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute a SQL query and return rows as list of dicts."""
        if not self._open:
            raise RuntimeError("Connection is closed")
        # Simulate query execution
        logger.debug("Executing: %s %s", sql, params)
        return []

    def close(self) -> None:
        self._open = False
        logger.debug("Closed connection #%d", self.conn_id)

    @property
    def is_healthy(self) -> bool:
        """Ping the database to check if the connection is still alive."""
        try:
            self.execute("SELECT 1")
            return self._open
        except Exception:
            return False


class ConnectionPool:
    """
    Thread-safe database connection pool.

    Maintains a pool of reusable connections.
    Connections are checked out for the duration of a query
    and returned to the pool automatically via context manager.

    Usage:
        pool = ConnectionPool("postgresql://localhost/mydb", min_size=2, max_size=10)

        with pool.acquire() as conn:
            rows = conn.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    """

    def __init__(
        self,
        dsn: str,
        min_size: int = 2,
        max_size: int = 10,
        max_conn_age_sec: float = 300.0,
        health_check_interval: float = 30.0,
    ):
        self.dsn                  = dsn
        self.min_size             = min_size
        self.max_size             = max_size
        self.max_conn_age_sec     = max_conn_age_sec

        self._pool   : queue.Queue[Connection] = queue.Queue(maxsize=max_size)
        self._lock   = threading.Lock()
        self._count  = 0
        self._closed = False

        # Pre-warm with minimum connections
        for _ in range(min_size):
            self._pool.put(self._new_connection())

        # Background health checker
        self._checker = threading.Thread(
            target=self._health_check_loop,
            args=(health_check_interval,),
            daemon=True,
        )
        self._checker.start()

    def _new_connection(self) -> Connection:
        with self._lock:
            self._count += 1
            return Connection(self.dsn, self._count)

    @contextmanager
    def acquire(self, timeout: float = 5.0) -> Generator[Connection, None, None]:
        """
        Check out a connection from the pool.
        Returns the connection to the pool when the block exits.
        Raises queue.Empty if no connection is available within *timeout* seconds.
        """
        if self._closed:
            raise RuntimeError("Connection pool is closed")

        try:
            conn = self._pool.get(timeout=timeout)
        except queue.Empty:
            # Pool exhausted — create a new connection if under max
            with self._lock:
                if self._count < self.max_size:
                    conn = self._new_connection()
                else:
                    raise RuntimeError("Connection pool exhausted")

        # Replace stale or unhealthy connections
        age = time.monotonic() - conn.created_at
        if age > self.max_conn_age_sec or not conn.is_healthy:
            conn.close()
            conn = self._new_connection()

        try:
            yield conn
        finally:
            if not self._closed:
                self._pool.put(conn)

    def _health_check_loop(self, interval: float) -> None:
        """Background thread: periodically verify all pooled connections."""
        while not self._closed:
            time.sleep(interval)
            replenished = []
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    if conn.is_healthy:
                        replenished.append(conn)
                    else:
                        conn.close()
                        replenished.append(self._new_connection())
                except queue.Empty:
                    break
            for conn in replenished:
                self._pool.put(conn)

    def close_all(self) -> None:
        """Drain and close all connections in the pool."""
        self._closed = True
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except queue.Empty:
                break
        logger.info("Connection pool closed. %d connections were open.", self._count)


# ── Query helpers ─────────────────────────────────────────────────────────────

_pool: Optional[ConnectionPool] = None


def init_pool(dsn: str, **kwargs) -> None:
    """Initialise the global connection pool. Call once at app startup."""
    global _pool
    _pool = ConnectionPool(dsn, **kwargs)


def get_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call init_pool() first.")
    return _pool


def fetch_one(sql: str, params: tuple = ()) -> Optional[dict]:
    """Execute a query and return the first row, or None."""
    with get_pool().acquire() as conn:
        rows = conn.execute(sql, params)
        return rows[0] if rows else None


def fetch_all(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a query and return all rows."""
    with get_pool().acquire() as conn:
        return conn.execute(sql, params)


def execute_write(sql: str, params: tuple = ()) -> None:
    """Execute an INSERT / UPDATE / DELETE statement."""
    with get_pool().acquire() as conn:
        conn.execute(sql, params)
