from __future__ import annotations

from pathlib import Path

from ordifile.core.logical_source import join_chemstation_runs
from ordifile.core.models import (
    DatasetBundle,
    FileResult,
    FileStatus,
    InstrumentMetadata,
    PeakRecord,
    SampleRecord,
    SeriesKind,
    SignalSeries,
    SourceFile,
)


def _source(path: Path) -> SourceFile:
    return SourceFile(path, path.name, path.name, 16, None, None, 0)


def _bundle(path: Path, *, signal: bool, peaks: int) -> DatasetBundle:
    source = _source(path)
    sample_id = path.stem
    sample = SampleRecord(
        sample_id,
        source,
        acquired_at=None,
        acquired_at_reliable=False,
        instrument=InstrumentMetadata(None, None),
        channels=(),
        detectors=(),
        runtime=None,
    )
    signals = (
        (
            SignalSeries(
                sample_id,
                path.name,
                "FID",
                None,
                (0.0, 1.0),
                (10.0, 20.0),
                x_label="retention_time",
                x_unit="min",
                y_label="detector_response",
                y_unit=None,
                series_kind=SeriesKind.SCIENTIFIC_SIGNAL,
            ),
        )
        if signal
        else ()
    )
    peak_rows = tuple(
        PeakRecord(
            sample_id,
            path.name,
            peak_number=index + 1,
            retention_time=float(index + 1),
            retention_time_unit="min",
            area=100.0 * (index + 1),
        )
        for index in range(peaks)
    )
    return DatasetBundle((source,), (sample,), signals=signals, peaks=peak_rows)


def _signal_result(path: Path) -> FileResult:
    return FileResult(_source(path), FileStatus.SUCCESS, bundle=_bundle(path, signal=True, peaks=0))


def _table_result(path: Path, *, mapped: bool = True) -> FileResult:
    return FileResult(
        _source(path),
        FileStatus.SUCCESS,
        bundle=_bundle(path, signal=False, peaks=2),
        mapping_route="explicit" if mapped else None,
    )


def _run(root: Path, name: str = "SAMPLE01.D") -> Path:
    run = root / name
    (run / "ACQ.M").mkdir(parents=True)
    (run / "DA.M").mkdir()
    (run / "RUN.LOG").write_text("run", encoding="utf-8")
    (run / "SAMPLE.MAC").write_text("macro", encoding="utf-8")
    return run


def _codes(item: FileResult) -> tuple[str, ...]:
    return tuple(issue.code for issue in item.issues)


def test_one_signal_and_one_mapped_table_are_joined(tmp_path: Path) -> None:
    run = _run(tmp_path)

    signal, table = join_chemstation_runs(
        [_signal_result(run / "FID3A.CH"), _table_result(run / "OGE00.CSV")]
    )

    assert signal.bundle is not None
    assert len(signal.bundle.peaks) == 2
    assert {peak.sample_id for peak in signal.bundle.peaks} == {"FID3A"}
    assert {peak.source_file for peak in signal.bundle.peaks} == {"FID3A.CH"}
    assert "AGILENT_D_RUN_JOINED" in _codes(signal)
    assert table.status is FileStatus.SKIPPED
    assert "AGILENT_D_PEAK_TABLE_MERGED" in _codes(table)


def test_files_outside_a_run_directory_are_never_joined(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()

    signal, table = join_chemstation_runs(
        [_signal_result(plain / "FID3A.CH"), _table_result(plain / "OGE00.CSV")]
    )

    assert signal.bundle is not None and signal.bundle.peaks == ()
    assert table.status is FileStatus.SUCCESS
    assert _codes(signal) == ()


def test_two_run_directories_are_joined_independently(tmp_path: Path) -> None:
    first = _run(tmp_path, "A01.D")
    second = _run(tmp_path, "A02.D")

    results = join_chemstation_runs(
        [
            _signal_result(first / "FID3A.CH"),
            _table_result(first / "OGE00.CSV"),
            _signal_result(second / "FID3A.CH"),
            _table_result(second / "OGE00.CSV"),
        ]
    )

    joined = [item for item in results if "AGILENT_D_RUN_JOINED" in _codes(item)]
    assert len(joined) == 2
    assert all(item.bundle is not None and len(item.bundle.peaks) == 2 for item in joined)


def test_an_unmapped_table_is_not_treated_as_the_run_peak_table(tmp_path: Path) -> None:
    run = _run(tmp_path)

    signal, table = join_chemstation_runs(
        [_signal_result(run / "FID3A.CH"), _table_result(run / "OGE00.CSV", mapped=False)]
    )

    assert signal.bundle is not None and signal.bundle.peaks == ()
    assert table.status is FileStatus.SUCCESS
    assert _codes(signal) == ()


def test_two_mapped_tables_in_one_run_are_reported_not_guessed(tmp_path: Path) -> None:
    run = _run(tmp_path)

    results = join_chemstation_runs(
        [
            _signal_result(run / "FID3A.CH"),
            _table_result(run / "OGE00.CSV"),
            _table_result(run / "OGE01.CSV"),
        ]
    )

    signal = results[0]
    assert signal.bundle is not None and signal.bundle.peaks == ()
    assert "AGILENT_D_JOIN_AMBIGUOUS" in _codes(signal)
    assert all(item.status is FileStatus.SUCCESS for item in results[1:])


def test_two_signals_in_one_run_are_reported_not_guessed(tmp_path: Path) -> None:
    run = _run(tmp_path)

    results = join_chemstation_runs(
        [
            _signal_result(run / "FID3A.CH"),
            _signal_result(run / "FID2B.CH"),
            _table_result(run / "OGE00.CSV"),
        ]
    )

    assert all("AGILENT_D_JOIN_AMBIGUOUS" in _codes(item) for item in results[:2])
    assert results[2].status is FileStatus.SUCCESS


def test_a_run_with_only_a_signal_is_left_alone(tmp_path: Path) -> None:
    run = _run(tmp_path)

    (signal,) = join_chemstation_runs([_signal_result(run / "FID3A.CH")])

    assert signal.bundle is not None and signal.bundle.peaks == ()
    assert _codes(signal) == ()


def test_a_directory_named_d_without_the_skeleton_does_not_join(tmp_path: Path) -> None:
    fake = tmp_path / "NOTREAL.D"
    fake.mkdir()

    signal, table = join_chemstation_runs(
        [_signal_result(fake / "FID3A.CH"), _table_result(fake / "OGE00.CSV")]
    )

    assert signal.bundle is not None and signal.bundle.peaks == ()
    assert table.status is FileStatus.SUCCESS
