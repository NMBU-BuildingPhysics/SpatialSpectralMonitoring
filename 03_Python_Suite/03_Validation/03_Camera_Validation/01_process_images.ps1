# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Camera validation pipeline: Validates camera-derived illuminance against spectral
# sensor reference measurements. Accepts device-generated HDR files paired with
# same-timestamp spectral sensor CSV files.
# ==============================================================================
param(
    # Folder containing HDR + CSV pairs (default: images/ in characterization pipeline)
    [string]$ImagesDir = "",
    # Filter to a single sensor, e.g. "sensor01". Leave empty to process all.
    [string]$SensorFilter = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Camera Validation Pipeline" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

# --------------------------------------------------------------------------
# Resolve input folder
# --------------------------------------------------------------------------
if ($ImagesDir -eq "") {
    $charBase = Resolve-Path "$scriptDir\..\..\01_Characterization\04_Camera_Characterization"
    $ImagesDir = "$charBase\images"
}

if (-not (Test-Path $ImagesDir)) {
    Write-Host "[ERROR] Images folder not found: $ImagesDir" -ForegroundColor Red
    Write-Host "Pass -ImagesDir <path> to specify the folder containing HDR + CSV pairs." -ForegroundColor Red
    exit 1
}

$charBase     = Resolve-Path "$scriptDir\..\..\01_Characterization\04_Camera_Characterization"
$vinFolder    = "$charBase\05_correct_vignetting_output"
$calibInputDir = "$scriptDir\02_calibration_input"

Write-Host "[Step 1/4] Scanning '$ImagesDir' for HDR + CSV pairs..." -ForegroundColor Yellow
Write-Host ""

# --------------------------------------------------------------------------
# Build list of valid (HDR, CSV, sensorId) triplets
# --------------------------------------------------------------------------
$validPairs = @()
$hdrFiles = Get-ChildItem "$ImagesDir\*.hdr" | Sort-Object Name

foreach ($hdr in $hdrFiles) {
    if ($hdr.Name -match '^(\d{8}_\d{6})_(sensor\d+)\.hdr$') {
        $ts       = $matches[1]
        $sensorId = $matches[2]
        if ($SensorFilter -ne "" -and $sensorId -ne $SensorFilter) { continue }
        $csvFile = Get-ChildItem "$ImagesDir\${ts}_${sensorId}.csv" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($csvFile) {
            $validPairs += [PSCustomObject]@{
                Timestamp = $ts
                SensorId  = $sensorId
                HdrFile   = $hdr
                CsvFile   = $csvFile
            }
        }
    }
}

if ($validPairs.Count -eq 0) {
    Write-Host "[ERROR] No matching HDR + CSV pairs found in: $ImagesDir" -ForegroundColor Red
    exit 1
}

Write-Host "Found $($validPairs.Count) HDR + CSV pairs:" -ForegroundColor Green
foreach ($p in $validPairs) {
    Write-Host "  - $($p.Timestamp) / $($p.SensorId)" -ForegroundColor White
}
Write-Host ""

# --------------------------------------------------------------------------
# Process each pair
# --------------------------------------------------------------------------
Write-Host "[Step 2/4] Processing scenes..." -ForegroundColor Yellow
Write-Host ""

$results  = @()
$sceneNum = 1

foreach ($pair in $validPairs) {
    $ts       = $pair.Timestamp
    $sensorId = $pair.SensorId
    $csvFile  = $pair.CsvFile

    Write-Host "Scene $sceneNum/$($validPairs.Count): $ts / $sensorId" -ForegroundColor Cyan

    try {
        $sceneOutputDir = "03_validation_output\${ts}_${sensorId}"
        New-Item -ItemType Directory -Path $sceneOutputDir -Force | Out-Null

        # Load calibration scale factor
        $calibFile = "$calibInputDir\${sensorId}_calibration_report.json"
        if (-not (Test-Path $calibFile)) { throw "Calibration report not found: $calibFile" }
        $calibData   = Get-Content $calibFile | ConvertFrom-Json
        $scaleFactor = $calibData.median_scale_factor
        Write-Host "  [1/4] Scale factor: $($scaleFactor.ToString('N4'))" -ForegroundColor White

        # Resolve HDR source: prefer _Vin.hdr, fall back to raw
        $vinPath = "$vinFolder\${sensorId}_Vin.hdr"
        if (Test-Path $vinPath) {
            $sourceHdr = $vinPath
            Write-Host "  [2/4] Using vignetting-corrected HDR" -ForegroundColor White
        } else {
            $sourceHdr = $pair.HdrFile.FullName
            Write-Host "  [2/4] Using raw HDR (no _Vin.hdr found)" -ForegroundColor DarkYellow
        }

        # Apply calibration
        Write-Host "  [3/4] Applying calibration..." -ForegroundColor White
        $calibratedHdrPath = "$sceneOutputDir\${ts}_${sensorId}_Cal.hdr"
        python tools\apply_calibration_standalone.py `
            --hdr $sourceHdr --scale $scaleFactor --output $calibratedHdrPath 2>&1 | Out-Null
        if (-not (Test-Path $calibratedHdrPath)) { throw "Calibration step produced no output HDR" }

        # Calculate lux
        Write-Host "  [4/4] Calculating illuminance..." -ForegroundColor White
        $luxReportPath = "$sceneOutputDir\${ts}_${sensorId}_lux_report.json"
        python tools\calculate_lux.py `
            --hdr $calibratedHdrPath --output $luxReportPath --sensor-id $sensorId 2>&1 | Out-Null
        if (-not (Test-Path $luxReportPath)) { throw "Lux calculation produced no report" }

        $luxData       = Get-Content $luxReportPath | ConvertFrom-Json
        $calculatedLux = $luxData.lux_calculation.horizontal_illuminance_lux

        # Reference lux from CSV column 16 (cal_lux)
        # Header: date,time,device,rssi,uptime_min,S_gain,S_time,U_gain,U_time,
        #         I_gain,I_time,num_accum,temperature,humidity,tsl_ch0,tsl_ch1,
        #         raw_lux,cal_lux,...
        $csvFields   = (Get-Content $csvFile.FullName -First 1) -split ','
        $measuredLux = [float]$csvFields[16]

        $error    = (($calculatedLux - $measuredLux) / $measuredLux) * 100
        $absError = [Math]::Abs($error)

        Write-Host "    Camera lux:   $($calculatedLux.ToString('N1'))" -ForegroundColor White
        Write-Host "    Sensor lux:   $($measuredLux.ToString('N1'))" -ForegroundColor White
        $errColor = if ($absError -lt 10) { 'Green' } elseif ($absError -lt 20) { 'Yellow' } else { 'Red' }
        Write-Host "    Error:        $($error.ToString('N1'))%" -ForegroundColor $errColor

        $results += [PSCustomObject]@{
            Timestamp     = $ts
            SensorId      = $sensorId
            CalculatedLux = $calculatedLux
            MeasuredLux   = $measuredLux
            ErrorPercent  = $error
            Success       = $true
            OutputDir     = $sceneOutputDir
        }
        Write-Host "[OK] $sensorId done" -ForegroundColor Green

    } catch {
        Write-Host "[ERROR] $sensorId failed: $_" -ForegroundColor Red
        $results += [PSCustomObject]@{
            Timestamp    = $ts
            SensorId     = $sensorId
            Success      = $false
            ErrorMessage = $_.ToString()
        }
    }

    Write-Host ""
    $sceneNum++
}

# --------------------------------------------------------------------------
Write-Host "[Step 3/4] Statistics..." -ForegroundColor Yellow
Write-Host ""

$ok     = $results | Where-Object { $_.Success }
$failed = $results | Where-Object { -not $_.Success }

if ($ok.Count -eq 0) {
    Write-Host "[ERROR] No scenes processed successfully." -ForegroundColor Red
    exit 1
}

$errors    = $ok | ForEach-Object { $_.ErrorPercent }
$absErrors = $errors | ForEach-Object { [Math]::Abs($_) }

$meanError = ($errors | Measure-Object -Average).Average
$stdError  = if ($errors.Count -gt 1) {
    $variance = ($errors | ForEach-Object { ($_ - $meanError) * ($_ - $meanError) } | Measure-Object -Sum).Sum / ($errors.Count - 1)
    [Math]::Sqrt($variance)
} else { 0 }
$minError = ($errors | Measure-Object -Minimum).Minimum
$maxError = ($errors | Measure-Object -Maximum).Maximum
$within10 = ($absErrors | Where-Object { $_ -lt 10 }).Count
$within20 = ($absErrors | Where-Object { $_ -lt 20 }).Count

Write-Host "Error Statistics (camera vs spectral sensor cal_lux):" -ForegroundColor Cyan
Write-Host "  Scenes total:  $($results.Count) ($($ok.Count) OK, $($failed.Count) failed)" -ForegroundColor White
Write-Host "  Mean error:    $($meanError.ToString('N2'))%" -ForegroundColor White
Write-Host "  Std dev:       $($stdError.ToString('N2'))%" -ForegroundColor White
Write-Host "  Min / Max:     $($minError.ToString('N2'))% / $($maxError.ToString('N2'))%" -ForegroundColor White
Write-Host "  Within �10%:   $within10 / $($ok.Count)" -ForegroundColor White
Write-Host "  Within �20%:   $within20 / $($ok.Count)" -ForegroundColor White
Write-Host ""

Write-Host "Per-sensor results:" -ForegroundColor Cyan
Write-Host ("  {0,-12} {1,10} {2,10} {3,8}" -f "Sensor", "Camera(lx)", "Sensor(lx)", "Error%") -ForegroundColor White
Write-Host ("  " + "-" * 46) -ForegroundColor DarkGray
foreach ($r in ($ok | Sort-Object SensorId)) {
    $errColor = if ([Math]::Abs($r.ErrorPercent) -lt 10) { 'Green' } `
                elseif ([Math]::Abs($r.ErrorPercent) -lt 20) { 'Yellow' } else { 'Red' }
    Write-Host ("  {0,-12} {1,10:N1} {2,10:N1} {3,8:N1}" -f `
        $r.SensorId, $r.CalculatedLux, $r.MeasuredLux, $r.ErrorPercent) -ForegroundColor $errColor
}
Write-Host ""

