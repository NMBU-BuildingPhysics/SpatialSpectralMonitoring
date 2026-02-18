# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Camera validation pipeline: Process JPEG brackets through HDR generation, vignetting correction, and calibration
# Cross-validates camera-derived illuminance against reference CSV measurements from spectral sensor
# ==============================================================================
param(
    [string]$SensorId = "sensor11"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Camera Validation Pipeline" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "[Step 1/5] Loading calibration data..." -ForegroundColor Yellow
Write-Host ""

$calibrationFile = "02_calibration_input\${SensorId}_calibration_report.json"
if (-not (Test-Path $calibrationFile)) {
    Write-Host "[ERROR] Calibration file not found: $calibrationFile" -ForegroundColor Red
    Write-Host "Please ensure calibration files are in the 02_calibration_input/ folder" -ForegroundColor Red
    exit 1
}

$calibData = Get-Content $calibrationFile | ConvertFrom-Json
$scaleFactor = $calibData.statistics.median

Write-Host "Calibration scale factor: $scaleFactor" -ForegroundColor Green
Write-Host ""

Write-Host "[Step 2/5] Scanning data folder for validation scenes..." -ForegroundColor Yellow
Write-Host ""

$dataDir = "data"
if (-not (Test-Path $dataDir)) {
    Write-Host "[ERROR] Data folder not found: $dataDir" -ForegroundColor Red
    exit 1
}

$allImages = Get-ChildItem "$dataDir\*.jpeg" | Sort-Object Name

$scenes = @{}
foreach ($img in $allImages) {
    if ($img.Name -match '(\d{8}_\d{6})_') {
        $timestamp = $matches[1]
        if (-not $scenes.ContainsKey($timestamp)) {
            $scenes[$timestamp] = @{
                Images = @()
                CSV = $null
            }
        }
        $scenes[$timestamp].Images += $img
    }
}

foreach ($timestamp in $scenes.Keys) {
    $csvFile = Get-ChildItem "$dataDir\${timestamp}_*.csv" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($csvFile) {
        $scenes[$timestamp].CSV = $csvFile
    }
}

$validScenes = $scenes.GetEnumerator() | Where-Object { $_.Value.Images.Count -gt 0 -and $_.Value.CSV -ne $null } | Sort-Object Name

Write-Host "Found $($validScenes.Count) validation scenes:" -ForegroundColor Green
foreach ($scene in $validScenes) {
    $ts = $scene.Key
    $imgCount = $scene.Value.Images.Count
    Write-Host "  - $ts : $imgCount images (with CSV)" -ForegroundColor White
}
Write-Host ""

Write-Host "[Step 3/5] Processing validation scenes..." -ForegroundColor Yellow
Write-Host ""

$results = @()
$sceneNum = 1

foreach ($scene in $validScenes) {
    $timestamp = $scene.Key
    $images = $scene.Value.Images
    $csvFile = $scene.Value.CSV
    
    Write-Host "Processing Scene $sceneNum/$($validScenes.Count): $timestamp" -ForegroundColor Cyan
    
    try {
        $sceneOutputDir = "03_validation_output\$timestamp"
        New-Item -ItemType Directory -Path $sceneOutputDir -Force | Out-Null
        
        $sortedImages = $images | Sort-Object Name
        $exposureTimes = @()
        $imagePaths = @()
        
        foreach ($img in $sortedImages) {
            if ($img.Name -match '_exp(\d+)\.jpeg$') {
                $expValue = [int]$matches[1]
                $exposureTimes += $expValue
                $imagePaths += $img.FullName
            }
        }
        
        if ($exposureTimes.Count -eq 0) {
            throw "No valid images with exposure values found"
        }
        
        Write-Host "  [1/6] Found $($exposureTimes.Count) exposure brackets" -ForegroundColor White
        
        Write-Host "  [2/6] Generating HDR..." -ForegroundColor White
        $rawHdrPath = "$sceneOutputDir\${timestamp}_${SensorId}_raw.hdr"
        $exposureStr = $exposureTimes -join ','
        $imagePathsStr = $imagePaths -join ' '
        
        python tools\generate_hdr_standalone.py $imagePaths --exposures $exposureStr --output $rawHdrPath 2>&1 | Out-Null
        
        if (-not (Test-Path $rawHdrPath)) {
            throw "HDR generation failed"
        }
        
        Write-Host "  [3/6] Applying vignetting correction..." -ForegroundColor White
        $vignettingMap = "02_calibration_input\${SensorId}_vignetting_correction_map.npy"
        $vignettingCorrectedPath = "$sceneOutputDir\${timestamp}_${SensorId}_vignetting_corrected.hdr"
        
        if (Test-Path $vignettingMap) {
            python tools\apply_vignetting_standalone.py --hdr $rawHdrPath --correction $vignettingMap --output $vignettingCorrectedPath 2>&1 | Out-Null
            
            if (-not (Test-Path $vignettingCorrectedPath)) {
                throw "Vignetting correction failed"
            }
            $hdrForCalibration = $vignettingCorrectedPath
        } else {
            Write-Host "    (No vignetting map found, skipping)" -ForegroundColor DarkGray
            $hdrForCalibration = $rawHdrPath
        }
        
        Write-Host "  [4/6] Applying calibration..." -ForegroundColor White
        $calibratedHdrPath = "$sceneOutputDir\${timestamp}_${SensorId}_calibrated.hdr"
        
        python tools\apply_calibration_standalone.py --hdr $hdrForCalibration --scale $scaleFactor --output $calibratedHdrPath 2>&1 | Out-Null
        
        if (-not (Test-Path $calibratedHdrPath)) {
            throw "Calibration application failed"
        }
        
        Write-Host "  [5/6] Calculating illuminance..." -ForegroundColor White
        
        $luxReportPath = "$sceneOutputDir\${timestamp}_${SensorId}_lux_report.json"
        python tools\calculate_lux.py --hdr $calibratedHdrPath --output $luxReportPath --sensor-id $SensorId 2>&1 | Out-Null
        
        if (-not (Test-Path $luxReportPath)) {
            throw "Lux calculation failed"
        }
        
        $luxData = Get-Content $luxReportPath | ConvertFrom-Json
        $calculatedLux = $luxData.lux_calculation.horizontal_illuminance_lux
        
        Write-Host "  [6/6] Comparing with measured value..." -ForegroundColor White
        $csvLine = Get-Content $csvFile.FullName -First 1
        $measuredLux = [float](($csvLine -split ',')[8])
        
        $error = (($calculatedLux - $measuredLux) / $measuredLux) * 100
        $absError = [Math]::Abs($error)
        
        Write-Host "    Calculated: $($calculatedLux.ToString('N2')) lux" -ForegroundColor White
        Write-Host "    Measured:   $($measuredLux.ToString('N2')) lux" -ForegroundColor White
        
        if ($absError -lt 10) {
            Write-Host "    Error:      $($error.ToString('N1'))%" -ForegroundColor Green
        } elseif ($absError -lt 20) {
            Write-Host "    Error:      $($error.ToString('N1'))%" -ForegroundColor Yellow
        } else {
            Write-Host "    Error:      $($error.ToString('N1'))%" -ForegroundColor Red
        }
        
        $results += @{
            Timestamp = $timestamp
            CalculatedLux = $calculatedLux
            MeasuredLux = $measuredLux
            ErrorPercent = $error
            Success = $true
            OutputDir = $sceneOutputDir
        }
        
        Write-Host "[OK] Scene $timestamp processed" -ForegroundColor Green
        
    } catch {
        Write-Host "[ERROR] Failed: $_" -ForegroundColor Red
        $results += @{
            Timestamp = $timestamp
            Success = $false
            ErrorMessage = $_.ToString()
        }
    }
    
    Write-Host ""
    $sceneNum++
}

Write-Host "[Step 4/5] Calculating validation statistics..." -ForegroundColor Yellow
Write-Host ""

$successfulResults = $results | Where-Object { $_.Success -eq $true }

if ($successfulResults.Count -eq 0) {
    Write-Host "[ERROR] No scenes processed successfully" -ForegroundColor Red
    exit 1
}

$errors = $successfulResults | ForEach-Object { $_.ErrorPercent }
$absErrors = $errors | ForEach-Object { [Math]::Abs($_) }

$meanError = ($errors | Measure-Object -Average).Average
$stdError = if ($errors.Count -gt 1) {
    $variance = ($errors | ForEach-Object { ($_ - $meanError) * ($_ - $meanError) } | Measure-Object -Sum).Sum / ($errors.Count - 1)
    [Math]::Sqrt($variance)
} else {
    0
}
$minError = ($errors | Measure-Object -Minimum).Minimum
$maxError = ($errors | Measure-Object -Maximum).Maximum

$within10 = ($absErrors | Where-Object { $_ -lt 10 }).Count
$within20 = ($absErrors | Where-Object { $_ -lt 20 }).Count

Write-Host "Validation Statistics:" -ForegroundColor Cyan
Write-Host "  Total scenes: $($results.Count)" -ForegroundColor White
Write-Host "  Successful: $($successfulResults.Count)" -ForegroundColor Green
Write-Host "  Failed: $($results.Count - $successfulResults.Count)" -ForegroundColor Red
Write-Host ""
Write-Host "Error Statistics:" -ForegroundColor Cyan
Write-Host "  Mean error:   $($meanError.ToString('N2'))%" -ForegroundColor White
Write-Host "  Std dev:      $($stdError.ToString('N2'))" -ForegroundColor White
Write-Host "  Min error:    $($minError.ToString('N2'))%" -ForegroundColor White
Write-Host "  Max error:    $($maxError.ToString('N2'))%" -ForegroundColor White
Write-Host "  Within ±10%:  $within10 / $($successfulResults.Count)" -ForegroundColor White
Write-Host "  Within ±20%:  $within20 / $($successfulResults.Count)" -ForegroundColor White
Write-Host ""

Write-Host "[Step 5/5] Generating validation report..." -ForegroundColor Yellow
Write-Host ""

$report = @{
    sensor_id = $SensorId
    calibration_scale_factor = $scaleFactor
    total_scenes = $results.Count
    successful_scenes = $successfulResults.Count
    failed_scenes = $results.Count - $successfulResults.Count
    error_statistics = @{
        mean_percent = $meanError
        std_dev_percent = $stdError
        min_percent = $minError
        max_percent = $maxError
        within_10_percent = $within10
        within_20_percent = $within20
    }
    scenes = $results | ForEach-Object {
        if ($_.Success) {
            @{
                timestamp = $_.Timestamp
                calculated_lux = $_.CalculatedLux
                measured_lux = $_.MeasuredLux
                error_percent = $_.ErrorPercent
                output_directory = $_.OutputDir
                success = $_.Success
            }
        } else {
            @{
                timestamp = $_.Timestamp
                success = $_.Success
                error_message = $_.ErrorMessage
            }
        }
    }
}

$reportPath = "03_validation_output\validation_report.json"
$report | ConvertTo-Json -Depth 10 | Set-Content $reportPath

Write-Host "Validation report saved: $reportPath" -ForegroundColor Green
Write-Host ""

Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "VALIDATION SUMMARY" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

Write-Host "Scene              Calculated   Measured    Error" -ForegroundColor White
Write-Host ("-" * 70) -ForegroundColor DarkGray

foreach ($result in $results) {
    if ($result.Success) {
        $line = "{0,-18} {1,10:N2}  {2,10:N2}  {3,8:N1}%" -f $result.Timestamp, $result.CalculatedLux, $result.MeasuredLux, $result.ErrorPercent
        $absError = [Math]::Abs($result.ErrorPercent)
        if ($absError -lt 10) {
            Write-Host $line -ForegroundColor Green
        } elseif ($absError -lt 20) {
            Write-Host $line -ForegroundColor Yellow
        } else {
            Write-Host $line -ForegroundColor Red
        }
    } else {
        Write-Host "$($result.Timestamp)      FAILED" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "All outputs saved in: 03_validation_output\" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""
