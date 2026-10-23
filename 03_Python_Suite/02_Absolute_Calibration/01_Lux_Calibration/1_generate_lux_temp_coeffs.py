# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Absolute lux calibration workflow for spectral sensor array.
# Generates temperature coefficients
# ==============================================================================

import pandas as pd
import numpy as np
import sys
from pathlib import Path
import matplotlib.pyplot as plt

base_folder = Path(__file__).parent
INPUT_DATA_FILE = base_folder / "0_Measurements" / "temp" / "temperature_sweep_data.csv"
output_folder = base_folder / "1_temp_coeffs"
output_folder.mkdir(exist_ok=True)

SENSOR_TO_MODEL = "sensor11"
REFERENCE_TEMPERATURE = 25.0
POLYNOMIAL_DEGREE = 2
MINIMUM_TEMPERATURE_TO_INCLUDE = 24.0
ENABLE_SUBSAMPLING = True
SUBSAMPLE_BIN_WIDTH_C = 1.0
SUBSAMPLE_MAX_PER_BIN = 50


def fit_and_plot(ax, x_data_full, y_data_full, x_data_fit, y_data_fit):
    if len(x_data_fit) < POLYNOMIAL_DEGREE + 1:
        ax.text(0.5, 0.5, "Not enough data to fit.", ha="center", va="center", transform=ax.transAxes)
        return [np.nan] * (POLYNOMIAL_DEGREE + 1)

    coeffs = np.polyfit(x_data_fit, y_data_fit, POLYNOMIAL_DEGREE)
    p = np.poly1d(coeffs)
    x_smooth = np.linspace(x_data_full.min(), x_data_full.max(), 200)
    y_smooth = p(x_smooth)

    ax.scatter(x_data_full, y_data_full, label=f"All Data ({SENSOR_TO_MODEL})", s=10, alpha=0.2, color="gray")
    ax.scatter(x_data_fit, y_data_fit, label=f"Fit Data (≥{MINIMUM_TEMPERATURE_TO_INCLUDE}°C)", s=15, alpha=0.7, color="C0")
    ax.plot(x_smooth, y_smooth, color="red", label=f"Polynomial Fit (deg={POLYNOMIAL_DEGREE})")

    ax.axvline(x=MINIMUM_TEMPERATURE_TO_INCLUDE, color="black", linestyle="--", alpha=0.6, label=f"Threshold {MINIMUM_TEMPERATURE_TO_INCLUDE}°C")

    equation_parts = []
    for i, c in enumerate(coeffs):
        power = POLYNOMIAL_DEGREE - i
        if abs(c) > 1e-10:
            if power > 1:
                equation_parts.append(f"{c:.4g}x^{power}")
            elif power == 1:
                equation_parts.append(f"{c:+.4g}x")
            else:
                equation_parts.append(f"{c:+.4g}")
    equation_str = "y = " + " ".join(equation_parts).lstrip("+ ")

    ax.set_title(f"Lux Temperature Correction Model (from {SENSOR_TO_MODEL})\n{equation_str}", fontsize=12)
    ax.set_xlabel("Temperature (°C)")
    ax.set_ylabel("Normalized Illuminance")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.6)

    return coeffs


print(f"Loading lux temp data from: {INPUT_DATA_FILE}")
try:
    df_full = pd.read_csv(INPUT_DATA_FILE)
except FileNotFoundError:
    print(f"ERROR: Cannot find '{INPUT_DATA_FILE}'.")
    sys.exit()

df_full = df_full[df_full['device'] == SENSOR_TO_MODEL].copy()
if df_full.empty:
    print(f"ERROR: No data found for '{SENSOR_TO_MODEL}' in the input file.")
    sys.exit()

df_fit = df_full[df_full['temperature'] >= MINIMUM_TEMPERATURE_TO_INCLUDE].copy()
if df_fit.empty:
    print("ERROR: No data remains after filtering for fitting.")
    sys.exit()

ref_df = df_full[(df_full['temperature'] >= REFERENCE_TEMPERATURE - 0.5) &
                 (df_full['temperature'] <= REFERENCE_TEMPERATURE + 0.5)]
if ref_df.empty:
    print(f"ERROR: No data found near reference temp {REFERENCE_TEMPERATURE}°C for {SENSOR_TO_MODEL}.")
    sys.exit()

ref_illuminance = ref_df['raw_lux'].mean()
print(f"Calculated reference illuminance for {SENSOR_TO_MODEL}: {ref_illuminance:.2f} lux")

df_full['normalized_illuminance'] = df_full['raw_lux'] / ref_illuminance
df_fit['normalized_illuminance'] = df_fit['raw_lux'] / ref_illuminance

if ENABLE_SUBSAMPLING:
    print(f"Subsampling data: max {SUBSAMPLE_MAX_PER_BIN} points per {SUBSAMPLE_BIN_WIDTH_C}°C bin.")
    df_fit['temp_bin'] = (df_fit['temperature'] / SUBSAMPLE_BIN_WIDTH_C).astype(int)
    df_fit = df_fit.groupby('temp_bin').apply(
        lambda x: x.sample(n=min(len(x), SUBSAMPLE_MAX_PER_BIN))
    ).reset_index(drop=True)
    print(f"Using {len(df_fit)} subsampled points for curve fitting.")

output_plot_path = output_folder / "lux_temp_correction_plot.png"
print(f"Generating plot: {output_plot_path}")
fig, ax = plt.subplots(figsize=(12, 7))
coeffs = fit_and_plot(
    ax,
    df_full['temperature'], df_full['normalized_illuminance'],
    df_fit['temperature'], df_fit['normalized_illuminance']
)

if len(coeffs) < 3:
    coeffs = np.pad(coeffs, (3 - len(coeffs), 0), 'constant')
a, b, c = coeffs

cpp_code = f"const TempCoeffSet universalLuxTempCoeffs = {{{a:.6g}f, {b:.6g}f, {c:.6g}f}};"
python_code = f"LUX_TEMP_COEFFS = {{'a': {a:.10g}, 'b': {b:.10g}, 'c': {c:.10g}}} # Temperature correction coefficients from 2_temp_coeffs"

output_message = (
    "\n\n" + "="*70 + "\n" +
    "=== C++ LUX TEMPERATURE COEFFICIENT DATA ===\n" +
    "="*70 + "\n" +
    "// This was generated by generate_lux_temp_coeffs.py\n" +
    f"// Model based on data from: {SENSOR_TO_MODEL}\n" +
    "// Add this line to your calibration.cpp file\n\n" +
    cpp_code + "\n" +
    "\n" + "="*70
)

print(output_message)

output_file = output_folder / "lux_cpp_temp_coefficients.txt"
with open(output_file, 'w') as f:
    f.write(output_message)
print(f"\nC++ coefficients saved to: {output_file}")

python_output_file = output_folder / "lux_python_coefficients.txt"
with open(python_output_file, 'w') as f:
    f.write(python_code)
print(f"Python coefficients saved to: {python_output_file}")

plt.tight_layout()
plt.savefig(output_plot_path, dpi=150)
plt.show()
plt.close()
