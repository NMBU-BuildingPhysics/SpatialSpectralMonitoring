# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Analyzes the relationship between TSL2591 Lux readings and optimal spectral integration times.
# Generates analysis plots and model validation visualizations for optimal integration times.
# ==============================================================================

import pandas as pd
import numpy as np
import sys
from pathlib import Path
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import seaborn as sns
import glob

INPUT_DATA_PATTERN = "1_a_merged_data/master_sweep_data*.csv"
LUX_CALIBRATION_FILE = "0_measurements\lux_calibration.csv"
SATURATION_THRESHOLD = 65530
TARGET_ADC_COUNTS = SATURATION_THRESHOLD * 0.75
ILLUMINANCE_BIN_WIDTH = 50
MINIMUM_LUX_THRESHOLD = 1

OUTPUT_DIR = Path.cwd() / "3_b_analysis_results"
OUTPUT_DIR.mkdir(exist_ok=True)

file_list = glob.glob(INPUT_DATA_PATTERN)
if not file_list: sys.exit(f"ERROR: No files found for '{INPUT_DATA_PATTERN}'.")

df = pd.concat([pd.read_csv(f) for f in file_list], ignore_index=True)
lux_cal_df = pd.read_csv(LUX_CALIBRATION_FILE)
df = pd.merge(df, lux_cal_df, left_on='sensor', right_on='DeviceName', how='left')
df['lux_factor'].fillna(1.0, inplace=True)
df['cal_lux'] = df['raw_lux'] * df['lux_factor']
df = df[df['cal_lux'] >= MINIMUM_LUX_THRESHOLD].copy()
spectral_cols = [f'raw_ch{i}' for i in range(1, 19)]
df['max_spectral_count'] = df[spectral_cols].max(axis=1)
df = df[df['max_spectral_count'] < SATURATION_THRESHOLD].copy()
df['S_time_sec'] = df['S_time'] * 2.8 * 2.0 / 1000.0
df['lux_bin'] = (df['cal_lux'] // ILLUMINANCE_BIN_WIDTH) * ILLUMINANCE_BIN_WIDTH

print("Finding optimal integration times...")
optimal_points = []
for (sensor_name, bin_val), group in df.groupby(['sensor', 'lux_bin']):
    if len(group) >= 2 and group['max_spectral_count'].min() < TARGET_ADC_COUNTS and group['max_spectral_count'].max() > TARGET_ADC_COUNTS:
        sorted_group = group.sort_values('max_spectral_count').drop_duplicates(subset=['max_spectral_count'])
        optimal_time = np.interp(TARGET_ADC_COUNTS, sorted_group['max_spectral_count'], sorted_group['S_time_sec'])
        avg_lux = group['cal_lux'].mean()
        optimal_points.append({'sensor': sensor_name, 'illuminance': avg_lux, 'optimal_time_sec': optimal_time})

df_optimal = pd.DataFrame(optimal_points)
if df_optimal.empty: sys.exit("ERROR: Could not generate optimal points.")
print(f"Generated {len(df_optimal)} optimal data points.")

def power_law(x, a, b): 
    return a * np.power(x, b)

MAX_INTEGRATION_TIME_SEC = (255 * 2.8 * 2.0) / 1000.0

a_master, b_master = None, None
if len(df_optimal) >= 2:
    try:
        popt_master, _ = curve_fit(power_law, df_optimal['illuminance'], df_optimal['optimal_time_sec'])
        a_master, b_master = popt_master
        print("Master fit coefficients calculated.")
    except (RuntimeError, TypeError):
        print("Warning: Could not fit master curve.")

print("Generating individual sensor plots...")
unique_sensors = sorted(df_optimal['sensor'].unique())
num_sensors = len(unique_sensors)
ncols = 3
nrows = int(np.ceil(num_sensors / ncols))
fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(ncols * 7, nrows * 6), squeeze=False)
axes = axes.flatten()

for i, sensor_name in enumerate(unique_sensors):
    group = df_optimal[df_optimal['sensor'] == sensor_name]
    ax = axes[i]
    ax.scatter(group['illuminance'] / 1000, group['optimal_time_sec'], label='Optimal Points', color='C2', zorder=10)
    
    if len(group) >= 2: 
        try:
            popt, _ = curve_fit(power_law, group['illuminance'], group['optimal_time_sec'])
            a, b = popt
            x_smooth = np.linspace(group['illuminance'].min(), group['illuminance'].max(), 100)
            y_fit = np.clip(power_law(x_smooth, a, b), None, MAX_INTEGRATION_TIME_SEC)
            ax.plot(x_smooth / 1000, y_fit, label='Fit', color='C0')
            equation = f'y = {a:.4f} * x^({b:.4f})'
            ax.text(0.05, 0.05, equation, ha='left', va='bottom', transform=ax.transAxes, fontsize=10, bbox=dict(boxstyle='round,pad=0.3', fc='white', alpha=0.8))
        except (RuntimeError, TypeError): 
            pass
    
    if a_master is not None:
        x_master = np.linspace(df_optimal['illuminance'].min(), df_optimal['illuminance'].max(), 200)
        y_master = np.clip(power_law(x_master, a_master, b_master), None, MAX_INTEGRATION_TIME_SEC)
        ax.plot(x_master / 1000, y_master, color='black', linestyle='--', label='Master Fit', zorder=5)

    ax.set_ylim(bottom=0, top=MAX_INTEGRATION_TIME_SEC * 1.1)
    ax.set_title(f'Sensor: {sensor_name}', fontsize=14)
    ax.set_xlabel('Illuminance (klux)')
    ax.set_ylabel('Optimal Integration Time (sec)')
    ax.legend()
    ax.grid(True, linestyle='--')

for j in range(i + 1, len(axes)): 
    axes[j].set_visible(False)

fig.suptitle('Individual Sensor Fits (Master Fit Overlay)', fontsize=20, y=1.0)
plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig(OUTPUT_DIR / "individual_fits.png", dpi=150)
plt.close()
print("Individual plots saved.")

print("Generating combined plot...")
plt.figure(figsize=(16, 9))
sns.scatterplot(data=df_optimal, x=df_optimal['illuminance'] / 1000, y='optimal_time_sec', hue='sensor', s=100, alpha=0.7)

if a_master is not None:
    x_smooth = np.linspace(df_optimal['illuminance'].min(), df_optimal['illuminance'].max(), 400)
    y_master_fit = np.clip(power_law(x_smooth, a_master, b_master), None, MAX_INTEGRATION_TIME_SEC)
    plt.plot(x_smooth / 1000, y_master_fit, color='black', linestyle='--', label='Master Fit')
    master_equation = f'y = {a_master:.4f} * x^({b_master:.4f})'
    plt.text(0.95, 0.95, master_equation, ha='right', va='top', transform=plt.gca().transAxes, fontsize=12, bbox=dict(boxstyle='round,pad=0.3', fc='white', alpha=0.8))

plt.title('Combined Sensor Response', fontsize=20, pad=20)
plt.xlabel('Illuminance (klux)', fontsize=14)
plt.ylabel('Optimal Integration Time (sec)', fontsize=14)
plt.ylim(bottom=0, top=MAX_INTEGRATION_TIME_SEC * 1.1)
ax = plt.gca()
ax.legend(title='Sensor', bbox_to_anchor=(1.02, 1), loc='upper left')
plt.subplots_adjust(right=0.85)
plt.savefig(OUTPUT_DIR / "combined_response.png", dpi=150)
plt.close()

print("Plots generated. Analysis complete.")