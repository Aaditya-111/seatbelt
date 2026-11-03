import sqlite3
from datetime import datetime, timezone

import pytest

from seatbelt.errors import StoreError
from seatbelt.store import Database, audit

KEY = audit.derive_audit_key("k" * 40)
OTHER_KEY = audit.derive_audit_key("z" * 40)
T = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "t.db")
    database.initialize()
    return database


def add(db, n=1, key=KEY):
    with db.transaction() as conn:
        for i in range(n):
            audit.append(conn, key, event="e", actor="a", subject_id=f"s{i}", data={"i": i}, now=T)


def raw(db):
    conn = sqlite3.connect(db.path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- database ----------------
def test_initialize_is_idempotent(db):
    db.initialize()
    db.initialize()


def test_memory_database_is_refused():
    with pytest.raises(StoreError):
        Database(":memory:")


def test_foreign_keys_and_wal_are_enabled(db):
    with db.transaction(write=False) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_newer_schema_is_refused(db):
    conn = raw(db)
    conn.execute("PRAGMA user_version = 999")
    conn.close()
    with pytest.raises(StoreError, match="newer"):
        db.initialize()


def test_failed_transaction_rolls_back(db):
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            audit.append(conn, KEY, event="e", actor="a", subject_id="s", data={}, now=T)
            raise RuntimeError("boom")
    with db.transaction(write=False) as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


# ---------------- audit chain ----------------
def test_empty_chain_is_ok(db):
    with db.transaction(write=False) as conn:
        status = audit.verify(conn, KEY)
    assert status.ok and status.entries == 0 and status.head_hash is None


def test_chain_verifies_and_links_entries(db):
    add(db, 5)
    with db.transaction(write=False) as conn:
        status = audit.verify(conn, KEY)
        rows = conn.execute("SELECT seq, prev_hash, hash FROM audit_log ORDER BY seq").fetchall()
    assert status.ok and status.entries == 5 and status.head_seq == 5
    assert rows[0]["prev_hash"] == audit.GENESIS_HASH
    assert all(rows[i]["prev_hash"] == rows[i - 1]["hash"] for i in range(1, 5))
    assert status.head_hash == rows[-1]["hash"]


def test_editing_an_entry_is_detected_at_that_entry(db):
    add(db, 5)
    conn = raw(db)
    conn.execute("UPDATE audit_log SET data = '{\"i\":999}' WHERE seq = 3")
    conn.close()
    with db.transaction(write=False) as c:
        status = audit.verify(c, KEY)
    assert not status.ok and status.first_bad_seq == 3


def test_deleting_a_middle_entry_is_detected(db):
    add(db, 5)
    conn = raw(db)
    conn.execute("DELETE FROM audit_log WHERE seq = 2")
    conn.close()
    with db.transaction(write=False) as c:
        status = audit.verify(c, KEY)
    assert not status.ok and status.first_bad_seq == 2


def test_reordering_entries_is_detected(db):
    add(db, 3)
    conn = raw(db)
    conn.execute("UPDATE audit_log SET seq = 99 WHERE seq = 2")
    conn.execute("UPDATE audit_log SET seq = 2 WHERE seq = 3")
    conn.execute("UPDATE audit_log SET seq = 3 WHERE seq = 99")
    conn.close()
    with db.transaction(write=False) as c:
        assert not audit.verify(c, KEY).ok


def test_forged_history_without_the_key_is_detected(db):
    # An attacker rewrites the whole log with their own (wrong) key.
    add(db, 4, key=OTHER_KEY)
    with db.transaction(write=False) as c:
        assert audit.verify(c, OTHER_KEY).ok  # consistent with itself...
        status = audit.verify(c, KEY)  # ...but not with the real key
    assert not status.ok and status.first_bad_seq == 1


def test_truncating_the_tail_is_only_detectable_against_a_remembered_head(db):
    add(db, 5)
    with db.transaction(write=False) as c:
        remembered = audit.verify(c, KEY).head_hash
    conn = raw(db)
    conn.execute("DELETE FROM audit_log WHERE seq > 3")
    conn.close()
    with db.transaction(write=False) as c:
        status = audit.verify(c, KEY)
    assert status.ok  # the chain alone cannot see this
    assert status.head_hash != remembered  # but an outside record of the head can


def test_field_boundaries_cannot_be_shifted(db):
    with db.transaction() as conn:
        audit.append(conn, KEY, event="e", actor="a\u001fb", subject_id="c", data={}, now=T)
    conn = raw(db)
    conn.execute("UPDATE audit_log SET actor = 'a', subject_id = 'b\u001fc'")
    conn.close()
    with db.transaction(write=False) as c:
        assert not audit.verify(c, KEY).ok