# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("prepare", "verify")]
  [string]$Mode,

  [Parameter(Mandatory = $true)]
  [string]$EnvironmentFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:ToolchainFailure = $null

function Stop-Toolchain {
  param([Parameter(Mandatory = $true)][string]$Category)

  $script:ToolchainFailure = $Category
  throw "fixed-category"
}

function Test-OrdinaryFile {
  param([Parameter(Mandatory = $true)][string]$Path)

  try {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    return (
      $item -is [System.IO.FileInfo] -and
      -not $item.PSIsContainer -and
      -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
    )
  }
  catch {
    return $false
  }
}

function Write-GitHubMask {
  param([Parameter(Mandatory = $true)][string]$Value)

  $escaped = $Value.Replace("%", "%25").Replace("`r", "%0D").Replace("`n", "%0A")
  [Console]::WriteLine("::add-mask::$escaped")
}

function Test-OrdinaryDirectory {
  param(
    [Parameter(Mandatory = $true)][object]$Item,
    [Parameter(Mandatory = $true)][string]$ExpectedPath,
    [Parameter(Mandatory = $true)][string]$ExpectedParent
  )

  try {
    if (
      $null -eq $Item -or
      -not ($Item -is [System.IO.DirectoryInfo]) -or
      -not $Item.PSIsContainer -or
      ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)
    ) {
      return $false
    }
    $actual = [IO.Path]::GetFullPath($Item.FullName)
    $parent = [IO.Path]::GetFullPath($Item.Parent.FullName)
    return (
      $actual.Equals($ExpectedPath, [StringComparison]::OrdinalIgnoreCase) -and
      $parent.Equals($ExpectedParent, [StringComparison]::OrdinalIgnoreCase)
    )
  }
  catch {
    return $false
  }
}

function Test-OrdinaryPathInsideRoot {
  param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][bool]$LeafIsDirectory
  )

  try {
    $rootPath = [IO.Path]::GetFullPath($Root)
    $pathValue = [IO.Path]::GetFullPath($Path)
    $trimCharacters = [char[]]@(
      [IO.Path]::DirectorySeparatorChar,
      [IO.Path]::AltDirectorySeparatorChar
    )
    $boundary = $rootPath.TrimEnd($trimCharacters) + [IO.Path]::DirectorySeparatorChar
    if (-not $pathValue.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) {
      return $false
    }
    $relative = $pathValue.Substring($boundary.Length)
    $parts = @($relative -split '[\\/]' | Where-Object { $_ })
    if ($parts.Count -eq 0) {
      return $false
    }
    $current = $rootPath
    for ($index = 0; $index -lt $parts.Count; $index += 1) {
      $current = Join-Path $current $parts[$index]
      $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
      $isLeaf = $index -eq $parts.Count - 1
      if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        return $false
      }
      if ($isLeaf) {
        return $LeafIsDirectory -eq $item.PSIsContainer
      }
      if (-not $item.PSIsContainer) {
        return $false
      }
    }
    return $false
  }
  catch {
    return $false
  }
}

function Get-ToolCommand {
  param([Parameter(Mandatory = $true)][string]$Name)

  try {
    $commands = @(Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue)
  }
  catch {
    Stop-Toolchain "TOOL_DISCOVERY_FAILED"
  }
  if ($commands.Count -eq 0) {
    return $null
  }
  if ($commands.Count -ne 1 -or -not (Test-OrdinaryFile $commands[0].Source)) {
    Stop-Toolchain "TOOL_DISCOVERY_FAILED"
  }
  return $commands[0]
}

