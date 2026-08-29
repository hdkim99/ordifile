# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""ANDI/AIA chromatography ``.CDF`` reader (ASTM E1947 data elements)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import ClassVar

from ordifile.adapters._andi_netcdf3 import (
    MAGIC,
    NetCdf3Error,
    NetCdf3File,
    numeric_values,
    read_header,
    text_values,
)
from ordifile.adapters.base import (
    AdapterDescriptor,
    DetectionResult,
    ParseOptions,
    SupportStatus,
)
from ordifile.core.errors import ParseError
from ordifile.core.models import (
    DatasetBundle,
    InstrumentMetadata,
    Issue,
    MetadataEntry,
    PeakRecord,
    SampleRecord,
    SeriesKind,
    Severity,
    SignalSeries,
    SourceFile,
)

_NAMESPACE = "adapter:andi_chromatography_cdf"
_COMPOUND_SOURCE = "canonical:andi_chromatography_cdf.peak_name"
_CHANNEL = "detector"

MAX_CDF_FILE_BYTES = 256 * 1024 * 1024
POINT_DIMENSION = "point_number"
PEAK_DIMENSION = "peak_number"
ORDINATE_VARIABLE = "ordinate_values"
SAMPLING_INTERVAL_VARIABLE = "actual_sampling_interval"
DELAY_TIME_VARIABLE = "actual_delay_time"
RUN_TIME_VARIABLE = "actual_run_time_length"
PEAK_RETENTION_VARIABLE = "peak_retention_time"
# The ordinate variable declares whether the sampling grid is uniform.  Only a uniform
# grid can be rebuilt from the delay and the interval, so the flags are checked and an
# unrecognised or non-uniform declaration fails closed.
UNIFORM_FLAG = "uniform_sampling_flag"
NON_UNIFORM_FLAG = "non_uniform_sampling_flag"

SECONDS_PER_MINUTE = 60.0
# Writers spell the same unit differently.  Only spellings seen in the corpus are
# accepted; an unrecognised one fails closed rather than being assumed to be seconds.
_SECOND_UNIT_SPELLINGS = frozenset(
    {"seconds", "second", "sec", "time in seconds", "time-sec", "time_sec", "s"}
)


def _parse_error(error: NetCdf3Error) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


def _attribute_text(source: NetCdf3File, key: str) -> str | None:
    value = source.attributes.get(key)
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _scalar(source: NetCdf3File, name: str) -> float | None:
    variable = source.variables.get(name)
    if variable is None or variable.element_count != 1:
        return None
    value = numeric_values(source, name)[0]
    return value if math.isfinite(value) else None


def _retention_unit_scale(source: NetCdf3File) -> tuple[float, str]:
    """Return the factor converting stored times to minutes, and how it was decided."""
    declared = _attribute_text(source, "retention_unit")
    if declared is None:
        # ASTM E1947 defines the timing elements in seconds, so an omitted attribute is
        # read as seconds; the decision is reported rather than left implicit.
        return 1.0 / SECONDS_PER_MINUTE, "absent_standard_default_seconds"
    folded = declared.casefold().strip()
    if folded in _SECOND_UNIT_SPELLINGS:
        return 1.0 / SECONDS_PER_MINUTE, "declared_seconds"
    raise NetCdf3Error(
        "ANDI_RETENTION_UNIT_UNSUPPORTED",
        "The file declares a retention unit this reader has not validated.",
        retention_unit=declared,
    )


