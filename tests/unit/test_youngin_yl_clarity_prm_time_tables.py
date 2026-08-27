from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from ordifile.adapters._youngin_yl_clarity_prm_binary import read_prm
from ordifile.adapters._youngin_yl_clarity_prm_time_tables import read_prm_time_tables

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_youngin_yl_clarity_prm import synthetic_prm_bytes  # noqa: E402


def _read(path: Path):  # type: ignore[no-untyped-def]
    decoded = read_prm(path)
    return read_prm_time_tables(
        path,
        expected_sha256=decoded.source_sha256,
        layout=decoded.current_revision_layout,
        history_count=decoded.history_count,
    )


def test_current_method_preserves_numbered_tables_and_opaque_events(tmp_path: Path) -> None:
    data = synthetic_prm_bytes(
        channels=((0.0, 2.0, 0.0),),
        marker_records=(((0x20, 0), (0x50, 1), (0x80, 2)),),
        time_table_events=(((11, 0.0, 1.0, 0.0, 32),),),
    )
    path = tmp_path / "synthetic.prm"
    path.write_bytes(data)

    decoded = _read(path)

    assert decoded.status == "matched"
    assert decoded.integration_type == 0x17
    assert len(decoded.tables) == 32
    assert decoded.tables[0].slot_number == 1
    assert tuple(event.opcode for event in decoded.tables[0].events) == (
        50,
        51,
        65,
        72,
        46,
        47,
        11,
    )
    assert decoded.tables[0].events[-1].a_time == 0.0
    assert decoded.tables[0].events[-1].b_time == 1.0
    assert decoded.method_span_sha256 is not None


def test_current_method_selects_last_history(tmp_path: Path) -> None:
    data = synthetic_prm_bytes(
        history_count=3,
        marker_records=(((0x20, 0), (0x50, 1), (0x80, 2)),),
        time_table_events=(((12, 0.0, 1.0, 0.0, 32),),),
    )
    path = tmp_path / "synthetic.prm"
    path.write_bytes(data)

    decoded = _read(path)

    assert decoded.status == "matched"
    assert decoded.tables[0].events[-1].opcode == 12


def test_current_method_rejects_changed_source_hash(tmp_path: Path) -> None:
    data = synthetic_prm_bytes(
        marker_records=(((0x20, 0), (0x50, 1), (0x80, 2)),),
    )
    path = tmp_path / "synthetic.prm"
    path.write_bytes(data)
    decoded = read_prm(path)

    result = read_prm_time_tables(
        path,
        expected_sha256=hashlib.sha256(data + b"changed").hexdigest(),
        layout=decoded.current_revision_layout,
        history_count=decoded.history_count,
    )

    assert result.status == "invalid"
    assert result.issue_code == "YOUNGIN_PRM_TIME_TABLE_SOURCE_CHANGED"


def test_current_method_failure_is_optional_to_structural_parser(tmp_path: Path) -> None:
    data = bytearray(
        synthetic_prm_bytes(
            marker_records=(((0x20, 0), (0x50, 1), (0x80, 2)),),
        )
    )
    path = tmp_path / "synthetic.prm"
    path.write_bytes(data)
    layout = read_prm(path).current_revision_layout
    opcode_key = b"\x06OpCode\x01"
    opcode_offset = data.index(opcode_key)
    data[opcode_offset + 1] = ord("X")
    path.write_bytes(data)

    structural = read_prm(path)
    result = read_prm_time_tables(
        path,
        expected_sha256=structural.source_sha256,
        layout=layout,
        history_count=structural.history_count,
    )

    assert structural.channels[0].record_count == 3
    assert result.status == "invalid"
    assert result.issue_code == "YOUNGIN_PRM_TIME_TABLE_STRUCTURE_INVALID"
