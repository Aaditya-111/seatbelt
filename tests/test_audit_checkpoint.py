
import json

import pytest

from seatbelt.store.audit import GENESIS_HASH
from seatbelt.store.audit_checkpoint import (
    CheckpointError,
    read_checkpoint,
    write_checkpoint,
)


KEY = b"test-audit-key-that-is-long-enough"


def test_checkpoint_round_trip(tmp_path):
    path = tmp_path / "backup" / "checkpoint.json"

    write_checkpoint(path, KEY, 7, "a" * 64)

    assert read_checkpoint(path, KEY) == (7, "a" * 64)


def test_empty_chain_checkpoint_uses_genesis_hash(tmp_path):
    path = tmp_path / "checkpoint.json"

    write_checkpoint(path, KEY, 0, GENESIS_HASH)

    assert read_checkpoint(path, KEY) == (0, GENESIS_HASH)


def test_missing_checkpoint_is_rejected(tmp_path):
    with pytest.raises(CheckpointError, match="does not exist"):
        read_checkpoint(tmp_path / "missing.json", KEY)


def test_modified_checkpoint_is_rejected(tmp_path):
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, KEY, 4, "b" * 64)

    document = json.loads(path.read_text(encoding="utf-8"))
    document["head_hash"] = "c" * 64
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CheckpointError, match="authentication failed"):
        read_checkpoint(path, KEY)


def test_wrong_key_is_rejected(tmp_path):
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, KEY, 4, "d" * 64)

    with pytest.raises(CheckpointError, match="authentication failed"):
        read_checkpoint(path, b"a-different-audit-key")


def test_unexpected_checkpoint_fields_are_rejected(tmp_path):
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, KEY, 4, "e" * 64)

    document = json.loads(path.read_text(encoding="utf-8"))
    document["extra"] = "unexpected"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CheckpointError, match="unexpected fields"):
        read_checkpoint(path, KEY)


@pytest.mark.parametrize("seq", [-1, True, 1.5, "3"])
def test_invalid_checkpoint_sequence_cannot_be_written(tmp_path, seq):
    with pytest.raises(CheckpointError, match="sequence"):
        write_checkpoint(tmp_path / "checkpoint.json", KEY, seq, "f" * 64)


def test_invalid_hash_cannot_be_written(tmp_path):
    with pytest.raises(CheckpointError, match="SHA-256"):
        write_checkpoint(tmp_path / "checkpoint.json", KEY, 1, "NOT-A-HASH")


def test_empty_checkpoint_rejects_non_genesis_hash(tmp_path):
    with pytest.raises(CheckpointError, match="genesis"):
        write_checkpoint(tmp_path / "checkpoint.json", KEY, 0, "a" * 64)


def test_malformed_json_is_rejected(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(CheckpointError, match="cannot be read"):
        read_checkpoint(path, KEY)

@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_unsupported_checkpoint_versions_are_rejected(tmp_path, version):
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, KEY, 4, "a" * 64)

    document = json.loads(path.read_text(encoding="utf-8"))
    document["version"] = version
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CheckpointError, match="version"):
        read_checkpoint(path, KEY)
