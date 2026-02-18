# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Launch HDR viewer with calibrated HDR files from validation output
# Enables visual spot evaluation of scenes which can be validated against reference luminance camera
# ==============================================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutputDir = Join-Path $ScriptDir "03_validation_output"
$HDRViewerPath = Join-Path $ScriptDir "..\..\00_Utilities\hdr_viewer.py"

if (-not (Test-Path $OutputDir)) {
    Write-Host "ERROR: Output directory not found: $OutputDir" -ForegroundColor Red
    Write-Host "Please ensure the validation script has been run and the output folder exists."
    exit 1
}

if (-not (Test-Path $HDRViewerPath)) {
    Write-Host "ERROR: HDR Viewer script not found: $HDRViewerPath" -ForegroundColor Red
    Write-Host "Please ensure the HDR Viewer script is located in the 00_Utilities folder."
    exit 1
}

$HDRFiles = Get-ChildItem -Path $OutputDir -Filter "*_calibrated.hdr" -Recurse -File

if ($HDRFiles.Count -eq 0) {
    Write-Host "ERROR: No calibrated HDR files found in $OutputDir" -ForegroundColor Red
    Write-Host "Please ensure the validation script has generated HDR files in the output folder."
    exit 1
}

$HDRFilePaths = ($HDRFiles.FullName | ForEach-Object { "`"$_`"" }) -join ' '
$PythonCmd = "python `"$HDRViewerPath`" $HDRFilePaths"

Write-Host "Launching HDR Viewer with $($HDRFiles.Count) calibrated HDR file(s):" -ForegroundColor Green
$HDRFiles | ForEach-Object { Write-Host "  - $($_.Name)" -ForegroundColor Cyan }
Write-Host ""
Write-Host "Command: $PythonCmd" -ForegroundColor DarkGray

Invoke-Expression $PythonCmd