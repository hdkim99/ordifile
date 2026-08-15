#!/usr/bin/env bash
# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

repository_root="$(cd "$(dirname "$0")/.." && pwd)"
output_dir="$repository_root/docs/assets"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

python_command="${PYTHON_COMMAND:-python3}"
demo_dir="$work_dir/demo"
venv_dir="$work_dir/venv"

mkdir -p "$demo_dir/exports" "$output_dir"
cp "$repository_root"/examples/basic/*.csv "$demo_dir/exports/"

"$python_command" -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --disable-pip-version-check --quiet \
  "$repository_root"

(
  cd "$demo_dir"
  {
    printf '$ ls exports\n'
    find exports -maxdepth 1 -type f -print | LC_ALL=C sort
    printf '\n$ ordifile convert exports --sort filename --output Ordifile_Result.xlsx\n'
  } > transcript.txt
  "$venv_dir/bin/ordifile" convert exports --sort filename \
    --output Ordifile_Result.xlsx >> transcript.txt
)

"$venv_dir/bin/python" - "$demo_dir/Ordifile_Result.xlsx" \
  "$demo_dir/workbook.json" <<'PY'
import json
import sys
from pathlib import Path

from openpyxl import load_workbook

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
workbook = load_workbook(source, read_only=True, data_only=False)
try:
    payload = {
        "sheet_names": workbook.sheetnames,
        "samples": [
            ["" if value is None else str(value) for value in row]
            for row in workbook["Samples"].iter_rows(min_row=1, max_row=4, values_only=True)
        ],
        "peak_matrix": [
            ["" if value is None else str(value) for value in row]
            for row in workbook["Peak_Matrix"].iter_rows(
                min_row=1,
                max_row=4,
                max_col=5,
                values_only=True,
            )
        ],
    }
finally:
    workbook.close()
destination.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
PY

/usr/bin/swift "$repository_root/scripts/render_demo_assets.swift" \
  "$demo_dir/transcript.txt" "$demo_dir/workbook.json" "$output_dir"

printf 'Generated:\n'
printf '  %s\n' \
  "$output_dir/ordifile-demo.gif" \
  "$output_dir/ordifile-workbook.png" \
  "$output_dir/ordifile-social-preview.png"
