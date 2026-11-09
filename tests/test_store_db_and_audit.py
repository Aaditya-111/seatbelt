import json
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

def test_forged_appended_entry_is_detected(db):
    add(db, 3)

    conn = raw(db)
    last = conn.execute(
        "SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1"
    ).fetchone()

    conn.execute(
        """
        INSERT INTO audit_log
            (seq, ts, event, actor, subject_id, data, prev_hash, hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            4,
            T.isoformat(),
            "payment.captured",
            "attacker",
            "forged-payment",
            '{"amount":"999999.00"}',
            last["hash"],
            "0" * 64,
        ),
    )
    conn.close()

    with db.transaction(write=False) as conn:
        status = audit.verify(conn, KEY)

    assert not status.ok
    assert status.first_bad_seq == 4


def test_editing_the_final_entry_is_detected(db):
    add(db, 3)

    conn = raw(db)
    conn.execute(
        "UPDATE audit_log SET event = 'payment.forged' WHERE seq = 3"
    )
    conn.close()

    with db.transaction(write=False) as conn:
        status = audit.verify(conn, KEY)

    assert not status.ok
    assert status.first_bad_seq == 3


def test_malformed_hash_storage_returns_invalid_chain(db):
    add(db, 2)

    conn = raw(db)
    conn.execute(
        "UPDATE audit_log SET hash = ? WHERE seq = 2",
        (sqlite3.Binary(b"malformed-hash"),),
    )
    conn.close()

    with db.transaction(write=False) as conn:
        status = audit.verify(conn, KEY)

    assert not status.ok
    assert status.first_bad_seq == 2

def test_malformed_entry_data_returns_invalid_chain(db):
    add(db, 2)

    conn = raw(db)
    conn.execute(
        "UPDATE audit_log SET data = ? WHERE seq = 2",
        (sqlite3.Binary(b"\xff\xfe"),),
    )
    conn.close()

    with db.transaction(write=False) as conn:
        status = audit.verify(conn, KEY)

    assert not status.ok
    assert status.first_bad_seq == 2


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


def test_v1_database_is_upgraded_without_losing_payment_data(tmp_path):
    database = Database(tmp_path / "migration.db")
    database.initialize()

    # Simulate an existing v1 database.
    with database.transaction() as conn:
        conn.execute("ALTER TABLE payments DROP COLUMN paypal_approve_url")
        conn.execute("PRAGMA user_version = 1")

    database.initialize()

    with database.transaction(write=False) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(payments)").fetchall()
        }

    assert version == 4
    assert "paypal_approve_url" in columns
    assert "payment_channel" in columns
    assert "paypal_approve_url" in columns
from datetime import timedelta
from decimal import Decimal

from seatbelt.errors import InvalidTransitionError, NotFoundError
from seatbelt.policy import PaymentRequest
from seatbelt.paypal.models import Money
from seatbelt.service import FakeExecutor, GuardService
from seatbelt.store import GuardStore, PaymentChannel


def test_paypal_checkout_is_persisted_and_resolved_by_order_id(db):
    store, payment = make_paypal_store_payment(db)

    updated = store.attach_checkout(
        payment.payment_id,
        "ORDER-STORE-1",
        "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-STORE-1",
        now=T,
    )

    assert updated.status.value == "awaiting_payer"
    assert updated.paypal_order_id == "ORDER-STORE-1"
    assert updated.paypal_approve_url.endswith("token=ORDER-STORE-1")

    resolved = store.get_payment_by_order_id("ORDER-STORE-1")
    assert resolved.payment_id == payment.payment_id
    assert resolved.payment_channel is PaymentChannel.PAYPAL


def test_unknown_paypal_order_lookup_raises_not_found(db):
    store, _ = make_paypal_store_payment(db)

    with pytest.raises(NotFoundError):
        store.get_payment_by_order_id("UNKNOWN-ORDER")


@pytest.mark.parametrize(
    "approve_url",
    [
        "http://www.sandbox.paypal.com/checkoutnow?token=ORDER-1",
        "https://evil.example/checkoutnow?token=ORDER-1",
        "https://www.paypal.com.evil.example/checkoutnow?token=ORDER-1",
        "https://www.paypal.com/not-checkout?token=ORDER-1",
        "https://user:password@www.paypal.com/checkoutnow?token=ORDER-1",
        "javascript:alert(1)",
    ],
)
def test_attach_checkout_rejects_untrusted_approval_urls(db, approve_url):
    store, payment = make_paypal_store_payment(db)

    with pytest.raises(ValueError, match="invalid PayPal approval URL"):
        store.attach_checkout(
            payment.payment_id,
            "ORDER-INVALID-URL",
            approve_url,
            now=T,
        )


def test_paypal_checkout_rejects_duplicate_attachment(db):
    store, payment = make_paypal_store_payment(db)

    store.attach_checkout(
        payment.payment_id,
        "ORDER-FIRST",
        "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-FIRST",
        now=T,
    )

    with pytest.raises(InvalidTransitionError):
        store.attach_checkout(
            payment.payment_id,
            "ORDER-SECOND",
            "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-SECOND",
            now=T,
        )


def test_paypal_payment_requires_approval_before_capture(db):
    store, payment = make_paypal_store_payment(db)

    store.attach_checkout(
        payment.payment_id,
        "ORDER-LIFECYCLE",
        "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-LIFECYCLE",
        now=T,
    )

    with pytest.raises(InvalidTransitionError):
        store.mark_captured(
            payment.payment_id,
            "CAPTURE-TOO-EARLY",
            now=T,
        )

    approved = store.mark_payer_approved(payment.payment_id, now=T)
    assert approved.status.value == "reserved"

    captured = store.mark_captured(
        payment.payment_id,
        "CAPTURE-LIFECYCLE",
        now=T,
    )

    assert captured.status.value == "captured"
    assert captured.paypal_capture_id == "CAPTURE-LIFECYCLE"


def test_paypal_payer_approval_cannot_be_recorded_twice(db):
    store, payment = make_paypal_store_payment(db)

    store.attach_checkout(
        payment.payment_id,
        "ORDER-APPROVAL-ONCE",
        "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-APPROVAL-ONCE",
        now=T,
    )

    store.mark_payer_approved(payment.payment_id, now=T)

    with pytest.raises(InvalidTransitionError):
        store.mark_payer_approved(payment.payment_id, now=T)
from datetime import timedelta
from decimal import Decimal

from seatbelt.errors import InvalidTransitionError, NotFoundError
from seatbelt.policy import PaymentRequest
from seatbelt.service import FakeExecutor, GuardService
from seatbelt.store import GuardStore, PaymentChannel


def make_paypal_store_payment(db, request_id="paypal-store-1"):
    signing_key = "k" * 40
    store = GuardStore(db, signing_key)

    service = GuardService(
        store,
        FakeExecutor(),
        signing_key,
        max_mandate_ttl=timedelta(hours=24),
        clock=lambda: T,
    )

    mandate, _ = service.issue_mandate(
        agent_id="agent-store-test",
        currency="USD",
        per_payment_limit="100",
        total_limit="300",
        approval_threshold="40",
        allowed_payees=["shop-a"],
        ttl=timedelta(hours=1),
    )

    request = PaymentRequest(
        request_id=request_id,
        agent_id="agent-store-test",
        payee="shop-a",
        money=Money(amount=Decimal("20.00"), currency="USD"),
    )

    payment = store.submit_payment(
        mandate,
        request,
        payment_channel=PaymentChannel.PAYPAL,
        now=T,
    )

    assert payment.status.value == "reserved"
    return store, payment


# ---------------- PayPal checkout persistence and lifecycle ----------------

def test_paypal_checkout_is_persisted_and_resolved_by_order_id(db):
    store, payment = make_paypal_store_payment(db)

    updated = store.attach_checkout(
        payment.payment_id,
        "ORDER-STORE-1",
        "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-STORE-1",
        now=T,
    )

    assert updated.status.value == "awaiting_payer"
    assert updated.paypal_order_id == "ORDER-STORE-1"
    assert updated.paypal_approve_url.endswith("token=ORDER-STORE-1")

    resolved = store.get_payment_by_order_id("ORDER-STORE-1")
    assert resolved.payment_id == payment.payment_id
    assert resolved.payment_channel is PaymentChannel.PAYPAL


def test_unknown_paypal_order_lookup_raises_not_found(db):
    store, _ = make_paypal_store_payment(db)

    with pytest.raises(NotFoundError):
        store.get_payment_by_order_id("UNKNOWN-ORDER")


@pytest.mark.parametrize(
    "approve_url",
    [
        "http://www.sandbox.paypal.com/checkoutnow?token=ORDER-1",
        "https://evil.example/checkoutnow?token=ORDER-1",
        "https://www.paypal.com.evil.example/checkoutnow?token=ORDER-1",
        "https://www.paypal.com/not-checkout?token=ORDER-1",
        "https://user:password@www.paypal.com/checkoutnow?token=ORDER-1",
        "javascript:alert(1)",
    ],
)
def test_attach_checkout_rejects_untrusted_approval_urls(db, approve_url):
    store, payment = make_paypal_store_payment(db)

    with pytest.raises(ValueError, match="invalid PayPal approval URL"):
        store.attach_checkout(
            payment.payment_id,
            "ORDER-INVALID-URL",
            approve_url,
            now=T,
        )


def test_paypal_checkout_rejects_duplicate_attachment(db):
    store, payment = make_paypal_store_payment(db)

    store.attach_checkout(
        payment.payment_id,
        "ORDER-FIRST",
        "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-FIRST",
        now=T,
    )

    with pytest.raises(InvalidTransitionError):
        store.attach_checkout(
            payment.payment_id,
            "ORDER-SECOND",
            "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-SECOND",
            now=T,
        )


def test_paypal_payment_requires_approval_before_capture(db):
    store, payment = make_paypal_store_payment(db)

    store.attach_checkout(
        payment.payment_id,
        "ORDER-LIFECYCLE",
        "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-LIFECYCLE",
        now=T,
    )

    with pytest.raises(InvalidTransitionError):
        store.mark_captured(
            payment.payment_id,
            "CAPTURE-TOO-EARLY",
            now=T,
        )

    approved = store.mark_payer_approved(payment.payment_id, now=T)
    assert approved.status.value == "reserved"

    captured = store.mark_captured(
        payment.payment_id,
        "CAPTURE-LIFECYCLE",
        now=T,
    )

    assert captured.status.value == "captured"
    assert captured.paypal_capture_id == "CAPTURE-LIFECYCLE"


def test_paypal_payer_approval_cannot_be_recorded_twice(db):
    store, payment = make_paypal_store_payment(db)

    store.attach_checkout(
        payment.payment_id,
        "ORDER-APPROVAL-ONCE",
        "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-APPROVAL-ONCE",
        now=T,
    )

    store.mark_payer_approved(payment.payment_id, now=T)

    with pytest.raises(InvalidTransitionError):
        store.mark_payer_approved(payment.payment_id, now=T)


def test_paypal_cancellation_marks_payment_cancelled(db):
    store, payment = make_paypal_store_payment(db)

    store.attach_checkout(
        payment.payment_id,
        "ORDER-CANCEL-STORE-1",
        "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-CANCEL-STORE-1",
        now=T,
    )

    cancelled = store.mark_paypal_cancelled(payment.payment_id, now=T)

    assert cancelled.status.value == "cancelled"
    assert cancelled.paypal_order_id == "ORDER-CANCEL-STORE-1"
    assert store.get_payment_by_order_id(
        "ORDER-CANCEL-STORE-1"
    ).status.value == "cancelled"

def test_paypal_webhook_cannot_resurrect_cancelled_payment(db):
    store, payment = make_paypal_store_payment(db)

    store.attach_checkout(
        payment.payment_id,
        "ORDER-CANCELLED-WEBHOOK",
        "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-CANCELLED-WEBHOOK",
        now=T,
    )
    cancelled = store.mark_paypal_cancelled(payment.payment_id, now=T)
    assert cancelled.status.value == "cancelled"

    with db.transaction(write=False) as conn:
        audit_before = conn.execute(
            "SELECT COUNT(*) FROM audit_log"
        ).fetchone()[0]

    with pytest.raises(InvalidTransitionError):
        store.reconcile_paypal_webhook(
            event_id="WH-CANCELLED-REPLAY",
            event_type="PAYMENT.CAPTURE.COMPLETED",
            payment_id=payment.payment_id,
            capture_id="CAPTURE-CANCELLED-REPLAY",
            now=T,
        )

    current = store.get_payment(payment.payment_id)
    assert current.status.value == "cancelled"
    assert current.paypal_capture_id is None

    with db.transaction(write=False) as conn:
        webhook_count = conn.execute(
            "SELECT COUNT(*) FROM paypal_webhook_events"
        ).fetchone()[0]
        audit_after = conn.execute(
            "SELECT COUNT(*) FROM audit_log"
        ).fetchone()[0]

    assert webhook_count == 0
    assert audit_after == audit_before


def test_paypal_webhook_cannot_resurrect_failed_payment(db):
    store, payment = make_paypal_store_payment(db)

    failed = store.mark_failed(
        payment.payment_id,
        now=T,
    )
    assert failed.status.value == "failed"
    assert failed.failure == "Payment execution failed"

    with db.transaction(write=False) as conn:
        failure_event = conn.execute(
            "SELECT data FROM audit_log "
            "WHERE event = 'payment.failed' AND subject_id = ?",
            (payment.payment_id,),
        ).fetchone()

    assert failure_event is not None
    assert json.loads(failure_event["data"]) == {
        "failure": "Payment execution failed"
    }

    with db.transaction(write=False) as conn:
        audit_before = conn.execute(
            "SELECT COUNT(*) FROM audit_log"
        ).fetchone()[0]

    with pytest.raises(InvalidTransitionError):
        store.reconcile_paypal_webhook(
            event_id="WH-FAILED-REPLAY",
            event_type="PAYMENT.CAPTURE.COMPLETED",
            payment_id=payment.payment_id,
            capture_id="CAPTURE-FAILED-REPLAY",
            now=T,
        )

    current = store.get_payment(payment.payment_id)
    assert current.status.value == "failed"
    assert current.paypal_capture_id is None

    with db.transaction(write=False) as conn:
        webhook_count = conn.execute(
            "SELECT COUNT(*) FROM paypal_webhook_events"
        ).fetchone()[0]
        audit_after = conn.execute(
            "SELECT COUNT(*) FROM audit_log"
        ).fetchone()[0]

    assert webhook_count == 0
    assert audit_after == audit_before

def test_paypal_webhook_deduplicates_same_capture_with_different_event_id(db):
    store, payment = make_paypal_store_payment(db)

    first, first_duplicate = store.reconcile_paypal_webhook(
        event_id="WH-FIRST-DELIVERY",
        event_type="PAYMENT.CAPTURE.COMPLETED",
        payment_id=payment.payment_id,
        capture_id="CAPTURE-SAME-PAYMENT",
        now=T,
    )

    assert first.status.value == "captured"
    assert first.paypal_capture_id == "CAPTURE-SAME-PAYMENT"
    assert first_duplicate is False

    with db.transaction(write=False) as conn:
        audit_before = conn.execute(
            "SELECT COUNT(*) FROM audit_log"
        ).fetchone()[0]

    second, second_duplicate = store.reconcile_paypal_webhook(
        event_id="WH-SECOND-DELIVERY",
        event_type="PAYMENT.CAPTURE.COMPLETED",
        payment_id=payment.payment_id,
        capture_id="CAPTURE-SAME-PAYMENT",
        now=T,
    )

    assert second.status.value == "captured"
    assert second.paypal_capture_id == "CAPTURE-SAME-PAYMENT"
    assert second_duplicate is True

    with db.transaction(write=False) as conn:
        webhook_count = conn.execute(
            "SELECT COUNT(*) FROM paypal_webhook_events"
        ).fetchone()[0]
        audit_after = conn.execute(
            "SELECT COUNT(*) FROM audit_log"
        ).fetchone()[0]

    assert webhook_count == 1
    assert audit_after == audit_before
