"""Authenticated audit-chain checkpoints stored outside the SQLite database."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from seatbelt.store.audit import GENESIS_HASH, canonical_json

_VERSION = 1


class CheckpointError(ValueError):
    """Raised when an audit checkpoint is missing, malformed, or unauthenticated."""


def _payload(seq: int, head_hash: str, created_at: str) -> dict[str, Any]:
    return {
        "version": _VERSION,
        "seq": seq,
        "head_hash": head_hash,
        "created_at": created_at,
    }


def _signature(key: bytes, payload: dict[str, Any]) -> str:
    return hmac.new(
        key,
        canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def write_checkpoint(path: str | Path, key: bytes, seq: int, head_hash: str) -> None:
    """Atomically write an authenticated checkpoint for a verified chain head."""
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise CheckpointError("checkpoint sequence must be a non-negative integer")

    if (
        not isinstance(head_hash, str)
        or len(head_hash) != 64
        or any(char not in "0123456789abcdef" for char in head_hash)
    ):
        raise CheckpointError("checkpoint hash must be a lowercase SHA-256 digest")

    if seq == 0 and head_hash != GENESIS_HASH:
        raise CheckpointError("empty-chain checkpoint must use the genesis hash")

    created_at = datetime.now(timezone.utc).isoformat()
    payload = _payload(seq, head_hash, created_at)
    document = {**payload, "signature": _signature(key, payload)}
    encoded = json.dumps(document, sort_keys=True, indent=2) + "\n"

    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)

    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = handle.name
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_path, destination)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


def read_checkpoint(path: str | Path, key: bytes) -> tuple[int, str]:
    """Read and authenticate a checkpoint. Never creates or replaces one."""
    try:
        document = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CheckpointError("audit checkpoint does not exist") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CheckpointError("audit checkpoint cannot be read") from exc

    if not isinstance(document, dict):
        raise CheckpointError("audit checkpoint must be a JSON object")

    expected_fields = {"version", "seq", "head_hash", "created_at", "signature"}
    if set(document) != expected_fields:
        raise CheckpointError("audit checkpoint has missing or unexpected fields")

    version = document["version"]
    seq = document["seq"]
    head_hash = document["head_hash"]
    created_at = document["created_at"]
    signature = document["signature"]

    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version != _VERSION
    ):
        raise CheckpointError("unsupported audit checkpoint version")

    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise CheckpointError("invalid checkpoint sequence")

    if (
        not isinstance(head_hash, str)
        or len(head_hash) != 64
        or any(char not in "0123456789abcdef" for char in head_hash)
    ):
        raise CheckpointError("invalid checkpoint hash")

    if not isinstance(created_at, str) or not created_at:
        raise CheckpointError("invalid checkpoint timestamp")

    if not isinstance(signature, str):
        raise CheckpointError("invalid checkpoint signature")

    if seq == 0 and head_hash != GENESIS_HASH:
        raise CheckpointError("invalid empty-chain checkpoint")

    payload = _payload(seq, head_hash, created_at)
    expected = _signature(key, payload)
    if not hmac.compare_digest(signature, expected):
        raise CheckpointError("audit checkpoint authentication failed")

    return seq, head_hash