function Initialize-ProbeRoot {
  param(
    [Parameter(Mandatory = $true)][object]$Probe,
    [Parameter(Mandatory = $true)][string]$ProbeMode,
    [Parameter(Mandatory = $true)][string]$CleanupEnvironmentFile
  )

  if (
    [string]::IsNullOrWhiteSpace($env:RUNNER_TEMP) -or
    $env:GITHUB_RUN_ID -notmatch '^[0-9]+$' -or
    $env:GITHUB_RUN_ATTEMPT -notmatch '^[0-9]+$' -or
    $env:GITHUB_JOB -ne "windows-prototype" -or
    $ProbeMode -notmatch '^(prepare|verify)$'
  ) {
    Stop-Toolchain "PROBE_IDENTITY_INVALID"
  }

  try {
    $rootParent = [IO.Path]::GetFullPath($env:RUNNER_TEMP)
    $parentItem = Get-Item -LiteralPath $rootParent -Force -ErrorAction Stop
    if (
      -not ($parentItem -is [System.IO.DirectoryInfo]) -or
      -not $parentItem.PSIsContainer -or
      ($parentItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
      -not ([IO.Path]::GetFullPath($parentItem.FullName)).Equals(
        $rootParent,
        [StringComparison]::OrdinalIgnoreCase
      )
    ) {
      Stop-Toolchain "PROBE_PARENT_INVALID"
    }
    $probeName = (
      "ordifile-msvc-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT-" +
        "$env:GITHUB_JOB-$ProbeMode"
    )
    $rootPath = [IO.Path]::GetFullPath((Join-Path $rootParent $probeName))
    $trimCharacters = [char[]]@(
      [IO.Path]::DirectorySeparatorChar,
      [IO.Path]::AltDirectorySeparatorChar
    )
    $boundary =
      $rootParent.TrimEnd($trimCharacters) + [IO.Path]::DirectorySeparatorChar
    if (-not $rootPath.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) {
      Stop-Toolchain "PROBE_IDENTITY_INVALID"
    }
    if (Test-Path -LiteralPath $rootPath -ErrorAction Stop) {
      Stop-Toolchain "PROBE_ROOT_OCCUPIED"
    }
    $Probe.Parent = $rootParent
    $Probe.Path = $rootPath
    $created = New-Item -ItemType Directory -Path $rootPath -ErrorAction Stop
    $Probe.Created = $true
    if (-not (Test-OrdinaryDirectory $created $rootPath $rootParent)) {
      Stop-Toolchain "PROBE_OWNERSHIP_INVALID"
    }
    $token = [Guid]::NewGuid().ToString("N")
    $marker = Join-Path $rootPath ".ordifile-msvc-owned"
    $markerBytes = [Text.UTF8Encoding]::new($false).GetBytes($token)
    $stream = [IO.File]::Open(
      $marker,
      [IO.FileMode]::CreateNew,
      [IO.FileAccess]::Write,
      [IO.FileShare]::None
    )
    try {
      $stream.Write($markerBytes, 0, $markerBytes.Length)
    }
    finally {
      $stream.Dispose()
    }
    if (
      -not (Test-OrdinaryFile $marker) -or
      [IO.File]::ReadAllText($marker, [Text.Encoding]::UTF8) -cne $token
    ) {
      Stop-Toolchain "PROBE_MARKER_FAILED"
    }
    if ([string]::IsNullOrWhiteSpace($CleanupEnvironmentFile)) {
      Stop-Toolchain "PROBE_MARKER_FAILED"
    }
    Write-GitHubMask $token
    $tokenName = "ORDIFILE_MSVC_$($ProbeMode.ToUpperInvariant())_CLEANUP_TOKEN"
    [IO.File]::AppendAllText(
      $CleanupEnvironmentFile,
      "$tokenName=$token$([Environment]::NewLine)",
      [Text.UTF8Encoding]::new($false)
    )
    $Probe.Marker = $marker
    $Probe.Token = $token
    $Probe.Owned = $true
  }
  catch {
    if ($script:ToolchainFailure) {
      throw
    }
    Stop-Toolchain "PROBE_SETUP_FAILED"
  }
}

function Remove-ProbeRoot {
  param([Parameter(Mandatory = $true)][object]$Probe)

  try {
    $item = Get-Item -LiteralPath $Probe.Path -Force -ErrorAction Stop
    if (
      -not (Test-OrdinaryDirectory $item $Probe.Path $Probe.Parent) -or
      -not (Test-OrdinaryFile $Probe.Marker) -or
      [IO.File]::ReadAllText($Probe.Marker, [Text.Encoding]::UTF8) -cne $Probe.Token
    ) {
      Stop-Toolchain "PROBE_CLEANUP_FAILED"
    }
    Remove-Item -LiteralPath $Probe.Path -Recurse -Force -ErrorAction Stop *> $null
    if (Test-Path -LiteralPath $Probe.Path -ErrorAction Stop) {
      Stop-Toolchain "PROBE_CLEANUP_FAILED"
    }
  }
  catch {
    if ($script:ToolchainFailure -eq "PROBE_CLEANUP_FAILED") {
      throw
    }
    Stop-Toolchain "PROBE_CLEANUP_FAILED"
  }
}

function Invoke-NativeQuietly {
  param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Arguments
  )

  try {
    & $Executable @Arguments *> $null
    return $LASTEXITCODE
  }
  catch {
    return -1
  }
}

