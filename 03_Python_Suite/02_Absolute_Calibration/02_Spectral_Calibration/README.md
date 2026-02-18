# Spectral Calibration Suite

Absolute spectral calibration workflow for the **Spatial-Spectral Sensing System**. Derives calibration coefficients (C_p) for all 21 sensor channels (3× AS7331 UV + 18× AS7265x VIS-NIR) and generates calibration data for sensor firmware.

## Overview

This suite provides tools for:
- **Sensor calibration** - Calculate absolute calibration coefficients from raw measurements and reference spectra
- **Spectral visualization** - Visualize sensor response curves and reference spectra  
- **C++ code generation** - Output calibration coefficients as C++ data structures for embedded systems

## Scripts

| Script | Purpose | Output |
|--------|---------|--------|
| `1_calibrate_sensor.py` | Main calibration engine. Calculates calibration coefficients (C_p) from raw sensor counts and reference SPD data using spectral convolution. Includes temperature correction and outputs C++ arrays. | `1_Results/calibration_results.txt`, plots to `1_Analysis_plots/` |
| `x1_visualize_sensor_SPD.py` | Generates visualization of all 21 sensor channels organized by chipset (AS7331 + AS7265x). | `x1_Analysis_Plots/x1_spectral_sensor_response.png` |
| `x2_visualize_spd_calibration_source.py` | Visualizes calibration source spectrum and sensor response curves with proper spectral ordering. | `x2_Analysis_Plots/x2_spd_visualization.png` |

## Folder Structure

```
├── 0_Measurements/                  # Input: Raw sensor measurement data
│   ├── Daylight/                    (alternative calibration source)
│   ├── LED/                         (alternative calibration source)
│   └── Sun2000/                     (PRIMARY CALIBRATION SOURCE)
│       ├── measured_counts.csv      (light measurements)
│       └── measured_counts_dark.csv (dark reference for noise characterization)
│
├── 0_SPD_Reference/                 # Reference: Spectroradiometer calibration data
│   ├── AS7265x/
│   │   └── SPD_AS7265x.csv          (18 VIS-NIR channels: 410-940 nm)
│   ├── AS7331/
│   │   ├── SPD_AS7331_uva.csv       (UVA 360 nm)
│   │   ├── SPD_AS7331_uvb.csv       (UVB 300 nm)
│   │   └── SPD_AS7331_uvc.csv       (UVC 260 nm)
│   ├── Daylight/                    (alternative reference)
│   ├── LED/                         (alternative reference)
│   └── Sun2000/
│       └── SPD_sun2000_Simulator.csv (Reference light source spectrum - PRIMARY)
│
├── 0_Correction_Factors/            # Calibration: Temperature correction coefficients
│   └── temp_coeffs.csv              (per-channel temperature sensitivity: a, b, c)
│
├── 1_Results/                       # Output: Final calibration results
│   └── calibration_results.txt      (C++ calibration coefficient data array)
│
├── 1_Analysis_plots/                # Output: Calibration analysis plots
│   ├── calibration_coefficients_UV.png
│   └── calibration_coefficients_VIS_NIR.png
│
├── x1_Analysis_Plots/               # Output: Datasheet-style visualization
│   └── x1_spectral_sensor_response.png
│
└── x2_Analysis_Plots/               # Output: Reference spectrum visualization
    └── x2_spd_visualization.png
```

## Quick Start

### 1. Run Main Calibration

**What it does:**
- Loads raw sensor measurements from `0_Measurements/Sun2000/`
- Loads reference spectral response data from `0_SPD_Reference/`
- Normalizes sensor response curves (to peak = 1.0)
- Pre-calculates known irradiance via spectral convolution: ∫ E_ref(λ) · R_p(λ) dλ
- Applies temperature corrections using `0_Correction_Factors/temp_coeffs.csv`
- Calculates normalized count rates: S'_p = S_p / (f_T,p · t_int · G)
- Computes calibration coefficients: C_p = ∫ E_ref(λ) · R_p(λ) dλ / (S'_p^Light - S'_p^Dark)
- Outputs C++ calibration array to `1_Results/calibration_results.txt`
- Creates analysis plots comparing UV and VIS-NIR channel calibration coefficients

**Output files:**
- `1_Results/calibration_results.txt` - C++ code with calibration coefficients (C_p)
- `1_Analysis_plots/calibration_coefficients_UV.png` - UV channels (UVC, UVB, UVA)
- `1_Analysis_plots/calibration_coefficients_VIS_NIR.png` - VIS-NIR channels (A-W)

### 2. Visualize Sensor Response

**Output:** `x1_Analysis_Plots/x1_spectral_sensor_response.png`  
Plot showing all 21 sensor channels organized by chipset with distinct colors:

### 3. Visualize Reference Spectra (Optional)

**Output:** `x2_Analysis_Plots/x2_spd_visualization.png`  
Combined visualization showing:
- Reference light source spectrum (Sun2000 Simulator) with filled outline
- All 21 sensor response curves overlaid by wavelength

## Data Processing Pipeline

```
Raw Measurements          Reference SPD Data       Temperature Coefficients
        ↓                         ↓                         ↓
    Load & Validate         Load & Normalize         Load Calibration Data
        ↓                         ↓                         ↓
        └─────────────────────────┼─────────────────────────┘
                                  ↓
            Pre-calculate Known Irradiance Per Channel:
            ∫ E_ref(λ) · R_p(λ) dλ  [mW/m²]
            (Spectral convolution via trapezoidal integration)
                                  ↓
        ┌─────────────────────────┼─────────────────────────┐
        ↓                         ↓                         ↓
    Extract Light/Dark      Apply Temp         Normalize by Settings:
    Counts (S_p)            Correction         S'_p = S_p/(f_T,p·t_int·G)
                            f_T,p = aT²+bT+c   [count/s]
        ↓                         ↓                         ↓
        └─────────────────────────┼─────────────────────────┘
                                  ↓
                Calculate Calibration Coefficients:
                C_p = ∫ E_ref(λ)·R_p(λ) dλ / (S'_p^Light - S'_p^Dark)
                [mJ/m²/count or equivalently mW/m² per count/s]
                                  ↓
                    Generate C++ Calibration Array
                                  ↓
                Output: calibration_results.txt
```

**C++ Output Order (Wavelength Ordered):**
```cpp
constexpr CalibrationFactorSet factorData[] = {
    // uvc, uvb, uva, ch1, ch2, ch3, ch4, ch5, ch6, ch13, ch14, ch7,
    // ch15, ch8, ch16, ch9, ch10, ch11, ch12, ch17, ch18
    {"device_name", {C_p1, C_p2, ..., C_p21}},
    ...
};
```