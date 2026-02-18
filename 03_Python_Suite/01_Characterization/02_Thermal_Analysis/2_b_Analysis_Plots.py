# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Thermal analysis module: Analyzes temperature effects on sensor performance and generates correction coefficients.
# Generates combined comparison plots, temperature sensitivity bar charts, and correction factor heatmaps.
# ==============================================================================

import pandas as pd
import numpy as np
import sys
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from pathlib import Path

OUTPUT_DIR = Path.cwd() / "2_b_Analysis_Plots"
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

INPUT_DATA_FILE = "0_Measurements/temperature_sweep_data.csv"
REFERENCE_TEMPERATURE = 25.0
POLYNOMIAL_DEGREE = 2
MINIMUM_TEMPERATURE_TO_INCLUDE = 25.0
OUTPUT_IMAGE_FILE = OUTPUT_DIR / f"temperature_correction_combined_plot_deg{POLYNOMIAL_DEGREE}.png"
IMAGE_DPI = 300

ENABLE_SUBSAMPLING = True
SUBSAMPLE_BIN_WIDTH_C = 0.5
SUBSAMPLE_MAX_PER_BIN = 25

print(f"Loading data from: {INPUT_DATA_FILE}")
try:
    df = pd.read_csv(INPUT_DATA_FILE)
except FileNotFoundError:
    print(f"ERROR: Cannot find file '{INPUT_DATA_FILE}'.")
    sys.exit()

df = df[df['temperature'] >= MINIMUM_TEMPERATURE_TO_INCLUDE].copy()
if df.empty:
    print("ERROR: No data remains after filtering.")
    sys.exit()

ref_df = df[(df['temperature'] >= REFERENCE_TEMPERATURE - 0.5) &
            (df['temperature'] <= REFERENCE_TEMPERATURE + 0.5)]
if ref_df.empty:
    print(f"ERROR: No data found near reference temperature {REFERENCE_TEMPERATURE}°C.")
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

channels_to_plot = [ch for ch in PLOT_ORDER_KEYS if ch in df.columns]
if not channels_to_plot:
    print("ERROR: None of the specified channels were found in the data file.")
    sys.exit()

print(f"\nProcessing {len(channels_to_plot)} channels for combined plot...")

fig, ax = plt.subplots(figsize=(12, 8))
colors = cm.viridis(np.linspace(0, 1, len(channels_to_plot)))

for i, channel_key in enumerate(channels_to_plot):
    x_data_fit = df_fit['temperature']
    y_data_fit = df_fit[channel_key] / ref_counts[channel_key]

    if len(x_data_fit.unique()) < POLYNOMIAL_DEGREE + 1:
        print(f"Skipping {channel_key}: Not enough unique data points.")
        continue

    coeffs = np.polyfit(x_data_fit, y_data_fit, POLYNOMIAL_DEGREE)
    p = np.poly1d(coeffs)

    x_smooth = np.linspace(df['temperature'].min(), df['temperature'].max(), 400)
    y_smooth = p(x_smooth)

    plot_label = CHANNEL_LABEL_MAP.get(channel_key, channel_key)
    ax.plot(x_smooth, y_smooth, label=plot_label, color=colors[i])

ax.set_title('Comparison of Temperature Correction Curves for All Channels',
             fontsize=16)
ax.set_xlabel('Temperature (°C)', fontsize=12)
ax.set_ylabel('Normalized Count (relative to 25°C)', fontsize=12)
ax.grid(True, which='both', linestyle='--', linewidth=0.5)

ax.axhline(1.0, color='black', linestyle=':', linewidth=1.5,
           label='Reference (No Change)')

legend = ax.legend(title="Sensor Channel", bbox_to_anchor=(1.04, 1),
                   loc="upper left")
legend.get_title().set_fontweight('bold')

