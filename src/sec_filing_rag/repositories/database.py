from __future__ import annotations

from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class Database:
    def __init__(
        self,
        database_url: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
        timeout: float = 10,
        open: bool = True,
    ) -> None:
        self.database_url = database_url
        self.pool = ConnectionPool(
            conninfo=database_url,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            kwargs={"row_factory": dict_row},
            open=open,
        )

    def open(self, *, timeout: float = 10) -> None:
        self.pool.open(wait=True, timeout=timeout)

    def close(self) -> None:
        self.pool.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        with self.pool.connection() as connection:
            yield connection
