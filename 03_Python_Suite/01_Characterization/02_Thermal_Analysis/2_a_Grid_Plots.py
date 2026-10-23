# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Thermal analysis module: Analyzes temperature effects on sensor performance and generates correction coefficients.
# Generates a grid of individual thermal analysis plots (4 columns × n rows), one per channel.
# ==============================================================================

import pandas as pd
import numpy as np
import sys
import matplotlib.pyplot as plt
import math
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "2_a_Grid_Plots"
OUTPUT_DIR.mkdir(exist_ok=True)

PLOT_ORDER_KEYS = [
    "raw_uvb", "raw_uva",
    "raw_ch1", "raw_ch2", "raw_ch3", "raw_ch4", "raw_ch5", "raw_ch6",
    "raw_ch13", "raw_ch14", "raw_ch7", "raw_ch15", "raw_ch8", "raw_ch16",
    "raw_ch9", "raw_ch10", "raw_ch11", "raw_ch12", "raw_ch17", "raw_ch18"
]

CHANNEL_LABEL_MAP = {
    "raw_uvb": "UVB", "raw_uva": "UVA",
    "raw_ch1": "410 nm", "raw_ch2": "435 nm", "raw_ch3": "460 nm",
    "raw_ch4": "485 nm", "raw_ch5": "510 nm", "raw_ch6": "535 nm",
    "raw_ch13": "560 nm", "raw_ch14": "585 nm", "raw_ch7": "610 nm",
    "raw_ch15": "645 nm", "raw_ch8": "680 nm", "raw_ch16": "705 nm",
    "raw_ch9": "730 nm", "raw_ch10": "760 nm", "raw_ch11": "810 nm",
    "raw_ch12": "860 nm", "raw_ch17": "900 nm", "raw_ch18": "940 nm"
}

INPUT_DATA_FILE = SCRIPT_DIR / "0_Measurements/temperature_sweep_data.csv"
REFERENCE_TEMPERATURE = 25.0
POLYNOMIAL_DEGREE = 2
MINIMUM_TEMPERATURE_TO_INCLUDE = 25.0
OUTPUT_IMAGE_FILE = OUTPUT_DIR / f"temperature_correction_grid_deg{POLYNOMIAL_DEGREE}.png"
IMAGE_DPI = 300

ENABLE_SUBSAMPLING = True
SUBSAMPLE_BIN_WIDTH_C = 0.5
SUBSAMPLE_MAX_PER_BIN = 25

def fit_and_plot(ax, x_data_full, y_data_full, x_data_fit, y_data_fit, plot_title, y_limits=None):
    if len(x_data_fit) < POLYNOMIAL_DEGREE + 1:
        ax.text(0.5, 0.5, 'Not enough data to fit.', ha='center', va='center', transform=ax.transAxes, fontsize=8)
        ax.set_title(plot_title, fontsize=10)
        return

    coeffs = np.polyfit(x_data_fit, y_data_fit, POLYNOMIAL_DEGREE)
    p = np.poly1d(coeffs)
    x_smooth = np.linspace(x_data_full.min(), x_data_full.max(), 200)
    y_smooth = p(x_smooth)

    ax.scatter(x_data_full, y_data_full, label='All Data', s=5, alpha=0.15, color='gray')
    ax.scatter(x_data_fit, y_data_fit, label='Fit Data (≥25°C)', s=10, alpha=0.7, color='C0')
    ax.plot(x_smooth, y_smooth, color='red', label=f'Fit (deg={POLYNOMIAL_DEGREE})')

    equation_parts = []
    for i, c in enumerate(coeffs):
        power = POLYNOMIAL_DEGREE - i
        if abs(c) > 1e-9:
            if power > 1: equation_parts.append(f"{c:.2g}x^{power}")
            elif power == 1: equation_parts.append(f"{c:+.2g}x")
            else: equation_parts.append(f"{c:+.2g}")
    equation_str = "y = " + " ".join(equation_parts).lstrip('+ ')

    ax.set_title(f"{plot_title}\n{equation_str}", fontsize=9)
    ax.set_xlabel("Temp (°C)", fontsize=8)
    ax.set_ylabel("Norm. Count", fontsize=8)
    ax.tick_params(axis='both', which='major', labelsize=8)
    ax.legend(fontsize=7)
    ax.grid(True, linestyle='--', alpha=0.6)

    if y_limits:
        ax.set_ylim(y_limits)


