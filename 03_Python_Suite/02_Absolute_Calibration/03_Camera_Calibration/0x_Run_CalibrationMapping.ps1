# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Map calibrated points: Helper script to run calibration point mapping using files from local input
# Runs the 04_map_cal_points.py from the characterization workflow
# ==============================================================================

param(
    [string]$SensorId = "sensor11",
    [string]$CsvFile = ""
)

function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Error { Write-Host $args -ForegroundColor Red }

Write-Host ""
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "CALIBRATION POINT MAPPING HELPER" -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalInputDir = Join-Path $ScriptDir "01_apply_calibration_input"
$LocalOutputDir = Join-Path $ScriptDir "01_apply_calibration_output"

$CharacterizationDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "01_Characterization\04_Camera_Characterization"
$MapScriptPath = Join-Path $CharacterizationDir "04_map_cal_points.py"
$CharInputDir = Join-Path $CharacterizationDir "04_map_calibration_points_input"
$CharOutputDir = Join-Path $CharacterizationDir "04_map_calibration_points_output"

Write-Info "Configuration:"
Write-Host "  Sensor ID:             $SensorId"
Write-Host "  Local Input:           $LocalInputDir"
Write-Host "  Characterization Dir:  $CharacterizationDir"
Write-Host ""

if (-not (Test-Path $LocalInputDir)) {
    Write-Error "ERROR: Local input directory not found: $LocalInputDir"
    Write-Host "Please create the directory and add required files."
    exit 1
}

if (-not (Test-Path $CharacterizationDir)) {
    Write-Error "ERROR: Characterization directory not found: $CharacterizationDir"
    Write-Host "Please check your workspace structure."
    exit 1
}

if (-not (Test-Path $MapScriptPath)) {
    Write-Error "ERROR: Mapping script not found: $MapScriptPath"
    exit 1
}

if ($CsvFile -eq "") {
    Write-Info "Looking for CSV files in local input folder..."
    $CsvFiles = Get-ChildItem -Path $LocalInputDir -Filter "*.csv"
    
    if ($CsvFiles.Count -eq 0) {
        Write-Error "ERROR: No CSV files found in $LocalInputDir"
        Write-Host ""
        Write-Host "Please add a CSV file with luminance values to the input folder."
        Write-Host "Expected format:"
        Write-Host "  point, luminance, comment"
        Write-Host "  1, 150, Point 1"
        Write-Host "  2, 200, Point 2"
        Write-Host "  ..."
        exit 1
    }
    
    $CsvPath = $CsvFiles[0].FullName
    Write-Success "  Found CSV: $($CsvFiles[0].Name)"
} else {
    $CsvPath = Join-Path $LocalInputDir $CsvFile
    if (-not (Test-Path $CsvPath)) {
        Write-Error "ERROR: CSV file not found: $CsvPath"
        exit 1
    }
    Write-Success "  Using CSV: $CsvFile"
}

$HdrFileName = "${SensorId}_raw.hdr"
$VignettingHdrFileName = "${SensorId}_vignetting_corrected.hdr"

$LocalHdrPath = $null
if (Test-Path (Join-Path $LocalInputDir $VignettingHdrFileName)) {
    $LocalHdrPath = Join-Path $LocalInputDir $VignettingHdrFileName
    Write-Success "  Found HDR: $VignettingHdrFileName (vignetting-corrected)"
} elseif (Test-Path (Join-Path $LocalInputDir $HdrFileName)) {
    $LocalHdrPath = Join-Path $LocalInputDir $HdrFileName
    Write-Success "  Found HDR: $HdrFileName (raw)"
} else {
    Write-Error "ERROR: No HDR file found for $SensorId in $LocalInputDir"
    Write-Host ""
    Write-Host "Expected files:"
    Write-Host "  - ${SensorId}_vignetting_corrected.hdr (recommended)"
    Write-Host "  - ${SensorId}_raw.hdr (fallback)"
    Write-Host ""
    Write-Host "Please copy an HDR file from the characterization workflow to the input folder."
    exit 1
}

Write-Host ""

Write-Info "[1/5] Setting up temporary workspace..."
if (-not (Test-Path $CharInputDir)) {
    New-Item -ItemType Directory -Path $CharInputDir -Force | Out-Null
}
if (-not (Test-Path $CharOutputDir)) {
    New-Item -ItemType Directory -Path $CharOutputDir -Force | Out-Null
}

Write-Info "[2/5] Copying files to characterization input folder..."
$TempCsvPath = Join-Path $CharInputDir (Split-Path -Leaf $CsvPath)
$TempHdrPath = Join-Path $CharInputDir (Split-Path -Leaf $LocalHdrPath)

Copy-Item -Path $CsvPath -Destination $TempCsvPath -Force
Copy-Item -Path $LocalHdrPath -Destination $TempHdrPath -Force
Write-Success "  Copied CSV and HDR files"

Write-Host ""
Write-Info "[3/5] Launching calibration point mapper..."
Write-Host ""
Write-Host "Instructions:"
Write-Host "  - Click on the image to mark calibration points in order"
Write-Host "  - Press 'u' to undo last point"
Write-Host "  - Press 'q' to save and quit"
Write-Host "  - Press ESC to quit without saving"
Write-Host ""

$PythonCmd = "python `"$MapScriptPath`" $SensorId `"$TempCsvPath`""
Write-Host "Running: $PythonCmd" -ForegroundColor DarkGray
Write-Host ""

Invoke-Expression $PythonCmd
$ExitCode = $LASTEXITCODE

Write-Host ""

if ($ExitCode -ne 0) {
    Write-Error "ERROR: Calibration mapping failed or was cancelled (exit code: $ExitCode)"
    
    Write-Info "[4/5] Cleaning up temporary files..."
    Remove-Item -Path $TempCsvPath -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $TempHdrPath -Force -ErrorAction SilentlyContinue
    
    Write-Host ""
    exit $ExitCode
}

Write-Info "[4/5] Copying calibration points to local input folder..."
$OutputJsonPath = Join-Path $CharOutputDir "${SensorId}_calibration_points.json"
$LocalJsonPath = Join-Path $LocalInputDir "${SensorId}_calibration_points.json"

if (Test-Path $OutputJsonPath) {
    Copy-Item -Path $OutputJsonPath -Destination $LocalJsonPath -Force
    Write-Success "  Saved: ${SensorId}_calibration_points.json"
} else {
    Write-Warning "  Output file not found: $OutputJsonPath"
}

Write-Info "[5/5] Cleaning up temporary files..."
Remove-Item -Path $TempCsvPath -Force -ErrorAction SilentlyContinue
Remove-Item -Path $TempHdrPath -Force -ErrorAction SilentlyContinue
Remove-Item -Path $OutputJsonPath -Force -ErrorAction SilentlyContinue
Write-Success "  Cleaned up temporary files"

Write-Host ""
Write-Host "============================================================================" -ForegroundColor Green
Write-Host "CALIBRATION MAPPING COMPLETE!" -ForegroundColor Green
Write-Host "============================================================================" -ForegroundColor Green
Write-Host ""
Write-Success "Output saved to: $LocalJsonPath"
Write-Host ""
Write-Info "Next Step:"
Write-Host "  Run calibration: python 01_apply_calibration.py $SensorId"
Write-Host ""
Write-Host "The calibration points file is ready in the 01_apply_calibration_input folder."
Write-Host "You can now run the calibration script to generate a calibrated HDR image."
Write-Host ""