def _read_peaks(
    source: NetCdf3File,
    peak_count: int,
    scale: float,
    sample_id: str,
    file_name: str,
    detector_unit: str | None,
) -> tuple[tuple[PeakRecord, ...], bool]:
    if not peak_count or PEAK_RETENTION_VARIABLE not in source.variables:
        return (), False
    retention = numeric_values(source, PEAK_RETENTION_VARIABLE)
    if len(retention) != peak_count:
        raise NetCdf3Error(
            "ANDI_PEAK_TABLE_INVALID",
            "The stored peak retention times do not match the declared peak count.",
        )

    def optional(name: str) -> tuple[float, ...] | None:
        variable = source.variables.get(name)
        if variable is None or variable.element_count != peak_count:
            return None
        return numeric_values(source, name)

    areas = optional("peak_area")
    heights = optional("peak_height")
    starts = optional("peak_start_time")
    ends = optional("peak_end_time")
    names: tuple[str, ...] = ()
    if "peak_name" in source.variables:
        candidate = text_values(source, "peak_name")
        if len(candidate) == peak_count:
            names = candidate

    def finite(values: tuple[float, ...] | None, index: int) -> float | None:
        if values is None:
            return None
        value = values[index]
        return value if math.isfinite(value) else None

    peaks: list[PeakRecord] = []
    for index in range(peak_count):
        if not math.isfinite(retention[index]):
            raise NetCdf3Error(
                "ANDI_PEAK_TABLE_INVALID",
                "A stored peak carries a non-finite retention time.",
            )
        height = finite(heights, index)
        if height is not None and height < 0:
            # A negative height is a writer's "not reported" sentinel, not a measurement.
            height = None
        start = finite(starts, index)
        end = finite(ends, index)
        if start is not None and end is not None and not start <= retention[index] <= end:
            raise NetCdf3Error(
                "ANDI_PEAK_TABLE_INVALID",
                "A stored peak does not contain its own retention time.",
            )
        compound = names[index].strip() if names else ""
        peaks.append(
            PeakRecord(
                sample_id,
                file_name,
                channel=_CHANNEL,
                detector=None,
                peak_number=index + 1,
                retention_time=retention[index] * scale,
                retention_time_unit="min",
                area=finite(areas, index),
                height=height,
                compound=compound or None,
                compound_source=_COMPOUND_SOURCE if compound else None,
                status="parsed",
                observation_order=index + 1,
                start_time=None if start is None else start * scale,
                end_time=None if end is None else end * scale,
                area_unit=None,
                height_unit=detector_unit,
            )
        )
    heights_unreported = heights is not None and all(
        not math.isfinite(value) or value <= 0 for value in heights
    )
    return tuple(peaks), heights_unreported


