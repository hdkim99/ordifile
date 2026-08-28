# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

from ordifile.adapters.agilent_chemstation_ch_v179 import AgilentChemStationChV179Adapter
from ordifile.adapters.base import ParseOptions, SupportStatus
from ordifile.core.errors import ParseError
from ordifile.core.models import SeriesKind

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))

from generate_agilent_ch_v179 import synthetic_v179_bytes  # noqa: E402


def _write(path: Path, data: bytes | None = None) -> Path:
    path.write_bytes(synthetic_v179_bytes() if data is None else data)
    return path


def _parse_error(path: Path) -> ParseError:
    with pytest.raises(ParseError) as caught:
        AgilentChemStationChV179Adapter().parse(path, ParseOptions())
    return caught.value


def test_descriptor_declares_an_experimental_scientific_signal() -> None:
    descriptor = AgilentChemStationChV179Adapter.descriptor
    assert descriptor.adapter_id == "agilent_chemstation_ch_v179"
    assert descriptor.extensions == (".ch",)
    assert descriptor.support_status is SupportStatus.EXPERIMENTAL
    assert descriptor.series_kinds == (SeriesKind.SCIENTIFIC_SIGNAL,)


def test_signal_uses_the_stored_axis_scale_and_unit(tmp_path: Path) -> None:
    data = synthetic_v179_bytes(start_ms=0.0, step_ms=20.0, values=(10.0, 40.0, 90.0, 40.0, 10.0))

    bundle = AgilentChemStationChV179Adapter().parse(
        _write(tmp_path / "FID3A.CH", data), ParseOptions()
    )

    assert len(bundle.signals) == 1
    signal = bundle.signals[0]
    assert signal.series_kind is SeriesKind.SCIENTIFIC_SIGNAL
    assert signal.x_unit == "min"
    assert signal.y_unit == "pA"
    # 20 ms per point, expressed in minutes.
    assert signal.x_values == pytest.approx((0.0, 1 / 3000, 2 / 3000, 3 / 3000, 4 / 3000))
    assert signal.y_values == pytest.approx(tuple(v / 7680.0 for v in (10, 40, 90, 40, 10)))
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["internal_version"] == 179
    assert metadata["point_count"] == 5
    assert metadata["response_unit_status"] == "observed"
    assert metadata["response_scale_status"] == "stored_supported_not_proven"
    assert "AGILENT_CH_V179_EXPERIMENTAL_SIGNAL" in {issue.code for issue in bundle.warnings}


def test_unobserved_response_unit_keeps_values_without_a_physical_unit(
    tmp_path: Path,
) -> None:
    data = synthetic_v179_bytes(response_unit="zz")

    bundle = AgilentChemStationChV179Adapter().parse(
        _write(tmp_path / "FID3A.CH", data), ParseOptions()
    )

    assert bundle.signals[0].y_unit is None
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["response_unit_status"] == "unresolved"
    assert metadata["stored_response_unit_lexeme"] == "zz"
    assert "AGILENT_CH_V179_RESPONSE_UNIT_UNRESOLVED" in {issue.code for issue in bundle.warnings}


def test_stored_maximum_disagreeing_with_the_payload_fails_closed(tmp_path: Path) -> None:
    # The header maximum is an independent check that the payload was read correctly.
    data = synthetic_v179_bytes(stored_maximum=1234.0)

    error = _parse_error(_write(tmp_path / "FID3A.CH", data))

    assert error.code == "AGILENT_CH_PAYLOAD_INVALID"


def test_partial_stored_value_fails_closed(tmp_path: Path) -> None:
    error = _parse_error(_write(tmp_path / "FID3A.CH", synthetic_v179_bytes(trailing=b"\x00")))

    assert error.code == "AGILENT_CH_PAYLOAD_INVALID"


def test_non_increasing_run_boundaries_fail_closed(tmp_path: Path) -> None:
    data = synthetic_v179_bytes(start_ms=100.0, end_ms=100.0)

    error = _parse_error(_write(tmp_path / "FID3A.CH", data))

    assert error.code == "AGILENT_CH_TIME_AXIS_INVALID"


def test_non_positive_response_scale_fails_closed(tmp_path: Path) -> None:
    error = _parse_error(_write(tmp_path / "FID3A.CH", synthetic_v179_bytes(response_scale=0.0)))

    assert error.code == "AGILENT_CH_RESPONSE_SCALE_INVALID"


def test_non_finite_stored_value_fails_closed(tmp_path: Path) -> None:
    data = bytearray(synthetic_v179_bytes())
    struct.pack_into("<d", data, 6_144, float("nan"))

    error = _parse_error(_write(tmp_path / "FID3A.CH", bytes(data)))

    assert error.code == "AGILENT_CH_PAYLOAD_INVALID"


def test_other_internal_versions_are_not_claimed(tmp_path: Path) -> None:
    data = synthetic_v179_bytes(version_text="181", numeric_version=181)
    path = _write(tmp_path / "FID3A.CH", data)

    detection = AgilentChemStationChV179Adapter().probe(path)

    assert detection.matched is False


def test_renamed_basename_is_recognised_but_not_routable(tmp_path: Path) -> None:
    path = _write(tmp_path / "renamed.ch")

    detection = AgilentChemStationChV179Adapter().probe(path)

    assert detection.matched is True
    assert detection.routable is False
    assert detection.failure_code == "AGILENT_CH_DETECTOR_UNSUPPORTED"
