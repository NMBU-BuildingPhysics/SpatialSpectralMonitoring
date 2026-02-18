# Integration Time Model

Analyzes the relationship between TSL2591 Lux readings and optimal spectral integration times for AS7265X and AS7331. Determines the power-law coefficients used in the firmware's auto-exposure algorithm.

---

## Quick Start

### Prerequisites
- Python 3.8+
- Required packages: `pandas`, `numpy`, `matplotlib`, `seaborn`, `scipy`

Install dependencies:
```bash
pip install pandas numpy matplotlib seaborn scipy
```

### Directory Setup

Key directories and files you must create or populate:
- **`0_measurements/csv_files/`** - Place your raw `.csv` sweep files here (required)
- **`0_measurements/image_files/`** - Optional: place sensor images for review
- **`lux_calibration.csv`** - Lux sensor calibration coefficients file (required, in root directory)

All other directories are auto-created by scripts.

Execute scripts in order. Each step builds on the previous.

### Data Collection with Arduino Firmware

The sweep data is generated using the Arduino sketch [`Int_Time_Characterization.ino`](../../../02_Firmware/Utilities/Int_Time_Characterization.ino) located in `02_Firmware/Utilities/`. This firmware performs automated sensor sweeps across different integration times to characterize the relationship between TSL2591 lux readings and optimal spectral integration times.

#### Running Data Collection
1. Flash the `Int_Time_Characterization.ino` to your ESP32 device
2. Ensure WiFi credentials are configured in `secrets.h`
3. Place the device in your measurement environment
4. The firmware will automatically:
   - Perform sweeps at configurable intervals (default: 10 minutes)
   - Generate CSV files with format: `sweep_YYYYMMDD_HHMMSS_deviceXX.csv`
   - Upload data to FTP server location
   - Capture optional reference images for qualitative analysis

The generated CSV files should be downloaded and placed in the `0_measurements/csv_files/` directory for analysis.

## Input Directories

#### `0_measurements/` (Required)
- **Contents:** Raw sensor measurement files and optional images
- **File format:** `sweep_YYYYMMDD_HHMMSS_sensorXX.csv`
  - `YYYYMMDD` = Date (e.g., 20250101)
  - `HHMMSS` = Time (e.g., 143045)
  - `XX` = Sensor ID (e.g., 01, 02, ..., 12)
- **Example:** `sweep_20250101_143045_sensor01.csv`
- **Subdirectory:** `image_files/` - Optional captured images for outlier review

## Scripts

| # | Script | Purpose |
|---|--------|---------|
| 1a | `1_a_mergecsv.py` | Merge raw CSV data from sweep measurements into a unified master dataset. |
| 1b | `1_b_analyze_sensor_data.py` | Analyze sensor behavior and TSL2591 lux response characteristics from merged data. |
| 2a | `2_a_find_outliers.py` | Identify outlier measurement sweeps based on data distribution analysis. |
| 2b | `2_b_review_outliers.py` | Review identified outlier measurement sweeps and generate visualization outputs. |
| 3a | `3_a_Auto_INT_Finetune Target.py` | Fine-tune integration time model to target specifications through sensitivity analysis. |
| 3b | `3_b_Auto_INT_generate plots.py` | Generate analysis plots and model validation visualizations for optimal integration times. |
| 3c1 | `3_c_1error_results.py` | Calculate and analyze error metrics from calibration results. |
| 3c2 | `3_c_2error_results_raw.py` | Analyze raw uncalibrated error data before post-processing. |

---

## Output

The analysis produces:
- **Model coefficients (a, b)** for power-law fit: `y = a * x^b`
- **R² value** indicating fit quality
- **Calibrated vs. raw data comparison** for validation
- **Sensitivity analysis** showing parameter robustness
- **Visual plots** for each analysis stage

Check `3_c_error_results/` for final model parameters and fit quality metrics.

