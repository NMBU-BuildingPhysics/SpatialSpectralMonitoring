<#
 .SYNOPSIS
   Generates 02_Firmware/Main/version.h from the current Git state.

 .DESCRIPTION
   Run this script before building to stamp the firmware with the exact
   Git version (tag + commit hash + dirty flag).

   Tagging convention:
     git tag -a v1.0.0 -m "Release 1.0.0"

   git describe output examples:
     v1.0.0                       clean commit that is exactly a tag
     v1.0.0-5-gdef1234            5 commits after v1.0.0
     v1.0.0-5-gdef1234-dirty      uncommitted changes present
     e6c1c27-dirty                no tags yet (hash only)

 .USAGE
   From the repo root:
     powershell -ExecutionPolicy Bypass -File 02_Firmware/generate_version.ps1
#>

$ErrorActionPreference = "Stop"

# Resolve paths relative to this script's location (02_Firmware/)
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = Split-Path -Parent $ScriptDir
$VersionFile = Join-Path $ScriptDir "Main\version.h"

# Get version string from Git
try {
    $GitVersion = & git -C $RepoRoot describe --tags --always --dirty 2>&1
    if ($LASTEXITCODE -ne 0) { throw "git describe failed" }
    $GitVersion = $GitVersion.Trim()
} catch {
    Write-Warning "Could not run git describe: $_"
    $GitVersion = "unknown"
}

Write-Host "Firmware version: $GitVersion"

# Write version.h
$Content = @"
/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* Powershell -ExecutionPolicy Bypass -File 02_Firmware/generate_version.ps1
*/

#pragma once

#define FIRMWARE_VERSION "$GitVersion"
"@

# Use ASCII encoding — content is pure ASCII and avoids the UTF-8 BOM
# that PowerShell 5.1's -Encoding UTF8 prepends (BOM breaks C++ #include).
Set-Content -Path $VersionFile -Value $Content -Encoding ASCII
Write-Host "Written: $VersionFile"
