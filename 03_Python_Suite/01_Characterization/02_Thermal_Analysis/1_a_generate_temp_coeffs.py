# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Thermal analysis module: Analyzes temperature effects on sensor performance and generates correction coefficients.
# Calculates temperature correction coefficients from thermal sweep data and outputs in C++, Python, and CSV formats.
# ==============================================================================

import pandas as pd
import numpy as np
import sys
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

SCRIPT_DIR = Path(__file__).parent
INPUT_DATA_FILE = SCRIPT_DIR / "0_Measurements/temperature_sweep_data.csv"
REFERENCE_TEMPERATURE = 25.0
POLYNOMIAL_DEGREE = 2
MINIMUM_TEMPERATURE_TO_INCLUDE = 25.0

ENABLE_SUBSAMPLING = True
SUBSAMPLE_BIN_WIDTH_C = 0.5
SUBSAMPLE_MAX_PER_BIN = 25

OUTPUT_DIR = SCRIPT_DIR / "1_a_Generate_temp_Coeffs"
OUTPUT_DIR.mkdir(exist_ok=True)
CORRECTION_FACTORS_DIR = OUTPUT_DIR


def fit_and_plot(ax, x_data_full, y_data_full, x_data_fit, y_data_fit, channel_name):
    """Fits polynomial to data and plots both full and subsampled datasets."""
    if len(x_data_fit) < POLYNOMIAL_DEGREE + 1:
        ax.text(0.5, 0.5, 'Not enough data points to fit curve.',
                ha='center', va='center', transform=ax.transAxes)
        return None

    coeffs = np.polyfit(x_data_fit, y_data_fit, POLYNOMIAL_DEGREE)
    p = np.poly1d(coeffs)
    x_smooth = np.linspace(x_data_full.min(), x_data_full.max(), 200)
    y_smooth = p(x_smooth)

    ax.scatter(x_data_full, y_data_full, label='All Measured Data',
               s=10, alpha=0.2, color='gray')
    ax.scatter(x_data_fit, y_data_fit, label='Data Used for Fit (Subsampled)',
               s=15, alpha=0.7, color='C0')
    ax.plot(x_smooth, y_smooth, color='red',
            label=f'Polynomial Fit (deg={POLYNOMIAL_DEGREE})')

    equation_parts = [
        f"{c:.4g}x^{POLYNOMIAL_DEGREE-i}" if (POLYNOMIAL_DEGREE-i) > 1
        else (f"{c:+.4g}x" if (POLYNOMIAL_DEGREE-i) == 1 else f"{c:+.4g}")
        for i, c in enumerate(coeffs) if abs(c) > 1e-9
    ]
    equation_str = "y = " + " ".join(equation_parts).lstrip('+ ')

    ax.set_title(f"Temperature Correction for Channel: {channel_name}\n{equation_str}",
                 fontsize=12)
    ax.set_xlabel("Temperature (°C)")
    ax.set_ylabel("Normalized Count")
    ax.legend()
    ax.grid(True, linestyle='--', alpha=0.6)
    return coeffs


print(f"Loading data from: {INPUT_DATA_FILE}")
try:
    df = pd.read_csv(str(INPUT_DATA_FILE))
except FileNotFoundError:
    print(f"ERROR: Cannot find file '{INPUT_DATA_FILE}'.")
    sys.exit()

df = df[df['temperature'] >= MINIMUM_TEMPERATURE_TO_INCLUDE].copy()
if df.empty:
    print("ERROR: No data remains after temperature filtering.")
    sys.exit()

ref_df = df[(df['temperature'] >= REFERENCE_TEMPERATURE - 0.5) &
            (df['temperature'] <= REFERENCE_TEMPERATURE + 0.5)]
if ref_df.empty:
    print(f"ERROR: No data found near reference temp {REFERENCE_TEMPERATURE}°C.")
    sys.exit()
ref_counts = ref_df.mean(numeric_only=True)

if ENABLE_SUBSAMPLING:
    print(f"Subsampling data: max {SUBSAMPLE_MAX_PER_BIN} points per "
          f"{SUBSAMPLE_BIN_WIDTH_C}°C bin.")
    df['temp_bin'] = (df['temperature'] / SUBSAMPLE_BIN_WIDTH_C).astype(int)
    df_fit = df.groupby('temp_bin').apply(
        lambda x: x.sample(n=min(len(x), SUBSAMPLE_MAX_PER_BIN))
    ).reset_index(drop=True)
    print(f"Using {len(df_fit)} subsampled points for curve fitting "
          f"(out of {len(df)} total).")
else:
    df_fit = df

channel_columns = [col for col in df.columns if col.startswith('raw_')]
all_coeffs = {}

output_pdf_path = OUTPUT_DIR / f"temperature_correction_plots_deg{POLYNOMIAL_DEGREE}.pdf"
with PdfPages(output_pdf_path) as pdf:
    print(f"\nProcessing {len(channel_columns)} channels...")
    for channel in channel_columns:
        norm_counts_full = df[channel] / ref_counts[channel]
        norm_counts_fit = df_fit[channel] / ref_counts[channel]

        fig, ax = plt.subplots(figsize=(10, 6))
        coeffs = fit_and_plot(ax, df['temperature'], norm_counts_full,
                              df_fit['temperature'], norm_counts_fit,
                              channel.replace('raw_', '').upper())
        pdf.savefig(fig)
        plt.close(fig)

        if coeffs is not None:
            coeff_key = channel.replace('raw_', '').upper()
            if len(coeffs) < 3:
                coeffs = np.pad(coeffs, (3 - len(coeffs), 0), 'constant')
            all_coeffs[coeff_key] = coeffs

print(f"\nAll plots saved to: {output_pdf_path}")

output_coeffs_path = CORRECTION_FACTORS_DIR / "temp_coeffs.csv"
print(f"Generating coefficient file: {output_coeffs_path}")
Path(CORRECTION_FACTORS_DIR).mkdir(exist_ok=True)
coeffs_df = pd.DataFrame.from_dict(all_coeffs, orient='index', columns=['a', 'b', 'c'])
coeffs_df.index.name = 'Channel'
coeffs_df.sort_index(inplace=True)
coeffs_df.to_csv(output_coeffs_path)

cpp_lines = []
cpp_lines.append("const std::map<std::string, TempCoeffSet> universalTempCoeffs = {")
sorted_keys = sorted(all_coeffs.keys())
for key in sorted_keys:
    coeffs = all_coeffs[key]
    cpp_lines.append(f'    {{"{key}", {{{coeffs[0]:.6g}f, {coeffs[1]:.6g}f, '
                    f'{coeffs[2]:.6g}f}}}},')
cpp_lines.append("};")
cpp_code_block = "\n".join(cpp_lines)

output_txt_path = OUTPUT_DIR / "calibration_temp_coeffs_CPP.txt"
print(f"Generating C++ code dump: {output_txt_path}")
with open(output_txt_path, "w") as f:
    f.write("// Automatically generated by 1_a_generate_temp_coeffs.py\n")
    f.write("// Copy and paste this into calibration.cpp\n\n")
    f.write(cpp_code_block)

print("\n" + "="*70)
print("=== C++ TEMPERATURE COEFFICIENT MAP ===")
print("="*70)
print(cpp_code_block)
print("\nProcess complete.")
print("="*70)