plt.savefig(OUTPUT_IMAGE_FILE, dpi=IMAGE_DPI, bbox_inches='tight')
print(f"\nCombined plot successfully saved to: {OUTPUT_IMAGE_FILE}")



print("\nGenerating Alternative 1: Bar Chart of Temperature Sensitivity...")

sensitivities = {}
temp_range_for_sensitivity = (25, 45)

for channel_key in channels_to_plot:
    x_data_fit = df_fit['temperature']
    y_data_fit = df_fit[channel_key] / ref_counts[channel_key]

    if len(x_data_fit.unique()) < POLYNOMIAL_DEGREE + 1:
        continue

    coeffs = np.polyfit(x_data_fit, y_data_fit, POLYNOMIAL_DEGREE)
    p = np.poly1d(coeffs)

    val_start = p(temp_range_for_sensitivity[0])
    val_end = p(temp_range_for_sensitivity[1])

    percent_change = ((val_end / val_start) - 1) * 100
    label = CHANNEL_LABEL_MAP.get(channel_key, channel_key)
    sensitivities[label] = percent_change

sorted_sensitivities = dict(sorted(sensitivities.items(),
                                   key=lambda item: item[1]))

fig_bar, ax_bar = plt.subplots(figsize=(10, 8))
labels = list(sorted_sensitivities.keys())
values = list(sorted_sensitivities.values())

colors_bar = ['red' if v < 0 else 'blue' for v in values]
ax_bar.barh(labels, values, color=colors_bar)

ax_bar.set_title(f'Sensor Sensitivity to Temperature Change '
                 f'({temp_range_for_sensitivity[0]}°C to '
                 f'{temp_range_for_sensitivity[1]}°C)', fontsize=16)
ax_bar.set_xlabel('Change in Reading (%)', fontsize=12)
ax_bar.set_ylabel('Sensor Channel', fontsize=12)
ax_bar.grid(axis='x', linestyle='--', alpha=0.7)
ax_bar.axvline(0, color='black', linewidth=1)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / "temperature_sensitivity_barchart.png", dpi=300)


print("\nGenerating Alternative 2: Heatmap of Correction Factor...")

temp_grid = np.linspace(df['temperature'].min(), df['temperature'].max(), 50)
channel_labels = [CHANNEL_LABEL_MAP.get(key) for key in channels_to_plot]
correction_matrix = []

for channel_key in channels_to_plot:
    x_data_fit = df_fit['temperature']
    y_data_fit = df_fit[channel_key] / ref_counts[channel_key]

    if len(x_data_fit.unique()) < POLYNOMIAL_DEGREE + 1:
        correction_matrix.append([np.nan] * len(temp_grid))
        continue

    coeffs = np.polyfit(x_data_fit, y_data_fit, POLYNOMIAL_DEGREE)
    p = np.poly1d(coeffs)

    normalized_counts_on_grid = p(temp_grid)
    correction_factors = 1.0 / normalized_counts_on_grid
    correction_matrix.append(correction_factors)

correction_matrix = np.array(correction_matrix)

fig_hm, ax_hm = plt.subplots(figsize=(12, 8))
im = ax_hm.imshow(correction_matrix, aspect='auto', cmap='coolwarm',
                   vmin=0.95, vmax=1.05,
                   extent=[temp_grid.min(), temp_grid.max(),
                          len(channel_labels)-0.5, -0.5])

ax_hm.set_title('Temperature Correction Factor across Channels', fontsize=16)
ax_hm.set_xlabel('Temperature (°C)', fontsize=12)
ax_hm.set_ylabel('Sensor Channel', fontsize=12)

ax_hm.set_yticks(np.arange(len(channel_labels)))
ax_hm.set_yticklabels(channel_labels)

cbar = fig_hm.colorbar(im, ax=ax_hm)
cbar.set_label('Correction Factor (Multiplier)', fontsize=12)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / "temperature_correction_heatmap.png", dpi=300)


print("\nProcess complete.")