function Test-PeMachineX64 {
  param([Parameter(Mandatory = $true)][string]$Path)

  try {
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 64 -or $bytes[0] -ne 0x4d -or $bytes[1] -ne 0x5a) {
      return $false
    }
    $peOffset = [BitConverter]::ToInt32($bytes, 0x3c)
    if ($peOffset -lt 0 -or $peOffset + 6 -gt $bytes.Length) {
      return $false
    }
    if (
      $bytes[$peOffset] -ne 0x50 -or
      $bytes[$peOffset + 1] -ne 0x45 -or
      $bytes[$peOffset + 2] -ne 0x00 -or
      $bytes[$peOffset + 3] -ne 0x00
    ) {
      return $false
    }
    return [BitConverter]::ToUInt16($bytes, $peOffset + 4) -eq 0x8664
  }
  catch {
    return $false
  }
}

function Invoke-ToolchainProbe {
  param(
    [Parameter(Mandatory = $true)][string]$ProbeMode,
    [Parameter(Mandatory = $true)][string]$CleanupEnvironmentFile
  )

  $tools = @{}
  foreach ($name in @("cl.exe", "link.exe", "dumpbin.exe", "rc.exe", "MSBuild.exe")) {
    $tool = Get-ToolCommand $name
    if ($null -eq $tool) {
      Stop-Toolchain "ACTIVE_TOOLS_INCOMPLETE"
    }
    $tools[$name] = $tool.Source
  }

  $probe = [PSCustomObject]@{
    Parent = $null
    Path = $null
    Created = $false
    Owned = $false
    Marker = $null
    Token = $null
  }
  try {
    Initialize-ProbeRoot $probe $ProbeMode $CleanupEnvironmentFile
    $current = Get-Item -LiteralPath $probe.Path -Force -ErrorAction Stop
    if (-not (Test-OrdinaryDirectory $current $probe.Path $probe.Parent)) {
      Stop-Toolchain "PROBE_OWNERSHIP_INVALID"
    }

    $source = Join-Path $probe.Path "probe.c"
    $resourceSource = Join-Path $probe.Path "probe.rc"
    $object = Join-Path $probe.Path "probe.obj"
    $resource = Join-Path $probe.Path "probe.res"
    $executable = Join-Path $probe.Path "probe.exe"
    [IO.File]::WriteAllText(
      $source,
      "#include <windows.h>`n" +
        "#if !defined(_MSC_VER) || _MSC_VER < 1930`n" +
        "#error unsupported compiler`n#endif`n" +
        "#if !defined(_M_X64)`n#error unsupported architecture`n#endif`n" +
        "int main(void) { return GetCurrentProcessId() == 0; }`n",
      [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
      $resourceSource,
      "1 RCDATA { 0 }`n",
      [Text.ASCIIEncoding]::new()
    )

    if ((Invoke-NativeQuietly $tools["cl.exe"] @(
      "/nologo", "/c", "/TC", $source, "/Fo$object"
    )) -ne 0) {
      Stop-Toolchain "ACTIVE_PROBE_FAILED"
    }
    if ((Invoke-NativeQuietly $tools["rc.exe"] @(
      "/nologo", "/fo", $resource, $resourceSource
    )) -ne 0) {
      Stop-Toolchain "ACTIVE_PROBE_FAILED"
    }
    if ((Invoke-NativeQuietly $tools["link.exe"] @(
      "/nologo", "/machine:x64", "/subsystem:console", "/out:$executable",
      $object, $resource, "kernel32.lib"
    )) -ne 0) {
      Stop-Toolchain "ACTIVE_PROBE_FAILED"
    }
    if (
      -not (Test-OrdinaryFile $executable) -or
      -not (Test-PeMachineX64 $executable) -or
      (Invoke-NativeQuietly $tools["dumpbin.exe"] @("/headers", $executable)) -ne 0 -or
      (Invoke-NativeQuietly $tools["MSBuild.exe"] @("-version", "-nologo")) -ne 0 -or
      (Invoke-NativeQuietly $executable @()) -ne 0
    ) {
      Stop-Toolchain "ACTIVE_PROBE_FAILED"
    }
  }
  catch {
    if (-not $script:ToolchainFailure) {
      $script:ToolchainFailure = "ACTIVE_PROBE_FAILED"
    }
  }
  finally {
    if ($probe.Created -and -not $probe.Owned) {
      $script:ToolchainFailure = "PROBE_CLEANUP_FAILED"
    }
    elseif ($probe.Owned) {
      try {
        Remove-ProbeRoot $probe
      }
      catch {
        $script:ToolchainFailure = "PROBE_CLEANUP_FAILED"
      }
    }
  }
  if ($script:ToolchainFailure) {
    throw "fixed-category"
  }
}

function Get-RegisteredToolchain {
  try {
    $programFilesX86 = [Environment]::GetFolderPath("ProgramFilesX86")
    if ([string]::IsNullOrWhiteSpace($programFilesX86)) {
      Stop-Toolchain "VSWHERE_UNAVAILABLE"
    }
    $vswhere = Join-Path $programFilesX86 "Microsoft Visual Studio/Installer/vswhere.exe"
    if (-not (Test-OrdinaryFile $vswhere)) {
      Stop-Toolchain "VSWHERE_UNAVAILABLE"
    }
    $installations = @(
      & $vswhere -latest -products '*' `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -version "[17.0,18.0)" -property installationPath 2>$null |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    if ($LASTEXITCODE -ne 0) {
      Stop-Toolchain "VSWHERE_QUERY_FAILED"
    }
    if ($installations.Count -ne 1) {
      Stop-Toolchain "VS_INSTANCE_UNAVAILABLE"
    }

    $installation = [IO.Path]::GetFullPath($installations[0].Trim())
    $installationItem = Get-Item -LiteralPath $installation -Force -ErrorAction Stop
    if (
      -not (Test-OrdinaryDirectory `
        $installationItem `
        $installation `
        ([IO.Path]::GetFullPath($installationItem.Parent.FullName)))
    ) {
      Stop-Toolchain "VS_INSTANCE_INVALID"
    }
    $trimCharacters = [char[]]@(
      [IO.Path]::DirectorySeparatorChar,
      [IO.Path]::AltDirectorySeparatorChar
    )
    $boundary =
      $installation.TrimEnd($trimCharacters) + [IO.Path]::DirectorySeparatorChar

    $candidates = @(
      [PSCustomObject]@{
        Kind = "VsDevCmd"
        Path = Join-Path $installation "Common7/Tools/VsDevCmd.bat"
      },
      [PSCustomObject]@{
        Kind = "VcVars64"
        Path = Join-Path $installation "VC/Auxiliary/Build/vcvars64.bat"
      }
    )
    foreach ($candidate in $candidates) {
      $candidatePath = [IO.Path]::GetFullPath($candidate.Path)
      if (Test-OrdinaryPathInsideRoot $installation $candidatePath $false) {
        return [PSCustomObject]@{
          Kind = $candidate.Kind
          Path = $candidatePath
        }
      }
    }
    Stop-Toolchain "ACTIVATION_SCRIPT_UNAVAILABLE"
  }
  catch {
    if ($script:ToolchainFailure) {
      throw
    }
    Stop-Toolchain "VSWHERE_QUERY_FAILED"
  }
}

