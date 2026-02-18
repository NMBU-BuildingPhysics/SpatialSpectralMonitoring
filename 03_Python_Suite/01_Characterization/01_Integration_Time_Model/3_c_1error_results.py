# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Analyzes the relationship between TSL2591 Lux readings and optimal spectral integration times.
# Calculates and analyzes error metrics from calibration results.
# ==============================================================================

import pandas as pd
import numpy as np
import sys
from pathlib import Path
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import glob

INPUT_DATA_PATTERN = "1_a_merged_data/master_sweep_data*.csv"
LUX_CALIBRATION_FILE = "lux_calibration.csv"
OUTPUT_DIR = Path.cwd() / "3_c_error_results"

SATURATION_THRESHOLD = 65530
TARGET_ADC_COUNTS = SATURATION_THRESHOLD * 0.75
ILLUMINANCE_BIN_WIDTH = 100
MINIMUM_LUX_THRESHOLD = 5.0
MAXIMUM_LUX_THRESHOLD = 1000000.0

def load_and_prepare_data():
    file_list = glob.glob(INPUT_DATA_PATTERN)
    if not file_list:
        sys.exit(f"ERROR: No data files found matching '{INPUT_DATA_PATTERN}'.")
    
    df = pd.concat([pd.read_csv(f) for f in file_list], ignore_index=True)
    lux_cal_df = pd.read_csv(LUX_CALIBRATION_FILE)
    print(f"Loaded {len(df)} rows from {len(file_list)} file(s).")

    df = pd.merge(df, lux_cal_df, left_on='sensor', right_on='DeviceName', how='left')
    df['lux_factor'].fillna(1.0, inplace=True)
    df['cal_lux'] = df['raw_lux'] * df['lux_factor']
    
    spectral_cols = [f'raw_ch{i}' for i in range(1, 19)]
    df['max_spectral_count'] = df[spectral_cols].max(axis=1)
    df['S_time_sec'] = df['S_time'] * 2.8 * 2.0 / 1000.0
    
    df_filtered = df[
        (df['cal_lux'] >= MINIMUM_LUX_THRESHOLD) &
        (df['max_spectral_count'] < SATURATION_THRESHOLD)
    ].copy()
    
    print(f"Filtered to {len(df_filtered)} rows.")
    return df_filtered

def generate_optimal_points(df):
    df['lux_bin'] = (df['cal_lux'] // ILLUMINANCE_BIN_WIDTH) * ILLUMINANCE_BIN_WIDTH
    
    optimal_points = []
    for (sensor_name, bin_val), group in df.groupby(['sensor', 'lux_bin']):
        if len(group) >= 2 and group['max_spectral_count'].min() < TARGET_ADC_COUNTS and group['max_spectral_count'].max() > TARGET_ADC_COUNTS:
            sorted_group = group.sort_values('max_spectral_count').drop_duplicates(subset=['max_spectral_count'])
            optimal_time = np.interp(TARGET_ADC_COUNTS, sorted_group['max_spectral_count'], sorted_group['S_time_sec'])
            avg_lux = group['cal_lux'].mean()
            optimal_points.append({'sensor': sensor_name, 'illuminance': avg_lux, 'optimal_time_sec': optimal_time})
            
    df_optimal = pd.DataFrame(optimal_points)
    if df_optimal.empty:
        sys.exit("ERROR: Could not generate optimal points.")
        
    print(f"Generated {len(df_optimal)} optimal data points.")
    return df_optimal

def power_law(x, a, b):
    return a * np.power(x, b)

def calculate_r_squared(y_actual, y_predicted):
    residuals = y_actual - y_predicted
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((y_actual - np.mean(y_actual))**2)
    return 1 - (ss_res / ss_tot) if ss_tot != 0 else 1.0

if __name__ == "__main__":
    
    df_filtered = load_and_prepare_data()
    df_optimal = generate_optimal_points(df_filtered)

    initial_points = len(df_optimal)
    df_optimal = df_optimal[df_optimal['illuminance'] <= MAXIMUM_LUX_THRESHOLD].copy()
    print(f"Filtered optimal points from {initial_points} to {len(df_optimal)} (removed values > {MAXIMUM_LUX_THRESHOLD} lux).")
    
    if df_optimal.empty:
        sys.exit("ERROR: No points remain after filtering.")
    
    try:
        popt_master, _ = curve_fit(power_law, df_optimal['illuminance'], df_optimal['optimal_time_sec'])
        a_master, b_master = popt_master
    except RuntimeError:
        sys.exit("ERROR: Could not fit power-law model.")

    y_actual = df_optimal['optimal_time_sec']
    y_predicted = power_law(df_optimal['illuminance'], a_master, b_master)
    r_squared = calculate_r_squared(y_actual, y_predicted)

    print("\n" + "="*50)
    print("MODEL PARAMETERS AND ERROR METRICS")
    print("="*50)
    print(f"  Coefficient 'a': {a_master:.4f}")
    print(f"  Coefficient 'b': {b_master:.4f}")
    print(f"  R-squared (R²):  {r_squared:.4f}")
    print("="*50)

    OUTPUT_DIR.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 7))

    ax.scatter(df_optimal['illuminance'] / 1000, df_optimal['optimal_time_sec'], 
            c='cornflowerblue', alpha=0.6, label='Optimal Data Points')
        
    x_smooth = np.linspace(df_optimal['illuminance'].min(), df_optimal['illuminance'].max(), 400)
    y_master_fit = power_law(x_smooth, a_master, b_master)

    master_fit_label = (
        f'Master Fit: '
        f'$y = {a_master:.3f} \\times x^{{{b_master:.3f}}} \\quad R^2 = {r_squared:.3f}$'
    )
    ax.plot(x_smooth / 1000, y_master_fit, color='black', linestyle='--', 
            label=master_fit_label)

    ax.set_title('Auto-Exposure Model Fit', fontsize=18)
    ax.set_xlabel('Illuminance (klux)', fontsize=14)
    ax.set_ylabel('Optimal Integration Time (sec)', fontsize=14)
    ax.legend(loc='upper right', fontsize=12)
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.set_ylim(bottom=0)

    plt.savefig(OUTPUT_DIR / "final_model_fit.png", dpi=150, bbox_inches='tight')
    plt.close()

    print("Model fit plot saved.")
    print("Complete.")