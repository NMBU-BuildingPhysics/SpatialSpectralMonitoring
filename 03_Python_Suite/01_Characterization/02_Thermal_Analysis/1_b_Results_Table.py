# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Thermal analysis module: Analyzes temperature effects on sensor performance and generates correction coefficients.
# Generates a summary table of thermal response data with temperature coefficients and normalization values.
# ==============================================================================

import pandas as pd
import numpy as np
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "1_b_Results_Table"
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
OUTPUT_CSV_FILE = OUTPUT_DIR / "temperature_correction_coefficients_table.csv"
REFERENCE_TEMPERATURE = 25.0
POLYNOMIAL_DEGREE = 2
MINIMUM_TEMPERATURE_TO_INCLUDE = 25.0

ENABLE_SUBSAMPLING = True
SUBSAMPLE_BIN_WIDTH_C = 0.5
SUBSAMPLE_MAX_PER_BIN = 25

print(f"Loading data from: {INPUT_DATA_FILE}")
try:
    df = pd.read_csv(str(INPUT_DATA_FILE))
except FileNotFoundError:
    print(f"ERROR: Cannot find file '{INPUT_DATA_FILE}'.")
    sys.exit()

df = df[df['temperature'] >= MINIMUM_TEMPERATURE_TO_INCLUDE].copy()
if df.empty:
    print("ERROR: No data remains after filtering.")
    sys.exit()

temp_min_global = df['temperature'].min()
temp_max_global = df['temperature'].max()
print(f"Data Temperature Range: {temp_min_global:.1f}°C to {temp_max_global:.1f}°C")

ref_df = df[(df['temperature'] >= REFERENCE_TEMPERATURE - 0.5) &
            (df['temperature'] <= REFERENCE_TEMPERATURE + 0.5)]
if ref_df.empty:
    print(f"ERROR: No data found near reference temperature {REFERENCE_TEMPERATURE}°C.")
    sys.exit()
ref_counts = ref_df.mean(numeric_only=True)

if ENABLE_SUBSAMPLING:
    print(f"Subsampling data for fit (Max {SUBSAMPLE_MAX_PER_BIN}/bin)...")
    df['temp_bin'] = (df['temperature'] / SUBSAMPLE_BIN_WIDTH_C).astype(int)
    df_fit = df.groupby('temp_bin').apply(
        lambda x: x.sample(n=min(len(x), SUBSAMPLE_MAX_PER_BIN))
    ).reset_index(drop=True)
else:
    df_fit = df

channels_to_process = [ch for ch in PLOT_ORDER_KEYS if ch in df.columns]
if not channels_to_process:
    print("ERROR: None of the specified channels were found in the data file.")
    sys.exit()

print(f"\nProcessing {len(channels_to_process)} channels...")
table_rows = []

t_grid_eval = np.linspace(temp_min_global, temp_max_global, 500)

for channel_key in channels_to_process:
    x_data = df_fit['temperature']
    y_data = df_fit[channel_key] / ref_counts[channel_key]

    if len(x_data.unique()) < POLYNOMIAL_DEGREE + 1:
        print(f"Warning: Skipping {channel_key} (insufficient data for fit).")
        continue

    coeffs = np.polyfit(x_data, y_data, POLYNOMIAL_DEGREE)
    p = np.poly1d(coeffs)

    y_eval = p(t_grid_eval)
    fit_min = np.min(y_eval)
    fit_max = np.max(y_eval)

    label = CHANNEL_LABEL_MAP.get(channel_key, channel_key)
    padded_coeffs = np.pad(coeffs, (3 - len(coeffs), 0), 'constant')

    row = {
        'Channel': label,
        'a (T^2)': padded_coeffs[0],
        'b (T^1)': padded_coeffs[1],
        'c (T^0)': padded_coeffs[2],
        f'Min Norm Count ({temp_min_global:.0f}-{temp_max_global:.0f}°C)': fit_min,
        f'Max Norm Count ({temp_min_global:.0f}-{temp_max_global:.0f}°C)': fit_max
    }
    table_rows.append(row)

results_df = pd.DataFrame(table_rows)

column_order = [
    'Channel',
    'a (T^2)', 'b (T^1)', 'c (T^0)',
    f'Min Norm Count ({temp_min_global:.0f}-{temp_max_global:.0f}°C)',
    f'Max Norm Count ({temp_min_global:.0f}-{temp_max_global:.0f}°C)'
]
results_df = results_df[column_order]

results_df.to_csv(OUTPUT_CSV_FILE, index=False)
print(f"\nTable successfully saved to: {OUTPUT_CSV_FILE}")

print("\n--- Table Preview (Rounded) ---")
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
display_df = results_df.copy()
numeric_cols = display_df.select_dtypes(include=[np.number]).columns
display_df[numeric_cols[:3]] = display_df[numeric_cols[:3]].map(lambda x: f"{x:.4e}")
display_df[numeric_cols[3:]] = display_df[numeric_cols[3:]].map(lambda x: f"{x:.4f}")
print(display_df)
print("-------------------------------")