print(f"Loading data from: {INPUT_DATA_FILE}")
try:
    df_full = pd.read_csv(str(INPUT_DATA_FILE))
except FileNotFoundError:
    print(f"ERROR: Cannot find file '{INPUT_DATA_FILE}'.")
    sys.exit()

df_fit = df_full[df_full['temperature'] >= MINIMUM_TEMPERATURE_TO_INCLUDE].copy()
if df_fit.empty:
    print("ERROR: No data remains after filtering for fitting."); sys.exit()

ref_df = df_full[(df_full['temperature'] >= REFERENCE_TEMPERATURE - 0.5) &
                 (df_full['temperature'] <= REFERENCE_TEMPERATURE + 0.5)]
if ref_df.empty:
    print(f"ERROR: No data found near reference temperature {REFERENCE_TEMPERATURE}°C."); sys.exit()
ref_counts = ref_df.mean(numeric_only=True)

if ENABLE_SUBSAMPLING:
    print(f"Subsampling data: max {SUBSAMPLE_MAX_PER_BIN} points per {SUBSAMPLE_BIN_WIDTH_C}°C bin.")
    df_fit['temp_bin'] = (df_fit['temperature'] / SUBSAMPLE_BIN_WIDTH_C).astype(int)
    df_fit = df_fit.groupby('temp_bin').apply(lambda x: x.sample(n=min(len(x), SUBSAMPLE_MAX_PER_BIN))).reset_index(drop=True)
    print(f"Using {len(df_fit)} subsampled points for curve fitting (out of {len(df_full)} total).")
else:
    df_fit = df_fit

channels_to_plot = [ch for ch in PLOT_ORDER_KEYS if ch in df_full.columns]
missing_channels = set(PLOT_ORDER_KEYS) - set(channels_to_plot)
if missing_channels:
    print(f"\nWarning: The following channels were not found and will be skipped: {', '.join(missing_channels)}")

num_channels = len(channels_to_plot)
if num_channels == 0:
    print("ERROR: None of the specified channels were found in the data file."); sys.exit()

global_y_min, global_y_max = float('inf'), float('-inf')
for channel_key in channels_to_plot:
    norm_counts = df_full[channel_key] / ref_counts[channel_key]
    global_y_min = min(global_y_min, norm_counts.min())
    global_y_max = max(global_y_max, norm_counts.max())

y_range = global_y_max - global_y_min
padding = y_range * 0.05
shared_y_lims = (global_y_min - padding, global_y_max + padding)
print(f"\nSetting shared Y-axis for all plots to: ({shared_y_lims[0]:.2f}, {shared_y_lims[1]:.2f})")

COLS_PER_ROW = 4
rows = math.ceil(num_channels / COLS_PER_ROW)
print(f"Processing {num_channels} channels to generate a {rows}x{COLS_PER_ROW} grid plot...")

fig, axes = plt.subplots(rows, COLS_PER_ROW, figsize=(COLS_PER_ROW * 4.5, rows * 3.5), constrained_layout=True)
axes = axes.flatten()

for i, channel_key in enumerate(channels_to_plot):
    ax = axes[i]
    plot_label = CHANNEL_LABEL_MAP.get(channel_key, channel_key)

    norm_counts_full = df_full[channel_key] / ref_counts[channel_key]
    norm_counts_fit = df_fit[channel_key] / ref_counts[channel_key]

    fit_and_plot(ax, df_full['temperature'], norm_counts_full,
                 df_fit['temperature'], norm_counts_fit,
                 plot_label, y_limits=shared_y_lims)

for i in range(num_channels, len(axes)):
    axes[i].axis('off')

fig.suptitle(f'Temperature Correction Fits (Reference Temp: {REFERENCE_TEMPERATURE}°C)', fontsize=16, y=1.02)

plt.savefig(OUTPUT_IMAGE_FILE, dpi=IMAGE_DPI, bbox_inches='tight')
print(f"\nGrid plot successfully saved to: {OUTPUT_IMAGE_FILE}")

plt.show()

print("\nProcess complete.")