# --------------------------------------------------------------------------
Write-Host "[Step 4/4] Saving validation report..." -ForegroundColor Yellow

$report = @{
    processed_at      = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    images_dir        = $ImagesDir
    total_scenes      = $results.Count
    successful_scenes = $ok.Count
    failed_scenes     = $failed.Count
    error_statistics  = @{
        mean_percent    = $meanError
        std_dev_percent = $stdError
        min_percent     = $minError
        max_percent     = $maxError
        within_10_pct   = $within10
        within_20_pct   = $within20
    }
    scenes = @($results | ForEach-Object {
        if ($_.Success) {
            @{ timestamp=$_.Timestamp; sensor_id=$_.SensorId;
               camera_lux=$_.CalculatedLux; sensor_lux=$_.MeasuredLux;
               error_percent=$_.ErrorPercent; success=$true }
        } else {
            @{ timestamp=$_.Timestamp; sensor_id=$_.SensorId;
               success=$false; error=$_.ErrorMessage }
        }
    })
}

New-Item -ItemType Directory -Path "03_validation_output" -Force | Out-Null
$reportPath = "03_validation_output\validation_report.json"
$report | ConvertTo-Json -Depth 10 | Set-Content $reportPath

Write-Host "Report saved: $reportPath" -ForegroundColor Green
Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "DONE" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""
