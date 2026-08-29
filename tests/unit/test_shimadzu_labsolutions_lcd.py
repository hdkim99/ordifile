from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

from ordifile.adapters.base import ParseOptions, SupportStatus
from ordifile.adapters.shimadzu_labsolutions_lcd import ShimadzuLabsolutionsLcdAdapter
from ordifile.core.errors import ParseError
from ordifile.core.models import DatasetBundle, SeriesKind

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_shimadzu_labsolutions_lcd import (  # noqa: E402
    synthetic_lcd_bytes,
)

_SECOND = (10, 50, 90, 300)


def _write(path: Path, **kwargs: object) -> Path:
    kwargs.setdefault("scan_count", 1_024)
    path.write_bytes(synthetic_lcd_bytes(**kwargs))
    return path


def _parse(path: Path) -> DatasetBundle:
    return ShimadzuLabsolutionsLcdAdapter().parse(path, ParseOptions())


def _error(path: Path) -> ParseError:
    with pytest.raises(ParseError) as caught:
        _parse(path)
    return caught.value


def _meta(bundle: DatasetBundle) -> dict[str, object]:
    return {entry.key: entry.value for entry in bundle.metadata}


def test_descriptor_declares_experimental_signal_only_support() -> None:
    descriptor = ShimadzuLabsolutionsLcdAdapter.descriptor

    assert descriptor.adapter_id == "shimadzu_labsolutions_lcd"
    assert descriptor.extensions == (".lcd",)
    assert descriptor.support_status is SupportStatus.EXPERIMENTAL
    assert descriptor.series_kinds == (SeriesKind.SCIENTIFIC_SIGNAL,)
    assert descriptor.signals
    assert not descriptor.peaks


def test_probe_requires_the_extension_and_the_ttfl_identity(tmp_path: Path) -> None:
    adapter = ShimadzuLabsolutionsLcdAdapter()
    source = _write(tmp_path / "synthetic.LCD", second_channel_scans=_SECOND)

    result = adapter.probe(source)

    assert result.matched
    assert result.confidence == pytest.approx(0.99)
    assert "2 validated TTFL channel(s)" in result.reason
    assert not adapter.probe(_write(tmp_path / "synthetic.bin")).matched


def test_each_populated_slot_becomes_its_own_channel(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "two.lcd", second_channel_scans=_SECOND))

    assert [series.channel for series in bundle.signals] == ["TIC Data 0", "TIC Data 1"]
    assert bundle.samples[0].channels == ("TIC Data 0", "TIC Data 1")
    assert all(series.series_kind is SeriesKind.SCIENTIFIC_SIGNAL for series in bundle.signals)
    assert all(series.x_unit == "min" for series in bundle.signals)
    assert all(series.y_unit is None for series in bundle.signals)


def test_a_single_channel_document_yields_one_series(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "one.lcd", second_channel_scans=()))

    assert len(bundle.signals) == 1
    assert _meta(bundle)["channel_count"] == 1


def test_a_sparse_channel_starts_at_its_own_first_scan(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "sparse.lcd", second_channel_scans=_SECOND))

    metadata = _meta(bundle)
    assert metadata["channel_1_first_scan_index"] == _SECOND[0]
    assert metadata["channel_1_stored_spectrum_count"] == len(_SECOND)
    # The window spans the chain, so it is longer than the number of stored spectra.
    assert metadata["channel_1_stored_scan_count"] == _SECOND[-1] - _SECOND[0] + 1
    primary, secondary = bundle.signals
    assert secondary.x_values[0] == pytest.approx(primary.x_values[_SECOND[0]])
    assert {issue.code for issue in bundle.warnings} >= {"SHIMADZU_LCD_SPARSE_CHANNEL"}


def test_a_scan_shared_by_two_channels_costs_extra_time(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "grid.lcd", second_channel_scans=_SECOND))

    metadata = _meta(bundle)
    assert metadata["retention_time_grid_uniform"] is False
    assert metadata["retention_time_interval_min"] == 400
    assert metadata["retention_time_interval_max"] == 900


def test_a_uniform_grid_is_reported_as_uniform(tmp_path: Path) -> None:
    metadata = _meta(_parse(_write(tmp_path / "uniform.lcd", second_channel_scans=())))

    assert metadata["retention_time_grid_uniform"] is True
    assert metadata["retention_time_interval_min"] == 400
    assert metadata["retention_time_interval_max"] == 400


