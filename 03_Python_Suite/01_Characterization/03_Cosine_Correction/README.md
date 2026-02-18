# Cosine Correction

Validates the angular response of the PTFE diffuser against an ideal cosine curve. Visualizes how well the sensor's optical response follows an ideal Lambertian (cosine) distribution across different incident angles.

---


## Quick Start

### Prerequisites
- Python 3.8+
- Required packages: `pandas`, `numpy`, `matplotlib`

Install dependencies:
```powershell
pip install pandas numpy matplotlib
```

### Input Data

**Required file:** `0_Measurements/sensor_data.csv`
- Angular response measurements at various incident angles
- Columns: `Angle` (0-90°) and wavelength data (260-940 nm)

Run the scripts in order.

## Scripts

| # | Script | Purpose |
|---|--------|---------|
| 1 | `01_cosine_correction_average.py` | Generate single comparison plot of average sensor response vs. ideal cosine distribution. Output: `01_cosine_correction_average.png`. |
| 2 | `02_cosine_correction_all_wavelengths.py` | Generate comprehensive 7×3 grid of angular response plots for all wavelengths (260-940 nm) with RMSE analysis. Output: `02_cosine_correction_all_wavelengths.png`. |