function Get-ActivatedEnvironment {
  param([Parameter(Mandatory = $true)][object]$Activation)

  try {
    $command = if ($Activation.Kind -eq "VsDevCmd") {
      'call "%ORDIFILE_VS_ACTIVATION%" -no_logo -arch=amd64 -host_arch=amd64 >nul 2>nul && set'
    }
    else {
      'call "%ORDIFILE_VS_ACTIVATION%" >nul 2>nul && set'
    }
    $start = [Diagnostics.ProcessStartInfo]::new()
    $commandProcessor = Get-ToolCommand "cmd.exe"
    if ($null -eq $commandProcessor) {
      Stop-Toolchain "ACTIVATION_FAILED"
    }
    $start.FileName = $commandProcessor.Source
    $start.Arguments = "/u /d /c $command"
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardOutputEncoding = [Text.Encoding]::Unicode
    $start.Environment["ORDIFILE_VS_ACTIVATION"] = $Activation.Path
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) {
      Stop-Toolchain "ACTIVATION_FAILED"
    }
    $output = $process.StandardOutput.ReadToEnd()
    $null = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0 -or $output.Length -gt 1048576) {
      Stop-Toolchain "ACTIVATION_FAILED"
    }

    $allowed = [ordered]@{
      Path = $null
      INCLUDE = $null
      LIB = $null
      LIBPATH = $null
      WindowsSdkDir = $null
      WindowsSDKVersion = $null
      UniversalCRTSdkDir = $null
      UCRTVersion = $null
      VCINSTALLDIR = $null
      VCToolsInstallDir = $null
      VSINSTALLDIR = $null
      VSCMD_ARG_HOST_ARCH = $null
      VSCMD_ARG_TGT_ARCH = $null
    }
    $canonical = @{}
    foreach ($name in $allowed.Keys) {
      $canonical[$name.ToUpperInvariant()] = $name
    }
    foreach ($line in ($output -split '\r?\n')) {
      if ([string]::IsNullOrEmpty($line)) {
        continue
      }
      $separator = $line.IndexOf("=")
      if ($separator -lt 1) {
        continue
      }
      $name = $line.Substring(0, $separator)
      $key = $name.ToUpperInvariant()
      if ($canonical.ContainsKey($key)) {
        $value = $line.Substring($separator + 1)
        if (
          [string]::IsNullOrWhiteSpace($value) -or
          $value.IndexOfAny([char[]]@([char]0, [char]10, [char]13)) -ge 0
        ) {
          Stop-Toolchain "ACTIVATED_ENV_INVALID"
        }
        $allowed[$canonical[$key]] = $value
      }
    }
    foreach ($required in @(
      "Path", "INCLUDE", "LIB", "LIBPATH", "WindowsSdkDir", "WindowsSDKVersion",
      "UniversalCRTSdkDir", "UCRTVersion", "VCINSTALLDIR", "VCToolsInstallDir",
      "VSINSTALLDIR", "VSCMD_ARG_HOST_ARCH", "VSCMD_ARG_TGT_ARCH"
    )) {
      if ([string]::IsNullOrWhiteSpace($allowed[$required])) {
        Stop-Toolchain "ACTIVATED_ENV_INVALID"
      }
    }
    if (
      $allowed["VSCMD_ARG_HOST_ARCH"] -notmatch '^(x64|amd64)$' -or
      $allowed["VSCMD_ARG_TGT_ARCH"] -notmatch '^(x64|amd64)$'
    ) {
      Stop-Toolchain "ACTIVATED_ENV_INVALID"
    }
    return $allowed
  }
  catch {
    if ($script:ToolchainFailure) {
      throw
    }
    Stop-Toolchain "ACTIVATION_FAILED"
  }
}