class AndiChromatographyCdfAdapter:
    """Read the chromatogram and stored peak table an ANDI ``.CDF`` file declares."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "andi_chromatography_cdf"
    adapter_version: ClassVar[str] = "0.1.0"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "ANDI/AIA chromatography .CDF, ASTM E1947 data elements (Experimental)",
        (".cdf",),
        True,
        True,
        True,
        True,
        SupportStatus.EXPERIMENTAL,
        (SeriesKind.SCIENTIFIC_SIGNAL,),
    )

    def probe(self, path: Path) -> DetectionResult:
        """Match the extension, the netCDF-3 signature, and the ANDI data elements."""
        if path.suffix.casefold() != ".cdf":
            return DetectionResult(False, 0.0, "the required .cdf extension is absent")
        try:
            if path.stat().st_size > MAX_CDF_FILE_BYTES:
                return DetectionResult(False, 0.0, "the file exceeds the bounded reader size")
            with path.open("rb") as stream:
                signature = stream.read(len(MAGIC)) == MAGIC
        except OSError:
            return DetectionResult(False, 0.0, "bounded header read failed")
        if not signature:
            return DetectionResult(False, 0.0, "the netCDF-3 signature is absent")
        try:
            source = read_header(path.read_bytes())
            self._require_profile(source)
            self._require_uniform_sampling(source)
        except NetCdf3Error as error:
            return DetectionResult(
                True, 0.70, error.message, routable=False, failure_code=error.code
            )
        except OSError:
            return DetectionResult(False, 0.0, "bounded read failed")
        points = source.dimension_length(POINT_DIMENSION) or 0
        peaks = source.dimension_length(PEAK_DIMENSION) or 0
        return DetectionResult(
            True,
            0.99,
            f"netCDF-3 container with the ANDI chromatography elements, {points} "
            f"ordinate point(s) and {peaks} stored peak(s)",
        )

    @staticmethod
    def _require_uniform_sampling(source: NetCdf3File) -> None:
        attributes = source.variables[ORDINATE_VARIABLE].attributes
        uniform = attributes.get(UNIFORM_FLAG)
        non_uniform = attributes.get(NON_UNIFORM_FLAG)
        if isinstance(uniform, str) and uniform.strip().casefold() == "y":
            return
        if isinstance(non_uniform, str) and non_uniform.strip().casefold() == "n":
            return
        raise NetCdf3Error(
            "ANDI_SAMPLING_NOT_UNIFORM",
            "The ordinate values are not declared to be uniformly sampled, so the time "
            "axis cannot be rebuilt from the delay and sampling interval.",
            uniform_sampling_flag=uniform,
            non_uniform_sampling_flag=non_uniform,
        )

    @staticmethod
    def _require_profile(source: NetCdf3File) -> None:
        if ORDINATE_VARIABLE not in source.variables:
            raise NetCdf3Error(
                "ANDI_PROFILE_UNSUPPORTED",
                "The file has no ordinate_values variable, so it is not ANDI chromatography.",
            )
        if source.dimension_length(POINT_DIMENSION) is None:
            raise NetCdf3Error(
                "ANDI_PROFILE_UNSUPPORTED",
                "The file declares no point_number dimension.",
            )

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Return the stored chromatogram and, when present, the stored peak table."""
        del options
        if path.suffix.casefold() != ".cdf":
            raise ParseError(
                "ANDI_EXTENSION_INVALID",
                "The ANDI chromatography profile requires a .cdf source extension.",
            )
        try:
            size = path.stat().st_size
            if size > MAX_CDF_FILE_BYTES:
                raise ParseError(
                    "ANDI_FILE_TOO_LARGE",
                    "The file exceeds the bounded reader size.",
                )
            source = read_header(path.read_bytes())
            self._require_profile(source)
            self._require_uniform_sampling(source)
            scale, unit_status = _retention_unit_scale(source)
            points = source.dimension_length(POINT_DIMENSION) or 0
            ordinate = numeric_values(source, ORDINATE_VARIABLE)
            if len(ordinate) != points or points < 2:
                raise NetCdf3Error(
                    "ANDI_ORDINATE_INVALID",
                    "The stored ordinate values do not match the declared point count.",
                )
            interval = _scalar(source, SAMPLING_INTERVAL_VARIABLE)
            delay = _scalar(source, DELAY_TIME_VARIABLE) or 0.0
            if interval is None or interval <= 0:
                raise NetCdf3Error(
                    "ANDI_TIME_BASE_INVALID",
                    "The file declares no usable actual_sampling_interval.",
                )
            run_length = _scalar(source, RUN_TIME_VARIABLE)
            peak_count = source.dimension_length(PEAK_DIMENSION) or 0
            detector_unit = _attribute_text(source, "detector_unit")
            sample_id = path.stem
            peaks, heights_unreported = _read_peaks(
                source, peak_count, scale, sample_id, path.name, detector_unit
            )
        except NetCdf3Error as error:
            raise _parse_error(error) from error
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                f"Could not read the input ({type(error).__name__}).",
            ) from error

        times = tuple((delay + index * interval) * scale for index in range(points))
        last_time = times[-1]
        if peaks and not all(
            times[0] - interval * scale <= peak.retention_time <= last_time + interval * scale
            for peak in peaks
            if peak.retention_time is not None
        ):
            raise ParseError(
                "ANDI_PEAK_TABLE_INVALID",
                "A stored peak falls outside the chromatogram's own time axis.",
            )

        source_file = SourceFile(path, path.name, path.name, size, None, None, 0)
        sample = SampleRecord(
            sample_id,
            source_file,
            acquired_at=None,
            acquired_at_reliable=False,
            instrument=InstrumentMetadata(
                _attribute_text(source, "detector_name"),
                _attribute_text(source, "dataset_origin"),
            ),
            channels=(_CHANNEL,),
            detectors=(_CHANNEL,),
            runtime=None,
        )
        signal = SignalSeries(
            sample_id,
            path.name,
            _CHANNEL,
            None,
            times,
            ordinate,
            x_label="retention_time",
            x_unit="min",
            y_label="detector_response",
            y_unit=detector_unit,
            series_kind=SeriesKind.SCIENTIFIC_SIGNAL,
        )

        values: list[tuple[str, object, str | None]] = [
            ("support_status", "experimental", None),
            ("profile", "ANDI/AIA chromatography (ASTM E1947 data elements)", None),
            ("netcdf_version", source.version, None),
            ("point_count", points, None),
            ("stored_peak_count", peak_count, None),
            ("actual_sampling_interval", interval, "s"),
            ("actual_delay_time", delay, "s"),
            ("retention_unit_status", unit_status, None),
            ("detector_unit_status", "declared" if detector_unit else "absent", None),
            ("stored_peak_height_column_populated", not heights_unreported, None),
            ("timestamp_status", "unsupported_timezone_unresolved", None),
        ]
        if run_length is not None:
            values.append(("actual_run_time_length", run_length, "s"))
        for key in (
            "aia_template_revision",
            "netcdf_revision",
            "dataset_completeness",
            "dataset_origin",
            "dataset_owner",
            "detector_name",
            "detector_unit",
            "retention_unit",
            "experiment_title",
            "operator_name",
            "sample_name",
            "sample_id",
            "injection_date_time_stamp",
            "separation_experiment_type",
            "peak_processing_results_comments",
        ):
            text = _attribute_text(source, key)
            if text is not None:
                values.append((key, text, None))
        metadata = tuple(
            MetadataEntry(sample_id, path.name, _NAMESPACE, key, value, unit)
            for key, value, unit in values
        )

        warnings: tuple[Issue, ...] = (
            Issue(
                "ANDI_EXPERIMENTAL_PROFILE",
                "ANDI chromatography support reads the standard's data elements; vendor "
                "extension variables in the same file are not interpreted.",
                Severity.WARNING,
                path.name,
            ),
        )
        if unit_status == "absent_standard_default_seconds":
            warnings += (
                Issue(
                    "ANDI_RETENTION_UNIT_ABSENT",
                    "The file declares no retention_unit, so the timing elements were read "
                    "as seconds, which is what ASTM E1947 defines them to be.",
                    Severity.WARNING,
                    path.name,
                ),
            )
        if detector_unit is None:
            warnings += (
                Issue(
                    "ANDI_DETECTOR_UNIT_ABSENT",
                    "The file declares no detector_unit, so the response is preserved without one.",
                    Severity.WARNING,
                    path.name,
                ),
            )
        if heights_unreported:
            warnings += (
                Issue(
                    "ANDI_PEAK_HEIGHT_NOT_REPORTED",
                    "Every stored peak height is zero or negative, so the writer did not "
                    "populate that column; negative sentinels were dropped rather than "
                    "reported as heights.",
                    Severity.WARNING,
                    path.name,
                ),
            )
        if peaks:
            warnings += (
                Issue(
                    "ANDI_STORED_PEAK_TABLE",
                    "Peaks are the stored values the file itself carries; Ordifile did not "
                    "integrate the chromatogram.",
                    Severity.WARNING,
                    path.name,
                ),
            )
        if run_length is not None and abs((points - 1) * interval - run_length) > interval:
            warnings += (
                Issue(
                    "ANDI_RUN_LENGTH_INCONSISTENT",
                    "The declared run length disagrees with the point count and sampling "
                    "interval; the axis was built from the interval.",
                    Severity.WARNING,
                    path.name,
                ),
            )
        return DatasetBundle(
            (source_file,),
            (sample,),
            signals=(signal,),
            peaks=peaks,
            metadata=metadata,
            warnings=warnings,
        )
