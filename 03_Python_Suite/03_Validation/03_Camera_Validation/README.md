# Camera Validation

Validation pipeline for HDR camera luminance measurements, comparing calibrated camera-derived luminance against reference instrumentation and cross-validating spatial illuminance data with spectral sensor readings.

## Validation Types
- **External Validation**: Camera luminance vs. reference luminance meter (spot measurements)
- **Internal Cross-Validation**: Camera-derived illuminance vs. spectral sensor illuminance measurements

## Workflow

### 1. Prepare Input Files

#### Calibration Input
Place the following files in the `02_calibration_input/` directory:
- `roi_params.json`
- `sensorXX_calibration_report.json`
- `sensorXX_vignetting_correction_map.npy`

#### Validation Input
Place the following files in the `data/` directory:
- JPEG brackets: `YYYYMMDD_HHMMSS_sensorXX_expXXX.jpeg` (exposures per scene)
- CSV measurements: `YYYYMMDD_HHMMSS_sensorXX.csv`

### 2. Run the Pipeline

Follow these steps to execute the validation pipeline:

1. Place the input data as described in the "Prepare Input Files" section.
2. Run `01_process_images.ps1` to process JPEG brackets into calibrated HDR luminance maps.
3. Run `02_open_calibrated_HDRs.ps1` to visually inspect HDR outputs and select reference spots for comparison.

## Directory Structure

```
02_calibration_input/           # Camera calibration files
    roi_params.json             # Region of interest definition
    sensorXX_calibration_report.json
    sensorXX_vignetting_correction_map.npy

data/                           # Raw measurement data
    YYYYMMDD_HHMMSS_sensorXX_expXXX.jpeg  # JPEG exposure brackets
    YYYYMMDD_HHMMSS_sensorXX.csv          # Synchronized sensor CSV data

03_validation_output/           # Generated validation results
    sensorXX_calibrated_luminance.hdr     # HDR luminance maps
    sensorXX_validation_report.json       # Validation statistics
    sensorXX_comparison_plots.png         # Visual comparison plots

tools/                          # Processing utilities
    calculate_lux.py            # Luminance-to-illuminance conversion
```

## Output Metrics

The validation generates:
- **Mean Absolute Error (MAE)**: Average deviation between camera and reference measurements
- **Root Mean Square Error (RMSE)**: Quadratic error metric for luminance accuracy
- **Relative Error (%)**: Percentage deviation for each measurement point
- **Correlation Coefficient (R²)**: Linear relationship quality between camera and reference data
- **Spatial Uniformity Index**: Vignetting correction effectiveness across the field of view

## Expected Performance

Well-calibrated systems typically achieve:
- **Spot luminance accuracy**: ±5-10% vs. reference luminance meter
- **Illuminance cross-validation**: ±10-15% vs. spectral sensor lux readings
- **Spatial uniformity**: <10% luminance variation across central 80% of FOV after vignetting correction
