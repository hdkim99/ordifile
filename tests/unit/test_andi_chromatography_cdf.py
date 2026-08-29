from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from ordifile.adapters.andi_chromatography_cdf import AndiChromatographyCdfAdapter
from ordifile.adapters.base import ParseOptions, SupportStatus
from ordifile.core.errors import ParseError
from ordifile.core.models import DatasetBundle, SeriesKind

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_andi_chromatography_cdf import synthetic_cdf_bytes  # noqa: E402


def _write(path: Path, **kwargs: Any) -> Path:
    path.write_bytes(synthetic_cdf_bytes(**kwargs))
    return path


def _parse(path: Path) -> DatasetBundle:
    return AndiChromatographyCdfAdapter().parse(path, ParseOptions())


def _error(path: Path) -> ParseError:
    with pytest.raises(ParseError) as caught:
        _parse(path)
    return caught.value


def _meta(bundle: DatasetBundle) -> dict[str, object]:
    return {entry.key: entry.value for entry in bundle.metadata}


def _codes(bundle: DatasetBundle) -> set[str]:
    return {issue.code for issue in bundle.warnings}


def test_descriptor_declares_experimental_signal_and_peak_support() -> None:
    descriptor = AndiChromatographyCdfAdapter.descriptor

    assert descriptor.adapter_id == "andi_chromatography_cdf"
    assert descriptor.extensions == (".cdf",)
    assert descriptor.support_status is SupportStatus.EXPERIMENTAL
    assert descriptor.series_kinds == (SeriesKind.SCIENTIFIC_SIGNAL,)
    assert descriptor.signals
    assert descriptor.peaks


def test_probe_requires_the_extension_and_the_andi_elements(tmp_path: Path) -> None:
    adapter = AndiChromatographyCdfAdapter()

    result = adapter.probe(_write(tmp_path / "sample.CDF"))

    assert result.matched
    assert result.confidence == pytest.approx(0.99)
    assert "64 ordinate point(s) and 3 stored peak(s)" in result.reason
    assert not adapter.probe(_write(tmp_path / "sample.bin")).matched


def test_the_axis_is_rebuilt_from_the_delay_and_the_sampling_interval(tmp_path: Path) -> None:
    bundle = _parse(
        _write(
            tmp_path / "axis.cdf",
            sampling_interval=0.5,
            delay_time=6.0,
            peak_retention_times=[8.0, 12.0, 16.0],
        )
    )

    series = bundle.signals[0]
    assert series.x_unit == "min"
    assert series.x_values[0] == pytest.approx(0.1)
    assert series.x_values[1] == pytest.approx(0.1 + 0.5 / 60.0)
    assert len(series.x_values) == len(series.y_values) == 64


def test_units_are_taken_from_the_file_rather_than_assumed(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "unit.cdf", detector_unit="Volts"))

    assert bundle.signals[0].y_unit == "Volts"
    assert _meta(bundle)["detector_unit_status"] == "declared"
    assert _meta(bundle)["retention_unit_status"] == "declared_seconds"


def test_an_absent_detector_unit_is_preserved_as_none(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "nounit.cdf", detector_unit=None))

    assert bundle.signals[0].y_unit is None
    assert "ANDI_DETECTOR_UNIT_ABSENT" in _codes(bundle)


def test_an_absent_retention_unit_falls_back_to_the_standard_and_says_so(
    tmp_path: Path,
) -> None:
    bundle = _parse(_write(tmp_path / "nort.cdf", retention_unit=None))

    assert _meta(bundle)["retention_unit_status"] == "absent_standard_default_seconds"
    assert "ANDI_RETENTION_UNIT_ABSENT" in _codes(bundle)


@pytest.mark.parametrize("spelling", ["Seconds", "Time-Sec", "time in seconds", "sec"])
def test_known_second_spellings_are_accepted(tmp_path: Path, spelling: str) -> None:
    bundle = _parse(_write(tmp_path / f"{spelling.replace(' ', '_')}.cdf", retention_unit=spelling))

    assert _meta(bundle)["retention_unit_status"] == "declared_seconds"


def test_an_unvalidated_retention_unit_fails_closed(tmp_path: Path) -> None:
    error = _error(_write(tmp_path / "minutes.cdf", retention_unit="minutes"))

    assert error.code == "ANDI_RETENTION_UNIT_UNSUPPORTED"


def test_a_non_uniform_sampling_declaration_fails_closed(tmp_path: Path) -> None:
    error = _error(
        _write(tmp_path / "nonuniform.cdf", uniform_flag=("non_uniform_sampling_flag", "Y"))
    )

    assert error.code == "ANDI_SAMPLING_NOT_UNIFORM"


def test_a_missing_sampling_declaration_fails_closed(tmp_path: Path) -> None:
    error = _error(_write(tmp_path / "noflag.cdf", uniform_flag=None))

    assert error.code == "ANDI_SAMPLING_NOT_UNIFORM"


