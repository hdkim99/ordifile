# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "standalone" / "windows_toolchain.ps1"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_windows_toolchain_active_path_is_authoritative_and_fully_probed() -> None:
    text = _script()
    assert 'Get-ToolCommand "cl.exe"' in text
    assert "if ($null -ne $activeCompiler)" in text
    assert 'Invoke-ToolchainProbe "prepare"' in text
    assert text.index("if ($null -ne $activeCompiler)") < text.index(
        "$activation = Get-RegisteredToolchain"
    )
    for tool in ("cl.exe", "link.exe", "dumpbin.exe", "rc.exe", "MSBuild.exe"):
        assert f'"{tool}"' in text
    assert "_MSC_VER < 1930" in text
    assert "!defined(_M_X64)" in text
    assert "#include <windows.h>" in text
    assert '"kernel32.lib"' in text
    assert "Test-PeMachineX64" in text
    assert "0x8664" in text
    assert "[AllowEmptyCollection()][string[]]$Arguments" in text
    assert "Invoke-NativeQuietly $executable @()" in text


def test_windows_toolchain_registered_route_is_exact_and_job_scoped() -> None:
    text = _script()
    assert '"Microsoft Visual Studio/Installer/vswhere.exe"' in text
    assert "Microsoft.VisualStudio.Component.VC.Tools.x86.x64" in text
    assert '-version "[17.0,18.0)"' in text
    assert 'Kind = "VsDevCmd"' in text
    assert '"Common7/Tools/VsDevCmd.bat"' in text
    assert 'Kind = "VcVars64"' in text
    assert '"VC/Auxiliary/Build/vcvars64.bat"' in text
    assert "-no_logo -arch=amd64 -host_arch=amd64" in text
    assert 'call "%ORDIFILE_VS_ACTIVATION%"' in text
    assert "[Environment]::SetEnvironmentVariable" in text
    assert "[IO.File]::AppendAllText" in text
    assert "Write-GitHubMask $value" in text
    assert 'Replace("%", "%25")' in text
    export = text.split("function Set-ActivatedEnvironment", 1)[1]
    assert export.index("Write-GitHubMask $value") < export.index("[IO.File]::AppendAllText")


def test_windows_toolchain_exports_only_the_reviewed_environment_allowlist() -> None:
    text = _script()
    block = text.split("    $allowed = [ordered]@{", 1)[1].split("    }", 1)[0]
    names = re.findall(r"^      ([A-Za-z0-9_]+) = \$null$", block, re.MULTILINE)
    assert names == [
        "Path",
        "INCLUDE",
        "LIB",
        "LIBPATH",
        "WindowsSdkDir",
        "WindowsSDKVersion",
        "UniversalCRTSdkDir",
        "UCRTVersion",
        "VCINSTALLDIR",
        "VCToolsInstallDir",
        "VSINSTALLDIR",
        "VSCMD_ARG_HOST_ARCH",
        "VSCMD_ARG_TGT_ARCH",
    ]
    assert "IndexOfAny([char[]]@([char]0, [char]10, [char]13))" in text
    assert '"GITHUB_' not in block
    assert '"RUNNER_' not in block


def test_windows_toolchain_probe_and_cleanup_are_bounded_and_fail_closed() -> None:
    text = _script()
    assert "ordifile-msvc-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT-" in text
    assert '$env:GITHUB_JOB -ne "windows-prototype"' in text
    assert "Test-OrdinaryDirectory" in text
    assert "Test-OrdinaryPathInsideRoot" in text
    assert "[IO.FileAttributes]::ReparsePoint" in text
    assert "PROBE_PARENT_INVALID" in text
    assert "PROBE_ROOT_OCCUPIED" in text
    assert "PROBE_OWNERSHIP_INVALID" in text
    assert "PROBE_CLEANUP_FAILED" in text
    assert "$Probe.Created = $true" in text
    assert "$Probe.Owned = $true" in text
    assert "$probe.Created -and -not $probe.Owned" in text
    assert ".ordifile-msvc-owned" in text
    assert "[IO.FileMode]::CreateNew" in text
    assert "ORDIFILE_MSVC_$($ProbeMode.ToUpperInvariant())_CLEANUP_TOKEN" in text
    assert "[IO.File]::ReadAllText($Probe.Marker" in text
    assert "Remove-Item -LiteralPath $Probe.Path -Recurse -Force" in text
    assert "Test-Path -LiteralPath $Probe.Path -ErrorAction Stop" in text


def test_windows_toolchain_uses_fixed_categories_without_host_mutation() -> None:
    text = _script()
    for category in (
        "ACTIVE_TOOLS_INCOMPLETE",
        "ACTIVE_PROBE_FAILED",
        "VSWHERE_UNAVAILABLE",
        "VSWHERE_QUERY_FAILED",
        "VS_INSTANCE_UNAVAILABLE",
        "ACTIVATION_SCRIPT_UNAVAILABLE",
        "ACTIVATION_FAILED",
        "ACTIVATED_ENV_INVALID",
        "ACTIVATED_PROBE_FAILED",
        "ENV_EXPORT_FAILED",
        "JOB_ENV_TOOLS_UNAVAILABLE",
        "PROBE_CLEANUP_FAILED",
    ):
        assert category in text
    assert "Windows native toolchain status: $category" in text
    for prohibited in (
        "Set-ExecutionPolicy",
        "Set-ItemProperty",
        "New-ItemProperty",
        "Start-Service",
        "Restart-Service",
        "sc.exe",
        "winget",
        "choco",
        "GITHUB_PATH",
        "Start-Process -Verb RunAs",
    ):
        assert prohibited not in text
