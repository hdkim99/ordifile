# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Ordifile command-line entry point."""

from __future__ import annotations

import argparse
import sys
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Never

from ordifile import __version__
from ordifile.adapters.base import SupportStatus
from ordifile.api import convert, get_format_report, inspect_file
from ordifile.core.models import BatchOutcome, SeriesKind
from ordifile.core.peak_mapping import load_peak_table_mapping, load_peak_table_mapping_set

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_PARTIAL_SUCCESS = 3
EXIT_INTERRUPTED = 130
_CONFIGURATION_ERROR_CODES = frozenset(
    {
        "ADAPTER_NOT_FOUND",
        "NO_INPUTS",
        "ON_ERROR_INVALID",
        "OUTPUT_DIRECTORY_MISSING",
        "OUTPUT_EXTENSION_INVALID",
        "OUTPUT_IS_DIRECTORY",
        "OUTPUT_IS_INPUT",
        "OUTPUT_PATH_TOO_LONG",
        "PEAK_MAPPING_ADAPTER_CONFLICT",
        "PEAK_MAPPING_INVALID",
        "PEAK_MAPPING_SHEET_INVALID",
        "SIDECAR_IS_INPUT",
        "SIDECAR_MODE_INVALID",
        "SORT_MODE_INVALID",
        "WINDOWS_OUTPUT_NAME_INVALID",
        "WINDOWS_OUTPUT_NAME_RESERVED",
    }
)


def _terminal_safe(value: object) -> str:
    """Render an untrusted value as deterministic, unambiguous single-line text."""
    text = str(value)
    rendered: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        codepoint = ord(character)
        if character == "\\":
            escape_width = {"x": 2, "u": 4, "U": 8}.get(
                text[index + 1] if index + 1 < len(text) else ""
            )
            escape_end = index + 2 + (escape_width or 0)
            looks_like_rendered_escape = (
                escape_width is not None
                and escape_end <= len(text)
                and all(
                    character in "0123456789abcdefABCDEF"
                    for character in text[index + 2 : escape_end]
                )
            )
            rendered.append("\\\\" if looks_like_rendered_escape else "\\")
        elif character.isprintable() and unicodedata.category(character) not in {
            "Cc",
            "Cf",
            "Cs",
            "Zl",
            "Zp",
        }:
            rendered.append(character)
        elif codepoint <= 0xFF:
            rendered.append(f"\\x{codepoint:02x}")
        elif codepoint <= 0xFFFF:
            rendered.append(f"\\u{codepoint:04x}")
        else:
            rendered.append(f"\\U{codepoint:08x}")
        index += 1
    return "".join(rendered)


class _SafeArgumentParser(argparse.ArgumentParser):
    """Keep argparse diagnostics readable without emitting raw terminal controls."""

    def error(self, message: str) -> Never:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {_terminal_safe(message)}\n")


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _add_parse_options(parser: argparse.ArgumentParser) -> None:
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--adapter",
        help="Use one registered adapter ID instead of automatic detection.",
    )
    parser.add_argument(
        "--sheet",
        help="Read this XLSX sheet instead of selecting an unambiguous compatible sheet.",
    )
    parser.add_argument(
        "--include-hidden-sheets",
        action="store_true",
        help="Include hidden XLSX sheets when detecting a compatible sheet.",
    )
    selection.add_argument(
        "--peak-mapping",
        type=Path,
        help="Apply a strict user-supplied peak-table mapping JSON to generic inputs.",
    )
    selection.add_argument(
        "--peak-mapping-set",
        type=Path,
        help="Route mixed generic tables with reusable exact-structure mapping profiles.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detection evidence and detailed diagnostics.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = _SafeArgumentParser(
        prog="ordifile",
        description=(
            "Batch-convert scientific instrument exports into one ordered Excel workbook."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "formats",
        help="List verified adapters and their documented capabilities.",
        description="List verified adapters and their documented capabilities.",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Detect and inspect one file without writing output.",
        description="Detect and inspect one file without writing output.",
    )
    inspect_parser.add_argument("file", type=Path, help="One regular input file to inspect.")
    _add_parse_options(inspect_parser)

    convert_parser = subparsers.add_parser(
        "convert",
        help="Convert files or folders into one ordered Excel workbook.",
        description="Convert files or folders into one ordered Excel workbook.",
    )
    convert_parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Input files or folders. Folder contents are non-recursive by default.",
    )
    convert_parser.add_argument(
        "--output",
        type=Path,
        default=Path("Ordifile_Result.xlsx"),
        help="Output workbook path (default: Ordifile_Result.xlsx).",
    )
    convert_parser.add_argument(
        "--sort",
        choices=("auto", "acquired_at", "sequence", "filename", "input_order"),
        default="auto",
        help="Requested file order (default: auto).",
    )
    convert_parser.add_argument(
        "--recursive",
        action="store_true",
        help="Discover files below input folders recursively.",
    )
    convert_parser.add_argument(
        "--extension",
        action="append",
        help="Only discover this extension; repeat the option for multiple extensions.",
    )
    convert_parser.add_argument(
        "--include-signals",
        action="store_true",
        help="Write parsed signal series without interpolation.",
    )
    convert_parser.add_argument(
        "--sheet-mode",
        choices=("split", "sidecar-csv"),
        default="split",
        help=(
            "Split data across workbook sheets, or use integrity-recorded CSV sidecars "
            "when a single cell cannot fit (default: split)."
        ),
    )
    convert_parser.add_argument(
        "--on-error",
        choices=("continue", "stop"),
        default="continue",
        help="Continue after a file failure or stop the batch before export (default: continue).",
    )
    convert_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output workbook. Inputs are never overwritten.",
    )
    _add_parse_options(convert_parser)
    return parser


