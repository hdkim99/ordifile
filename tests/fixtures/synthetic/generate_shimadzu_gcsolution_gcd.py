# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate an invented structural GCD profile without proprietary byte slices."""

from __future__ import annotations

import struct
from collections.abc import Mapping
from pathlib import Path

from generate_cfb_v4 import SECTOR_BYTES, build_cfb_v4

_DEFAULT_VALUES = tuple(-10.0 + item / 4 for item in range(512))


def _stox(value: str) -> str:
    return "@StoX@" + value.encode("ascii").hex().upper()


def _f64_hex(value: float) -> str:
    return struct.pack("<d", value).hex().upper()


def _regular_text_stream(data: bytes, *, unit: bytes) -> bytes:
    if len(data) >= SECTOR_BYTES:
        return data
    remaining = SECTOR_BYTES - len(data)
    return data + unit * (remaining // len(unit))


def synthetic_gcd_streams(
    *,
    software_version: str = "5.82",
    file_schema: str = "5.01",
    sample_name: str = "synthetic_sample",
    sample_id: str = "SYN-001",
    operator_name: str = "synthetic_operator",
    injection_volume_raw: str = "@FtoX@1",
    unit: str = "uV",
    axis_factor: float = 1.0,
    correction_factor: float = 1.0,
    gain_factor: float = 1.0,
    interval_ms: int = 40,
    acquisition_time_ms: float | None = None,
    delay_ms: float = 20.0,
    data_source_id: str = "GC.1.1.DET.1.DetCh",
    data_source_name: str = "SFID1",
    user_data_source_name: str = "SFID1",
    analysis_trace_name: str = "[Chromatogram (Ch1)]",
    values: tuple[float, ...] = _DEFAULT_VALUES,
    encoded_point_count: int | None = None,
    encoded_signal_length: int | None = None,
    signal_magic: int = 17_234,
    signal_interval_ms: int | None = None,
    system_root_version: str = "1.0",
    instrument_model: str = "GC-2014",
    extra_ch2_values: tuple[float, ...] | None = None,
    path_replacements: Mapping[tuple[str, ...], tuple[str, ...]] | None = None,
) -> dict[tuple[str, ...], bytes]:
    """Return invented streams for the exact validated structural profile."""
    point_count = len(values) if encoded_point_count is None else encoded_point_count
    acquisition = (
        float(len(values) * interval_ms) if acquisition_time_ms is None else acquisition_time_ms
    )
    file_property = b"\x01\x02\x03\x04" + (
        f"<FileProperty><szVersion>{_stox(file_schema)}</szVersion></FileProperty>"
        f"<SampleInfo><smpl_name>{_stox(sample_name)}</smpl_name>"
        f"<smpl_id>{_stox(sample_id)}</smpl_id>"
        f"<operator_name>{_stox(operator_name)}</operator_name>"
        f"<inj_vol>{injection_volume_raw}</inj_vol>"
        "<dwLowDateTime>1988739072</dwLowDateTime>"
        "<dwHighDateTime>31079493</dwHighDateTime></SampleInfo>"
    ).encode("ascii")
    file_property = _regular_text_stream(file_property, unit=b" ")
    system_check = (
        f'<SystemCheckResult version="{system_root_version}"><Summary>'
        f"<Performer>{operator_name}</Performer>"
        '<DateTime Bias="0">133485408000000000</DateTime>'
        f"<SWVersion>{software_version}</SWVersion>"
        "</Summary><Result/></SystemCheckResult>"
    ).encode()
    system_check = _regular_text_stream(system_check, unit=b" ")
    system_information = (
        f'<GUD Type="SI"><IN>{instrument_model}</IN><IC>2</IC><Cmt></Cmt><II>1</II>'
        f'<SGLI Name="GC" Idx="1"><U>{instrument_model}</U>'
        f'<GUM IT="{instrument_model}"></GUM>'
        "</SGLI></GUD>"
    ).encode("utf-16-le")
    system_information = _regular_text_stream(system_information, unit=b" \x00")
    data_item_text = (
        '<GUD Type="2DDataItem" Rev="0" RevSrc="0">'
        '<DII Rev="0" RevSrc="0"><DT>18</DT><DK>0</DK><LN>1</LN><CN>1</CN>'
        "<CCID>1</CCID><DDI>"
        '<Axis ID="0" DUS="1"><Rng><Min>0000000000000000</Min>'
        "<Max>0000000000000000</Max><Step>000000000000F03F</Step></Rng>"
        f'<US ID="1"><VF>{_f64_hex(axis_factor)}</VF><Unit>{unit}</Unit><UT>0</UT></US>'
        f'<US ID="2"><VF>{_f64_hex(1000.0)}</VF><Unit>mV</Unit><UT>0</UT></US>'
        f'<US ID="3"><VF>{_f64_hex(1_000_000.0)}</VF><Unit>V</Unit><UT>0</UT></US>'
        "</Axis>"
        '<Axis ID="1" DUS="0"><Rng><Min>0000000000000000</Min>'
        f"<Max>{_f64_hex(acquisition / 60000.0)}</Max>"
        f"<Step>{_f64_hex(float(interval_ms))}</Step></Rng></Axis>"
        '<Axis ID="2" DUS="0"><Rng><Min>0000000000000000</Min>'
        "<Max>0000000000000000</Max><Step>0000000000000000</Step></Rng></Axis>"
        "</DDI>"
        f"<CF>{_f64_hex(correction_factor)}</CF><GF>{_f64_hex(gain_factor)}</GF>"
        f"<Rate>{interval_ms}</Rate><AT>{_f64_hex(acquisition)}</AT>"
        f"<DLT>{_f64_hex(delay_ms)}</DLT><DSID>{data_source_id}</DSID>"
        f"<DSCN></DSCN><UDDSN>{user_data_source_name}</UDDSN><ADN></ADN>"
        f"<DNRID>1</DNRID><DN>Det#1</DN><DSN>{data_source_name}</DSN>"
        f"<RDC>1</RDC><DETN>DET#1</DETN><LKID>0</LKID><CHN></CHN>"
        f"<ATN>{analysis_trace_name}</ATN><SPR/></DII><SPR/></GUD>"
    )
    data_item = _regular_text_stream(data_item_text.encode("utf-16-le"), unit=b" \x00")
    signal = struct.pack(
        "<6I",
        signal_magic,
        interval_ms if signal_interval_ms is None else signal_interval_ms,
        point_count,
        len(values) * 8 + 5 if encoded_signal_length is None else encoded_signal_length,
        0,
        0,
    ) + struct.pack(f"<{len(values)}d", *values)
    streams: dict[tuple[str, ...], bytes] = {
        ("File Property",): file_property,
        ("SystemCheckResult", "SystemCheckResult"): system_check,
        ("GUMM_Information", "GUMMSubStg", "SystemInformation"): system_information,
        ("LSS Raw Data", "2D Data Item U"): data_item,
        ("LSS Raw Data", "Chromatogram Ch1"): signal,
    }
    if extra_ch2_values is not None:
        ch2 = struct.pack(
            "<6I",
            signal_magic,
            interval_ms,
            len(extra_ch2_values),
            len(extra_ch2_values) * 8 + 5,
            0,
            0,
        ) + struct.pack(f"<{len(extra_ch2_values)}d", *extra_ch2_values)
        streams[("LSS Raw Data", "Chromatogram Ch2")] = ch2
    for old, new in (path_replacements or {}).items():
        streams[new] = streams.pop(old)
    return streams


def synthetic_gcd_bytes(**kwargs: object) -> bytes:
    """Return one deterministic invented compound document."""
    return build_cfb_v4(synthetic_gcd_streams(**kwargs))  # type: ignore[arg-type]


def write_synthetic_gcd(path: Path, **kwargs: object) -> Path:
    """Write one invented structural fixture and return its path."""
    path.write_bytes(synthetic_gcd_bytes(**kwargs))
    return path
