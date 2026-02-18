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

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutputDir = Join-Path $ScriptDir "01_apply_calibration_output"
$HDRViewerPath = Join-Path $ScriptDir "..\..\00_Utilities\hdr_viewer.py"

if (-not (Test-Path $OutputDir)) {
    Write-Host "ERROR: Output directory not found: $OutputDir" -ForegroundColor Red
    Write-Host "Please ensure the calibration script has been run and the output folder exists."
    exit 1
}

if (-not (Test-Path $HDRViewerPath)) {
    Write-Host "ERROR: HDR Viewer script not found: $HDRViewerPath" -ForegroundColor Red
    Write-Host "Please ensure the HDR Viewer script is located in the 00_Utilities folder."
    exit 1
}

$HDRFiles = Get-ChildItem -Path $OutputDir -Filter "*.hdr"

if ($HDRFiles.Count -eq 0) {
    Write-Host "ERROR: No HDR files found in $OutputDir" -ForegroundColor Red
    Write-Host "Please ensure the calibration script has generated HDR files in the output folder."
    exit 1
}

$HDRFilePaths = $HDRFiles.FullName -join ' '
$PythonCmd = "python `"$HDRViewerPath`" $HDRFilePaths"

Write-Host "Launching HDR Viewer with the following files:" -ForegroundColor Green
$HDRFiles | ForEach-Object { Write-Host "  - $($_.Name)" -ForegroundColor Cyan }
Write-Host ""
Write-Host "Command: $PythonCmd" -ForegroundColor DarkGray

Invoke-Expression $PythonCmd