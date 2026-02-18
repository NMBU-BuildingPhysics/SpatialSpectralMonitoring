# Camera Calibration: Apply Calibration and Validation

This folder contains scripts for calibrating HDR images to generate luminance-accurate results and validating calibration quality.

## Scripts
- **`0x_Run_CalibrationMapping.ps1`**: Helper script to map calibration points using HDR and CSV luminance values. Saves calibration points JSON to the input folder.
- **`01_apply_calibration.py`**: Main script to apply calibration. Auto-detects sensor ID from input files, calculates scale factors, and generates calibrated HDR and a report.
- **`02_validate_calibration.py`**: Validation script that generates falsecolor luminance maps, calibration statistics plots, and comprehensive validation reports.
- **`03_open_HDR_files.ps1`**: Opens HDR files for viewing.

## Workflow

1. Place HDR and optional CSV in `01_apply_calibration_input/`.
2. Run `0x_Run_CalibrationMapping.ps1` to generate new calibration points (if needed).
3. Run `01_apply_calibration.py` to apply calibration.
4. Run `02_validate_calibration.py` to validate calibration and generate visualizations.
5. Open files with `03_open_HDR_files.ps1` or find outputs in respective output folders.

## Outputs

### Apply Calibration (`01_apply_calibration_output/`)
- Calibrated HDR file
- Calibration report JSON with scale factors and error metrics

### Validation (`02_validate_output/`)
- Falsecolor luminance map (PNG)
- Calibration statistics plots (PNG)
- Validation report (Markdown) with quality assessment and recommendations

## Notes

- Auto-detects sensor ID from filenames in the input folder.
- Uses vignetting-corrected HDR if available, otherwise raw HDR.
- Outliers are flagged but not excluded.
- Sampling region: 5×5 pixels around each calibration point.