function Set-ActivatedEnvironment {
  param(
    [Parameter(Mandatory = $true)][object]$Variables,
    [Parameter(Mandatory = $true)][string]$Destination
  )

  try {
    if ([string]::IsNullOrWhiteSpace($Destination)) {
      Stop-Toolchain "ENV_EXPORT_FAILED"
    }
    $lines = [Collections.Generic.List[string]]::new()
    foreach ($name in $Variables.Keys) {
      $value = [string]$Variables[$name]
      Write-GitHubMask $value
      if ($name -in @("Path", "INCLUDE", "LIB", "LIBPATH")) {
        foreach ($part in ($value -split ";")) {
          if (-not [string]::IsNullOrWhiteSpace($part)) {
            Write-GitHubMask $part
          }
        }
      }
      [Environment]::SetEnvironmentVariable($name, $value, "Process")
      $lines.Add("$name=$value")
    }
    [IO.File]::AppendAllText(
      $Destination,
      (($lines -join [Environment]::NewLine) + [Environment]::NewLine),
      [Text.UTF8Encoding]::new($false)
    )
  }
  catch {
    if ($script:ToolchainFailure) {
      throw
    }
    Stop-Toolchain "ENV_EXPORT_FAILED"
  }
}

try {
  $activeCompiler = Get-ToolCommand "cl.exe"
  if ($Mode -eq "verify") {
    if ($null -eq $activeCompiler) {
      Stop-Toolchain "JOB_ENV_TOOLS_UNAVAILABLE"
    }
    Invoke-ToolchainProbe "verify" $EnvironmentFile
    [Console]::WriteLine("Windows native toolchain status: READY_JOB_ENV")
    exit 0
  }

  if ($null -ne $activeCompiler) {
    Invoke-ToolchainProbe "prepare" $EnvironmentFile
    [Console]::WriteLine("Windows native toolchain status: READY_ACTIVE")
    exit 0
  }

  $activation = Get-RegisteredToolchain
  $variables = Get-ActivatedEnvironment $activation
  foreach ($name in $variables.Keys) {
    [Environment]::SetEnvironmentVariable($name, [string]$variables[$name], "Process")
  }
  try {
    Invoke-ToolchainProbe "prepare" $EnvironmentFile
  }
  catch {
    if ($script:ToolchainFailure -ne "PROBE_CLEANUP_FAILED") {
      $script:ToolchainFailure = "ACTIVATED_PROBE_FAILED"
    }
    throw
  }
  Set-ActivatedEnvironment $variables $EnvironmentFile
  [Console]::WriteLine("Windows native toolchain status: READY_ACTIVATED")
  exit 0
}
catch {
  $category = $script:ToolchainFailure
  if ([string]::IsNullOrWhiteSpace($category)) {
    $category = "TOOLCHAIN_PREFLIGHT_FAILED"
  }
  [Console]::Error.WriteLine("Windows native toolchain status: $category")
  exit 1
}
