
from seatbelt.store import audit
from seatbelt.store.audit_checkpoint import read_checkpoint
from seatbelt.store.db import Database
from seatbelt.store.guard import GuardStore


SIGNING_KEY = "integration-test-signing-key-long-enough"


def make_store(tmp_path):
    db = Database(tmp_path / "seatbelt.db")
    db.initialize()

    checkpoint_path = tmp_path / "external" / "audit-checkpoint.json"
    store = GuardStore(
        db,
        SIGNING_KEY,
        audit_checkpoint_path=str(checkpoint_path),
    )
    audit_key = audit.derive_audit_key(SIGNING_KEY)

    with db.transaction() as conn:
        audit.append(
            conn,
            audit_key,
            event="test.first",
            actor="test",
            subject_id="subject-1",
            data={"value": 1},
        )
        audit.append(
            conn,
            audit_key,
            event="test.second",
            actor="test",
            subject_id="subject-2",
            data={"value": 2},
        )

    return db, store, checkpoint_path, audit_key


def test_first_checkpoint_can_be_created(tmp_path):
    _, store, path, key = make_store(tmp_path)

    status = store.create_audit_checkpoint()

    assert status.ok is True
    assert status.checkpoint_ok is True
    assert status.checkpoint_seq == 2
    assert path.exists()
    assert read_checkpoint(path, key)[0] == 2


def test_missing_checkpoint_fails_verification(tmp_path):
    _, store, _, _ = make_store(tmp_path)

    status = store.verify_audit()

    assert status.ok is False
    assert status.checkpoint_ok is False
    assert "does not exist" in status.checkpoint_error


def test_tail_truncation_is_detected_by_checkpoint(tmp_path):
    db, store, path, key = make_store(tmp_path)
    store.create_audit_checkpoint()
    original_checkpoint = read_checkpoint(path, key)

    with db.transaction() as conn:
        conn.execute("DELETE FROM audit_log WHERE seq = 2")

    status = store.verify_audit()

    assert status.ok is False
    assert status.checkpoint_ok is False
    assert status.checkpoint_seq == 2
    assert "does not match checkpoint" in status.checkpoint_error

    # A failed verification must not replace the trusted checkpoint.
    try:
        store.create_audit_checkpoint()
    except ValueError:
        pass
    else:
        raise AssertionError("checkpoint creation should reject truncated history")

    assert read_checkpoint(path, key) == original_checkpoint


def test_valid_checkpoint_can_be_advanced_after_new_entries(tmp_path):
    db, store, path, key = make_store(tmp_path)
    first = store.create_audit_checkpoint()
    first_checkpoint = read_checkpoint(path, key)

    with db.transaction() as conn:
        audit.append(
            conn,
            key,
            event="test.third",
            actor="test",
            subject_id="subject-3",
            data={"value": 3},
        )

    status_before = store.verify_audit()
    assert status_before.ok is True
    assert status_before.checkpoint_seq == first_checkpoint[0]

    status_after = store.create_audit_checkpoint()

    assert status_after.ok is True
    assert status_after.checkpoint_ok is True
    assert status_after.checkpoint_seq == first.head_seq + 1
    assert read_checkpoint(path, key)[0] == status_after.checkpoint_seq