def _run_formats() -> int:
    report = get_format_report()
    descriptors = tuple(
        descriptor for descriptor in report.descriptors if descriptor.tested_fixture
    )
    headers = (
        "Adapter",
        "Name",
        "Extensions",
        "Metadata",
        "Peaks",
        "Signal output",
        "Verification",
    )

    def signal_output(descriptor: object) -> str:
        if not getattr(descriptor, "signals", False):
            return "No"
        kinds = getattr(descriptor, "series_kinds", ())
        labels = []
        if SeriesKind.SCIENTIFIC_SIGNAL in kinds:
            labels.append("Scientific signals")
        if SeriesKind.DECODED_RECORDS in kinds:
            labels.append("Decoded records")
        return ", ".join(labels) or "Yes"

    verification_labels = {
        SupportStatus.VERIFIED: "Verified",
        SupportStatus.EXPERIMENTAL: "Experimental",
        SupportStatus.FIXTURE_DECLARED: "Fixture declared",
    }
    rows = [
        (
            _terminal_safe(item.adapter_id),
            _terminal_safe(item.display_name),
            ", ".join(_terminal_safe(extension) for extension in item.extensions),
            _yes_no(item.metadata),
            _yes_no(item.peaks),
            signal_output(item),
            verification_labels[item.support_status],
        )
        for item in descriptors
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    print("  ".join(value.ljust(widths[index]) for index, value in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    print()
    verified_count = sum(item.support_status is SupportStatus.VERIFIED for item in descriptors)
    experimental_count = sum(
        item.support_status is SupportStatus.EXPERIMENTAL for item in descriptors
    )
    fixture_declared_count = len(descriptors) - verified_count - experimental_count
    print(f"Verified adapters: {verified_count}")
    print(f"Experimental adapters: {experimental_count}")
    print(f"Fixture declarations: {fixture_declared_count}")
    if report.load_errors:
        print(f"External adapter load failures: {len(report.load_errors)}")
        for error in report.load_errors:
            print(f"- {_terminal_safe(error)}")
        print("  Reinstall, update, or remove the affected external adapter package.")
    print(
        "Verified built-in support is limited to documented generic tabular schemas. "
        "Experimental adapters expose only their explicitly documented capabilities; "
        "installed external adapters are listed only when they declare a tested fixture."
    )
    return EXIT_SUCCESS


def _print_issues(result: object, *, verbose: bool) -> None:
    issues = getattr(result, "issues", ())
    if not issues:
        return
    print("Issues:")
    for issue in issues:
        severity = _terminal_safe(issue.severity.value.upper())
        print(f"- {severity} [{_terminal_safe(issue.code)}]: {_terminal_safe(issue.message)}")
        if verbose and issue.context:
            context = ", ".join(
                f"{_terminal_safe(key)}={_terminal_safe(value)}" for key, value in issue.context
            )
            print(f"  Context: {context}")


def _run_inspect(args: argparse.Namespace) -> int:
    mapping = load_peak_table_mapping(args.peak_mapping) if args.peak_mapping else None
    mapping_set = (
        load_peak_table_mapping_set(args.peak_mapping_set) if args.peak_mapping_set else None
    )
    inspected = inspect_file(
        args.file,
        adapter=args.adapter,
        sheet=args.sheet,
        include_hidden_sheets=args.include_hidden_sheets,
        peak_table_mapping=mapping,
        peak_table_mapping_set=mapping_set,
    )
    result = inspected.file
    bundle = result.bundle
    print(f"File: {_terminal_safe(result.source.public_reference)}")
    print(f"Status: {_terminal_safe(result.status.value)}")
    print(f"Detected format: {_terminal_safe(result.source.detected_format or 'not detected')}")
    print(f"Adapter: {_terminal_safe(result.adapter_id or 'none')}")
    print(f"Adapter version: {_terminal_safe(result.adapter_version or 'none')}")
    print(f"SHA-256: {_terminal_safe(result.source.sha256 or 'unavailable')}")
    print(f"Samples: {len(bundle.samples) if bundle is not None else 0}")
    print(f"Peaks: {len(bundle.peaks) if bundle is not None else 0}")
    scientific_signals = (
        sum(signal.series_kind is SeriesKind.SCIENTIFIC_SIGNAL for signal in bundle.signals)
        if bundle is not None
        else 0
    )
    decoded_record_series = (
        sum(signal.series_kind is SeriesKind.DECODED_RECORDS for signal in bundle.signals)
        if bundle is not None
        else 0
    )
    print(f"Scientific signals: {scientific_signals}")
    print(f"Decoded record series: {decoded_record_series}")
    print(f"Metadata entries: {len(bundle.metadata) if bundle is not None else 0}")
    _print_issues(result, verbose=args.verbose)
    if args.verbose:
        print("Detection evidence:")
        if inspected.probes:
            for adapter_id, confidence, reason in inspected.probes:
                print(
                    f"- {_terminal_safe(adapter_id)}: confidence={confidence:.3f}; "
                    f"{_terminal_safe(reason)}"
                )
        else:
            print("- No successful probe evidence was recorded.")
    return EXIT_FAILURE if result.status.value == "failed" else EXIT_SUCCESS


def _print_file_failures(result: object, *, verbose: bool) -> None:
    files = getattr(result, "files", ())
    failed = [item for item in files if item.status.value == "failed"]
    if not failed:
        return
    print("Failed files:")
    for item in failed:
        errors = [issue for issue in item.issues if issue.severity.value == "error"]
        if not errors:
            source_reference = _terminal_safe(item.source.public_reference)
            print(f"- {source_reference}: no structured error was recorded")
            continue
        first = errors[0]
        print(
            f"- {_terminal_safe(item.source.public_reference)} "
            f"[{_terminal_safe(first.code)}]: {_terminal_safe(first.message)}"
        )
        if verbose:
            for issue in errors[1:]:
                print(f"  [{_terminal_safe(issue.code)}]: {_terminal_safe(issue.message)}")


def _print_file_warnings(result: object, *, verbose: bool) -> None:
    files = getattr(result, "files", ())
    warned = [
        (item, [issue for issue in item.issues if issue.severity.value == "warning"])
        for item in files
    ]
    warned = [(item, issues) for item, issues in warned if issues]
    if not warned:
        return
    print("Warning files:")
    for item, warnings in warned:
        first = warnings[0]
        print(
            f"- {_terminal_safe(item.source.public_reference)} "
            f"[{_terminal_safe(first.code)}]: {_terminal_safe(first.message)}"
        )
        if verbose:
            for issue in warnings[1:]:
                print(f"  [{_terminal_safe(issue.code)}]: {_terminal_safe(issue.message)}")


def _print_batch_detection_evidence(result: object) -> None:
    files = getattr(result, "files", ())
    print("Detection evidence:")
    for item in files:
        source_file = _terminal_safe(item.source.public_reference)
        if not item.probes:
            print(f"- {source_file}: no successful probe evidence was recorded")
            continue
        print(f"- {source_file}:")
        for adapter_id, confidence, reason in item.probes:
            print(
                f"  {_terminal_safe(adapter_id)}: confidence={confidence:.3f}; "
                f"{_terminal_safe(reason)}"
            )


def _run_convert(args: argparse.Namespace) -> int:
    print(f"Input paths: {len(args.inputs)}")
    mapping = load_peak_table_mapping(args.peak_mapping) if args.peak_mapping else None
    mapping_set = (
        load_peak_table_mapping_set(args.peak_mapping_set) if args.peak_mapping_set else None
    )

    def print_progress(event: object) -> None:
        stage = getattr(event, "stage", None)
        if stage == "discovery":
            print(f"Discovered files: {getattr(event, 'total', 0)}")
        elif stage == "processing":
            status = getattr(event, "status", None)
            rendered_status = _terminal_safe(getattr(status, "value", "unknown"))
            print(
                f"Processed {getattr(event, 'completed', 0)}/"
                f"{getattr(event, 'total', 0)}: {rendered_status} "
                f"{_terminal_safe(getattr(event, 'source_file', 'unknown'))}"
            )
        elif stage == "export_start":
            print(f"Export started: {_terminal_safe(getattr(event, 'source_file', 'workbook'))}")
        elif stage == "export_complete":
            print(f"Output ready: {_terminal_safe(getattr(event, 'source_file', 'workbook'))}")

    result = convert(
        args.inputs,
        args.output,
        recursive=args.recursive,
        extensions=args.extension,
        sort=args.sort,
        include_signals=args.include_signals,
        adapter=args.adapter,
        sheet=args.sheet,
        include_hidden_sheets=args.include_hidden_sheets,
        peak_table_mapping=mapping,
        peak_table_mapping_set=mapping_set,
        on_error=args.on_error,
        overwrite=args.overwrite,
        sidecar_mode="csv" if args.sheet_mode == "sidecar-csv" else "error",
        progress=print_progress,
    )
    status = {
        BatchOutcome.SUCCESS: "success",
        BatchOutcome.PARTIAL_SUCCESS: "partial success",
        BatchOutcome.FAILED: "failed",
    }[result.outcome]
    print(f"Status: {status}")
    print(f"Output: {_terminal_safe(result.output_path or args.output)}")
    print(f"Successful files: {result.success_count}")
    print(f"Files with warnings: {result.warning_count}")
    print(f"Failed files: {result.failure_count}")
    print(f"Duplicate files: {result.duplicate_count}")
    print(f"Sort requested: {_terminal_safe(result.sort.requested.value)}")
    print(f"Sort used: {_terminal_safe(result.sort.effective.value)}")
    print(f"Sort reason: {_terminal_safe(result.sort.reason)}")
    print(f"Sheets: {', '.join(_terminal_safe(sheet) for sheet in result.sheets)}")
    if mapping_set is not None:
        exact_count = sum(item.mapping_route == "EXACT_ADAPTER" for item in result.files)
        used_profiles = {
            item.mapping_profile_id
            for item in result.files
            if item.mapping_route == "USER_MAPPING_PROFILE" and item.mapping_profile_id is not None
        }
        unmapped_count = sum(item.mapping_route == "NO_MAPPING_MATCH" for item in result.files)
        print(f"Exact adapter routes: {exact_count}")
        print(f"Mapping profiles used: {len(used_profiles)}")
        print(f"Unmapped generic tables: {unmapped_count}")
    if result.sidecars:
        print("Sidecars:")
        for sidecar in result.sidecars:
            print(
                f"- {_terminal_safe(sidecar.relative_path)}: rows={sidecar.row_count}, "
                f"sha256={_terminal_safe(sidecar.sha256)}"
            )
    _print_file_warnings(result, verbose=args.verbose)
    _print_file_failures(result, verbose=args.verbose)
    if args.verbose:
        _print_batch_detection_evidence(result)
    if result.outcome is BatchOutcome.FAILED:
        return EXIT_FAILURE
    if result.outcome is BatchOutcome.PARTIAL_SUCCESS:
        return EXIT_PARTIAL_SUCCESS
    return EXIT_SUCCESS


def _run(args: argparse.Namespace) -> int:
    if args.command == "formats":
        return _run_formats()
    if args.command == "inspect":
        return _run_inspect(args)
    if args.command == "convert":
        return _run_convert(args)
    raise AssertionError(f"Unhandled command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return an automation-friendly exit code."""
    try:
        return _run(build_parser().parse_args(argv))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except Exception as error:
        code = getattr(error, "code", None)
        message = getattr(error, "message", None)
        if isinstance(code, str) and isinstance(message, str):
            print(
                f"Error [{_terminal_safe(code)}]: {_terminal_safe(message)}",
                file=sys.stderr,
            )
            if code == "OUTPUT_EXISTS":
                print(
                    "Hint: Re-run with --overwrite only if replacing that workbook is intended.",
                    file=sys.stderr,
                )
            details = getattr(error, "details", None)
            if isinstance(details, Mapping) and details:
                detail_text = ", ".join(
                    f"{_terminal_safe(key)}={_terminal_safe(value)}"
                    for key, value in details.items()
                )
                print(f"Details: {detail_text}", file=sys.stderr)
            if code in _CONFIGURATION_ERROR_CODES:
                return EXIT_USAGE
            return EXIT_FAILURE
        verbose = "--verbose" in (sys.argv[1:] if argv is None else argv)
        if verbose:
            print(
                f"Diagnostic type: {_terminal_safe(type(error).__name__)}",
                file=sys.stderr,
            )
        else:
            print(
                "Error [UNEXPECTED_ERROR]: An unexpected error occurred. "
                "Re-run with --verbose for diagnostics.",
                file=sys.stderr,
            )
        return EXIT_FAILURE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
