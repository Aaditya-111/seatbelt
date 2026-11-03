"""A tamper-evident audit log.

Each entry's hash is an HMAC (keyed with a secret derived from the signing key) over the
entry's contents AND the previous entry's hash. So:
  * editing or deleting a past entry breaks every hash after it;
  * someone who can edit the database file but does NOT hold the key cannot recompute valid
    hashes, so a forged history is detectable.

Limit worth knowing: removing the most recent entries cannot be detected from the database
alone. Record the `head_hash` that verification reports somewhere outside the database (the
API will expose it) to catch that.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from pydantic import SecretStr

from seatbelt.store.models import ChainStatus

GENESIS_HASH = "0" * 64
_KEY_CONTEXT = b"seatbelt-audit-log-v1"


def derive_audit_key(signing_key: SecretStr | str | bytes) -> bytes:
    if isinstance(signing_key, SecretStr):
        signing_key = signing_key.get_secret_value()
    raw = signing_key.encode("utf-8") if isinstance(signing_key, str) else signing_key
    return hmac.new(raw, _KEY_CONTEXT, hashlib.sha256).digest()


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def _entry_hash(
    key: bytes, seq: int, ts: str, event: str, actor: str, subject_id: str, data: str, prev: str
) -> str:
    # A JSON list is unambiguous: no field can bleed into its neighbour.
    message = json.dumps([seq, ts, event, actor, subject_id, data, prev]).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def append(
    conn: sqlite3.Connection,
    key: bytes,
    *,
    event: str,
    actor: str,
    subject_id: str,
    data: dict[str, Any],
    now: datetime | None = None,
) -> int:
    """Add one entry. Must run inside a write transaction so seq/prev_hash cannot race."""
    ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    last = conn.execute("SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    seq = 1 if last is None else last["seq"] + 1
    prev = GENESIS_HASH if last is None else last["hash"]
    data_json = canonical_json(data)
    digest = _entry_hash(key, seq, ts, event, actor, subject_id, data_json, prev)
    conn.execute(
        "INSERT INTO audit_log (seq, ts, event, actor, subject_id, data, prev_hash, hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (seq, ts, event, actor, subject_id, data_json, prev, digest),
    )
    return seq


def verify(conn: sqlite3.Connection, key: bytes) -> ChainStatus:
    expected_seq = 1
    prev = GENESIS_HASH
    for row in conn.execute("SELECT * FROM audit_log ORDER BY seq ASC"):
        if row["seq"] != expected_seq:
            return ChainStatus(
                ok=False,
                entries=expected_seq - 1,
                first_bad_seq=expected_seq,
                reason=f"entry {expected_seq} is missing (found {row['seq']})",
            )
        if row["prev_hash"] != prev:
            return ChainStatus(
                ok=False,
                entries=expected_seq - 1,
                first_bad_seq=row["seq"],
                reason="link to the previous entry is broken",
            )
        recomputed = _entry_hash(
            key,
            row["seq"],
            row["ts"],
            row["event"],
            row["actor"],
            row["subject_id"],
            row["data"],
            row["prev_hash"],
        )
        if not hmac.compare_digest(recomputed, row["hash"]):
            return ChainStatus(
                ok=False,
                entries=expected_seq - 1,
                first_bad_seq=row["seq"],
                reason="entry contents do not match their signature",
            )
        prev = row["hash"]
        expected_seq += 1
    return ChainStatus(
        ok=True,
        entries=expected_seq - 1,
        head_seq=expected_seq - 1 or None,
        head_hash=prev if expected_seq > 1 else None,
    )