def test_the_tlm_architecture_is_refused_with_its_own_code(tmp_path: Path) -> None:
    error = _error(_write(tmp_path / "tlm.lcd", second_channel_scans=(), use_tlm_storage=True))

    assert error.code == "SHIMADZU_LCD_ARCHITECTURE_UNSUPPORTED"


def test_a_channel_window_that_disagrees_with_its_chain_fails_closed(tmp_path: Path) -> None:
    error = _error(
        _write(
            tmp_path / "window.lcd",
            second_channel_scans=_SECOND,
            channel_declared_overrides={1: 400},
        )
    )

    assert error.code == "SHIMADZU_LCD_CHANNEL_INVALID"


def test_a_secondary_intensity_above_its_primary_fails_closed(tmp_path: Path) -> None:
    error = _error(
        _write(tmp_path / "intensity.lcd", second_channel_scans=(), secondary_exceeds_primary_at=3)
    )

    assert error.code == "SHIMADZU_LCD_CHANNEL_INVALID"


def test_a_non_monotonic_retention_axis_fails_closed(tmp_path: Path) -> None:
    times = [index * 400 for index in range(1_024)]
    times[500] = times[499]

    error = _error(_write(tmp_path / "flat.lcd", second_channel_scans=(), retention_times_ms=times))

    assert error.code == "SHIMADZU_LCD_ARRAY_INVALID"


def test_two_records_claiming_one_predecessor_fail_closed(tmp_path: Path) -> None:
    # Record 4 already names 3 as its predecessor, so record 5 naming 3 forks the chain.
    error = _error(
        _write(tmp_path / "fork.lcd", second_channel_scans=(), index_previous_overrides={5: 3})
    )

    assert error.code == "SHIMADZU_LCD_INDEX_INVALID"


def test_an_extra_chain_head_without_a_matching_slot_fails_closed(tmp_path: Path) -> None:
    error = _error(
        _write(tmp_path / "orphan.lcd", second_channel_scans=(), index_previous_overrides={5: -1})
    )

    assert error.code == "SHIMADZU_LCD_CHANNEL_INVALID"


def test_an_index_record_outside_the_retention_axis_fails_closed(tmp_path: Path) -> None:
    error = _error(
        _write(tmp_path / "scan.lcd", second_channel_scans=(), index_scan_overrides={7: 99_999})
    )

    assert error.code == "SHIMADZU_LCD_INDEX_INVALID"


def test_a_non_lcd_extension_is_refused_before_reading(tmp_path: Path) -> None:
    source = _write(tmp_path / "wrong.dat")

    with pytest.raises(ParseError) as caught:
        _parse(source)

    assert caught.value.code == "SHIMADZU_LCD_EXTENSION_INVALID"


def test_metadata_records_the_architecture_and_stream_digests(tmp_path: Path) -> None:
    metadata = _meta(_parse(_write(tmp_path / "meta.lcd", second_channel_scans=_SECOND)))

    assert metadata["raw_data_architecture"] == "TTFL"
    assert metadata["support_status"] == "experimental"
    assert metadata["tic_signal_unit_status"] == "unknown"
    assert metadata["file_property_schema"] == "3.00"
    assert len(str(metadata["data_index_stream_sha256"])) == 64
    assert len(str(metadata["retention_time_stream_sha256"])) == 64


def test_the_unresolved_third_record_field_is_never_exported(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "fields.lcd", second_channel_scans=_SECOND))

    keys = set(_meta(bundle))
    assert not any("secondary" in key or "base_peak" in key for key in keys)
    assert all(isinstance(value, int) for series in bundle.signals for value in series.y_values)


def test_the_registry_exposes_the_adapter() -> None:
    from ordifile.adapters.registry import create_registry

    ids = {
        descriptor.adapter_id
        for descriptor in create_registry(include_external=False).descriptors()
    }

    assert "shimadzu_labsolutions_lcd" in ids


def test_index_records_are_sixteen_bytes(tmp_path: Path) -> None:
    from ordifile.adapters._shimadzu_labsolutions_lcd_binary import INDEX_RECORD_BYTES

    assert INDEX_RECORD_BYTES == struct.calcsize("<Qii")
