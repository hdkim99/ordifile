from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast


def test_distinct_curve_blocks_require_identical_header_and_original_lexemes() -> None:
    namespace = runpy.run_path(
        str(Path(__file__).parents[2] / "scripts/local/youngin_yl_clarity_prm_area_probe.py")
    )
    curve_block = cast(type[Any], namespace["_CurveBlock"])
    distinct = cast(
        Callable[[tuple[Any, ...]], tuple[Any, ...]],
        namespace["_distinct_curve_blocks"],
    )
    positive_zero = curve_block("Time [min]\tVoltage [mV]", (("0.00000", "0.0000"),))
    signed_zero = curve_block("Time [min]\tVoltage [mV]", (("0.00000", "-0.0000"),))
    other_unit = curve_block("Time [min]\tResponse [pA]", (("0.00000", "0.0000"),))

    assert distinct((positive_zero, positive_zero)) == (positive_zero,)
    assert distinct((positive_zero, signed_zero, other_unit)) == (
        positive_zero,
        signed_zero,
        other_unit,
    )
