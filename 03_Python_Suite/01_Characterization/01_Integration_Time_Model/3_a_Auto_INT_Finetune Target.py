# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Analyzes the relationship between TSL2591 Lux readings and optimal spectral integration times.
# Fine-tunes integration time model to target specifications through sensitivity analysis.
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
LUX_CALIBRATION_FILE = "0_measurements/lux_calibration.csv"
SATURATION_THRESHOLD = 65530
MINIMUM_LUX_THRESHOLD = 5.0

TARGET_ACD_PERCENTAGE = [0.60, 0.70, 0.75, 0.80, 0.90]
TARGET_ADC_COUNTS_LIST = SATURATION_THRESHOLD * np.array(TARGET_ACD_PERCENTAGE)
print(TARGET_ADC_COUNTS_LIST)
ILLUMINANCE_BIN_WIDTH_LIST = [100]

ExcludeSensors = []
UseSensors = [f'sensor{str(i).zfill(2)}' for i in range(1, 13) if f'sensor{str(i).zfill(2)}' not in ExcludeSensors]

OUTPUT_DIR = Path.cwd() / "3_a_finetune_results"
OUTPUT_DIR.mkdir(exist_ok=True)

file_list = glob.glob(INPUT_DATA_PATTERN)
if not file_list: sys.exit(f"ERROR: No files found for '{INPUT_DATA_PATTERN}'.")

df = pd.concat([pd.read_csv(f) for f in file_list], ignore_index=True)
lux_cal_df = pd.read_csv(LUX_CALIBRATION_FILE)

df = df[df['sensor'].isin(UseSensors)].copy()
df = pd.merge(df, lux_cal_df, left_on='sensor', right_on='DeviceName', how='left')
df['lux_factor'].fillna(1.0, inplace=True)
df['cal_lux'] = df['raw_lux'] * df['lux_factor']
df = df[df['cal_lux'] >= MINIMUM_LUX_THRESHOLD].copy()
spectral_cols = [f'raw_ch{i}' for i in range(1, 19)]
df['max_spectral_count'] = df[spectral_cols].max(axis=1)
df = df[df['max_spectral_count'] < SATURATION_THRESHOLD].copy()
df['S_time_sec'] = df['S_time'] * 2.8 * 2.0 / 1000.0
print(f"Prepared {len(df)} valid data rows.")

master_fit_summary = []

def power_law(x, a, b): 
    return a * np.power(x, b)

for bin_width in ILLUMINANCE_BIN_WIDTH_LIST:
    for target_counts in TARGET_ADC_COUNTS_LIST:
        print(f"\nAnalyzing: Target={int(target_counts)} counts, Bin Width={int(bin_width)} lux")
        
        df['lux_bin'] = (df['cal_lux'] // bin_width) * bin_width
        optimal_points = []
        
        for (sensor_name, bin_val), group in df.groupby(['sensor', 'lux_bin']):
            if len(group) >= 2 and group['max_spectral_count'].min() < target_counts and group['max_spectral_count'].max() > target_counts:
                sorted_group = group.sort_values('max_spectral_count').drop_duplicates(subset=['max_spectral_count'])
                optimal_time = np.interp(target_counts, sorted_group['max_spectral_count'], sorted_group['S_time_sec'])
                avg_lux = group['cal_lux'].mean()
                optimal_points.append({'sensor': sensor_name, 'illuminance': avg_lux, 'optimal_time_sec': optimal_time})

        if not optimal_points:
            print(" - No optimal points found. Skipping.")
            continue
        
        df_optimal = pd.DataFrame(optimal_points)
        print(f" - Generated {len(df_optimal)} optimal points.")

        individual_coeffs = {}
        for sensor_name, group in df_optimal.groupby('sensor'):
            if len(group) >= 2:
                try:
                    popt, _ = curve_fit(power_law, group['illuminance'], group['optimal_time_sec'])
                    individual_coeffs[sensor_name] = popt
                except RuntimeError:
                    pass

        if not individual_coeffs:
            print(" - Not enough data to fit models. Skipping.")
            continue

        coeffs_df = pd.DataFrame.from_dict(individual_coeffs, orient='index', columns=['a', 'b'])
        a_master = coeffs_df['a'].mean()
        b_master = coeffs_df['b'].mean()
        master_fit_summary.append({'target': target_counts, 'bin_width': bin_width, 'a': a_master, 'b': b_master, 'sensors_modeled': len(coeffs_df)})
        
        plt.figure(figsize=(16, 9))
        sns.scatterplot(data=df_optimal, x=df_optimal['illuminance'] / 1000, y='optimal_time_sec', hue='sensor', s=100, alpha=0.7)
        x_smooth = np.linspace(df_optimal['illuminance'].min(), df_optimal['illuminance'].max(), 400)
        y_master_fit = power_law(x_smooth, a_master, b_master)
        plt.plot(x_smooth / 1000, y_master_fit, color='black', linestyle='--', label='Master Fit')
        
        master_equation = f'y = {a_master:.3f} * x^({b_master:.3f})'
        plt.text(0.95, 0.95, master_equation, ha='right', va='top', transform=plt.gca().transAxes, bbox=dict(boxstyle='round', fc='w', alpha=0.8))
        plt.title(f'Combined Response (Target={int(target_counts)}, Bin={int(bin_width)})', fontsize=18)
        plt.xlabel('Illuminance (klux)'); plt.ylabel('Optimal Integration Time (sec)')
        ax = plt.gca()
        ax.legend(title='Sensor', bbox_to_anchor=(1.02, 1), loc='upper left')
        plt.subplots_adjust(right=0.85)
        
        filename = f"combined_plot_target{int(target_counts)}_bin{int(bin_width)}.png"
        plt.savefig(OUTPUT_DIR / filename, dpi=150)
        plt.close()

print("\n" + "="*70)
print("SENSITIVITY ANALYSIS SUMMARY")
print("="*70)
summary_df = pd.DataFrame(master_fit_summary)
print(summary_df)
print("\nNote: Look for (a, b) pairs that are most stable across runs.")