def test_stored_peaks_are_read_without_integrating_the_chromatogram(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "peaks.cdf"))

    assert len(bundle.peaks) == 3
    first = bundle.peaks[0]
    assert first.peak_number == 1
    assert first.retention_time_unit == "min"
    assert first.retention_time == pytest.approx(4.0 / 60.0)
    assert first.compound == "Compound 0"
    assert first.compound_source == "canonical:andi_chromatography_cdf.peak_name"
    assert "ANDI_STORED_PEAK_TABLE" in _codes(bundle)


def test_a_chromatogram_without_peaks_still_parses(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "nopeaks.cdf", peak_count=0))

    assert bundle.peaks == ()
    assert len(bundle.signals) == 1
    assert _meta(bundle)["stored_peak_count"] == 0


def test_negative_heights_are_dropped_rather_than_reported(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "neg.cdf", peak_heights=[-1.0, -1.0, -1.0]))

    assert [peak.height for peak in bundle.peaks] == [None, None, None]
    assert _meta(bundle)["stored_peak_height_column_populated"] is False
    assert "ANDI_PEAK_HEIGHT_NOT_REPORTED" in _codes(bundle)


def test_an_all_zero_height_column_is_reported_but_preserved(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "zero.cdf", peak_heights=[0.0, 0.0, 0.0]))

    assert [peak.height for peak in bundle.peaks] == [0.0, 0.0, 0.0]
    assert _meta(bundle)["stored_peak_height_column_populated"] is False


def test_start_and_end_times_are_converted_and_bound_checked(tmp_path: Path) -> None:
    bundle = _parse(
        _write(
            tmp_path / "bounds.cdf",
            peak_retention_times=[4.0, 8.0, 12.0],
            peak_start_times=[3.0, 7.0, 11.0],
            peak_end_times=[5.0, 9.0, 13.0],
        )
    )

    first = bundle.peaks[0]
    assert first.start_time == pytest.approx(3.0 / 60.0)
    assert first.end_time == pytest.approx(5.0 / 60.0)


def test_a_peak_outside_its_own_window_fails_closed(tmp_path: Path) -> None:
    error = _error(
        _write(
            tmp_path / "outside.cdf",
            peak_retention_times=[4.0, 8.0, 12.0],
            peak_start_times=[5.0, 7.0, 11.0],
            peak_end_times=[6.0, 9.0, 13.0],
        )
    )

    assert error.code == "ANDI_PEAK_TABLE_INVALID"


def test_a_peak_outside_the_chromatogram_axis_fails_closed(tmp_path: Path) -> None:
    error = _error(
        _write(tmp_path / "far.cdf", point_count=64, peak_retention_times=[4.0, 8.0, 9_999.0])
    )

    assert error.code == "ANDI_PEAK_TABLE_INVALID"


def test_a_file_without_ordinate_values_is_not_andi_chromatography(tmp_path: Path) -> None:
    error = _error(_write(tmp_path / "noord.cdf", omit_ordinate=True))

    assert error.code == "ANDI_PROFILE_UNSUPPORTED"


def test_record_variables_are_refused(tmp_path: Path) -> None:
    error = _error(_write(tmp_path / "records.cdf", record_count=3))

    assert error.code == "NETCDF3_RECORD_VARIABLES_UNSUPPORTED"


def test_an_unsupported_netcdf_version_fails_closed(tmp_path: Path) -> None:
    source = _write(tmp_path / "v5.cdf")
    data = bytearray(source.read_bytes())
    data[3] = 5
    source.write_bytes(bytes(data))

    assert _error(source).code == "NETCDF3_VERSION_UNSUPPORTED"


def test_the_sixty_four_bit_offset_variant_is_supported(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "v2.cdf", version=2))

    assert _meta(bundle)["netcdf_version"] == 2
    assert len(bundle.signals[0].x_values) == 64


def test_a_truncated_file_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "cut.cdf"
    source.write_bytes(synthetic_cdf_bytes()[:120])

    assert _error(source).code in {"NETCDF3_TRUNCATED", "NETCDF3_HEADER_INVALID"}


def test_global_attributes_reach_metadata(tmp_path: Path) -> None:
    metadata = _meta(_parse(_write(tmp_path / "meta.cdf")))

    assert metadata["dataset_origin"] == "Synthetic Instruments"
    assert metadata["dataset_completeness"] == "C1+C2"
    assert metadata["aia_template_revision"] == "1.0"
    assert metadata["support_status"] == "experimental"


def test_the_registry_exposes_the_adapter() -> None:
    from ordifile.adapters.registry import create_registry

    ids = {
        descriptor.adapter_id
        for descriptor in create_registry(include_external=False).descriptors()
    }

    assert "andi_chromatography_cdf" in ids
