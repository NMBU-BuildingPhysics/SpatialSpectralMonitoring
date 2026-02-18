# Thermal Analysis

Analyzes temperature effects on sensor performance through thermal ramp experiments. Determines temperature correction coefficients for compensating thermal drift in measurements.

---


## Quick Start

### Prerequisites
- Python 3.8+
- Required packages: `pandas`, `numpy`, `matplotlib`, `scipy`

Install dependencies:
```powershell
pip install pandas numpy matplotlib scipy
```

### Input Data

**Required file:** `0_Measurements/temperature_sweep_data.csv`
- Raw thermal ramp measurements across temperature range
- Columns: `temperature` (°C) and channel data (`raw_*`)

Run the scripts in order. Each step builds on the previous.

## Scripts

| # | Script | Purpose |
|---|--------|---------|
| 1a | `1_a_generate_temp_coeffs.py` | Calculate temperature correction coefficients from thermal sweep data. Outputs coefficients in C++ format (`calibration_temp_coeffs_CPP.txt`), CSV (`temp_coeffs.csv`), and plots (`temperature_correction_plots_deg2.pdf`). |
| 1b | `1_b_Results_Table.py` | Generate summary table of thermal response data with temperature coefficients and min/max normalization values. Output: `temperature_correction_coefficients_table.csv`. |
| 2a | `2_a_Grid_Plots.py` | Generate grid of individual thermal analysis plots (4 columns × n rows), one per channel. Output: `temperature_correction_grid_deg2.png`. |
| 2b | `2_b_Analysis_Plots.py` | Generate combined comparison plot (`temperature_correction_combined_plot_deg2.png`), temperature sensitivity bar chart (`temperature_sensitivity_barchart.png`), and correction factor heatmap (`temperature_correction_heatmap.png`). |
