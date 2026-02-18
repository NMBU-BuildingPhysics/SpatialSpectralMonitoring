# Lux Calibration Suite

Absolute illuminance (lux) calibration workflow for the Spatial-Spectral Sensing System. Generates temperature correction coefficients and applies per-sensor calibration factors.

## Scripts

| Script | Purpose |
|--------|---------|
| `1_generate_lux_temp_coeffs.py` | Generates temperature correction coefficients from temperature sweep data. Outputs plot and coefficients in C++/Python formats. |
| `2_calibrate_lux.py` | Calculates per-sensor calibration factors using temperature-corrected measurements. |
| `x_1_mergecsv.py` | Helper: Merges individual sensor CSV files into unified dataset. |

## Folders

| Folder | Contents |
|--------|----------|
| `0_Measurements/` | Input data: Raw measurements and temperature sweep data |
| `1_temp_coeffs/` | Temperature correction model (plot + C++/Python coefficients) |
| `2_Results/` | Final calibration factors for all sensors |
| `x_1_mergeCSV/` | Intermediate merged data (if using helper script) |

## Quick Start

1. Run: `python 1_generate_lux_temp_coeffs.py`
   - Generates temperature coefficients → saves to `1_temp_coeffs/`
   - Copy coefficients from output files

2. Run: `python 2_calibrate_lux.py`
   - Calculates calibration factors → saves to `2_Results/calibration_results.txt`
   - Enter reference lux value and temperature coefficients

## File Reference

### Input Data (0_Measurements/)
- `Source - halogenlamp/master_light_measurements.csv` - Raw sensor measurements (all sensors)
- `temp/lux_temp_sweep_data.csv` - Temperature sweep data for coefficient fitting

### Temperature Coefficients (1_temp_coeffs/)
- `lux_temp_correction_plot.png` - Temperature correction curve visualization
- `lux_cpp_temp_coefficients.txt` - C++ format coefficients
- `lux_python_coefficients.txt` - Python dict format (copy to `2_calibrate_lux.py`)

### Results (2_Results/)
- `calibration_results.txt` - C++ map of per-sensor calibration factors

