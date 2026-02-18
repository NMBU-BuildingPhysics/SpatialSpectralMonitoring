# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# HDR Viewer: Open HDR Viewer with HDR files from the local output folder
# This script launches the HDR Viewer with all HDR files
# ==============================================================================

<#
.SYNOPSIS
    Open HDR Viewer with HDR files from the 05_correct_vignetting_output and 03_generate_hdr_output folders.

.DESCRIPTION
    This script launches the HDR Viewer (`hdr_viewer.py`) with all HDR files
    located in the `05_correct_vignetting_output` and `03_generate_hdr_output` folders
    within the `04_Camera_Characterization` directory.

.EXAMPLE
    .\06_open_HDR_files.ps1
    # Opens the HDR Viewer with all HDR files in the specified folders.
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VignettingOutputDir = Join-Path $ScriptDir "05_correct_vignetting_output"
$GenerateHDROutputDir = Join-Path $ScriptDir "03_generate_hdr_output"
$HDRViewerPath = Join-Path $ScriptDir "..\..\00_Utilities\hdr_viewer.py"

if (-not (Test-Path $VignettingOutputDir)) {
    Write-Host "ERROR: Vignetting output directory not found: $VignettingOutputDir" -ForegroundColor Red
    Write-Host "Please ensure the vignetting correction script has been run and the output folder exists."
    exit 1
}

if (-not (Test-Path $GenerateHDROutputDir)) {
    Write-Host "ERROR: HDR generation output directory not found: $GenerateHDROutputDir" -ForegroundColor Red
    Write-Host "Please ensure the HDR generation script has been run and the output folder exists."
    exit 1
}

if (-not (Test-Path $HDRViewerPath)) {
    Write-Host "ERROR: HDR Viewer script not found: $HDRViewerPath" -ForegroundColor Red
    Write-Host "Please ensure the HDR Viewer script is located in the 00_Utilities folder."
    exit 1
}

$VignettingHDRFiles = Get-ChildItem -Path $VignettingOutputDir -Filter "*.hdr"
$GenerateHDRFiles = Get-ChildItem -Path $GenerateHDROutputDir -Filter "*.hdr"

$AllHDRFiles = @($VignettingHDRFiles) + @($GenerateHDRFiles)

if ($AllHDRFiles.Count -eq 0) {
    Write-Host "ERROR: No HDR files found in the specified directories." -ForegroundColor Red
    Write-Host "Please ensure the scripts have generated HDR files in the output folders."
    exit 1
}

$HDRFilePaths = $AllHDRFiles.FullName -join ' '
$PythonCmd = "python `"$HDRViewerPath`" $HDRFilePaths"

Write-Host "Launching HDR Viewer with the following files:" -ForegroundColor Green
$AllHDRFiles | ForEach-Object { Write-Host "  - $($_.Name)" -ForegroundColor Cyan }
Write-Host ""
Write-Host "Command: $PythonCmd" -ForegroundColor DarkGray

Invoke-Expression $PythonCmd