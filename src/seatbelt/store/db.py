
"""SQLite access with explicit, serialised write transactions."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from seatbelt.errors import StoreError

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS mandates (
    mandate_id   TEXT PRIMARY KEY,
    agent_id     TEXT NOT NULL,
    currency     TEXT NOT NULL,
    token        TEXT NOT NULL,
    mandate_json TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    revoked_at   TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id         TEXT PRIMARY KEY,
    mandate_id         TEXT NOT NULL REFERENCES mandates(mandate_id),
    request_id         TEXT NOT NULL,
    agent_id           TEXT NOT NULL,
    payee              TEXT NOT NULL,
    amount             TEXT NOT NULL,
    currency           TEXT NOT NULL,
    description        TEXT NOT NULL,
    status             TEXT NOT NULL,
    verdict            TEXT NOT NULL,
    reasons            TEXT NOT NULL,
    payment_channel    TEXT NOT NULL DEFAULT 'executor',
    paypal_order_id    TEXT,
    paypal_approve_url TEXT,
    paypal_capture_id  TEXT,
    decided_by         TEXT,
    failure            TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    UNIQUE (mandate_id, request_id)
);

CREATE INDEX IF NOT EXISTS idx_payments_mandate_status
    ON payments (mandate_id, status);

CREATE TABLE IF NOT EXISTS audit_log (
    seq        INTEGER PRIMARY KEY,
    ts         TEXT NOT NULL,
    event      TEXT NOT NULL,
    actor      TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    data       TEXT NOT NULL,
    prev_hash  TEXT NOT NULL,
    hash       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paypal_webhook_events (
    event_id     TEXT PRIMARY KEY,
    event_type   TEXT NOT NULL,
    payment_id   TEXT NOT NULL REFERENCES payments(payment_id),
    capture_id   TEXT NOT NULL UNIQUE,
    processed_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 10_000) -> None:
        if str(path) == ":memory:":
            raise StoreError(
                "':memory:' is not supported (each connection would be a new DB); use a file"
            )
        self._path = str(path)
        self._busy_timeout_ms = busy_timeout_ms

    @property
    def path(self) -> str:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._path,
            isolation_level=None,
            timeout=self._busy_timeout_ms / 1000,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"PRAGMA busy_timeout = {int(self._busy_timeout_ms)}")
        return conn

    def initialize(self) -> None:
        """Create tables and apply safe, versioned schema migrations."""
        conn = self._connect()
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]

            if version > SCHEMA_VERSION:
                raise StoreError(
                    f"database schema v{version} is newer than this code "
                    f"(v{SCHEMA_VERSION})"
                )

            # Create missing tables. Existing tables are left untouched.
            conn.executescript(SCHEMA)

            conn.execute("BEGIN IMMEDIATE")
            try:
                columns = {
                    row["name"]
                    for row in conn.execute(
                        "PRAGMA table_info(payments)"
                    ).fetchall()
                }

                if "paypal_approve_url" not in columns:
                    conn.execute(
                        "ALTER TABLE payments ADD COLUMN paypal_approve_url TEXT"
                    )

                if "payment_channel" not in columns:
                    conn.execute(
                        "ALTER TABLE payments ADD COLUMN "
                        "payment_channel TEXT NOT NULL DEFAULT 'executor'"
                    )

                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                conn.execute("COMMIT")

            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

        finally:
            conn.close()

    @contextmanager
    def transaction(
        self, *, write: bool = True
    ) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.execute("COMMIT")

        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

        finally:
            conn.close()
