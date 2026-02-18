# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Analyzes the relationship between TSL2591 Lux readings and optimal spectral integration times.
# Finding outlier measurement sweeps based on data distribution analysis.
# ==============================================================================

import pandas as pd
import numpy as np
import sys
from pathlib import Path
import glob
import os

INPUT_FILE_PATTERN = "1_a_merged_data/master_sweep_data*.csv"
IQR_MULTIPLIER = 2.0
MINIMUM_K_VALUE_THRESHOLD = 0.00017
MINIMUM_LUX_THRESHOLD = 5.0

base_folder = Path(__file__).parent
analysis_output_folder = base_folder / "2_a_outliers"
os.makedirs(analysis_output_folder, exist_ok=True)
OUTPUT_CSV_FILE = analysis_output_folder / "outliers_to_check.csv"

file_list = glob.glob(INPUT_FILE_PATTERN)
if not file_list: sys.exit(f"ERROR: No files found matching '{INPUT_FILE_PATTERN}'.")
df = pd.concat([pd.read_csv(f) for f in file_list], ignore_index=True)

df['raw_lux'] = pd.to_numeric(df['raw_lux'], errors='coerce')
df.dropna(subset=['raw_lux'], inplace=True)
df = df[df['raw_lux'] >= MINIMUM_LUX_THRESHOLD].copy()
if df.empty: sys.exit("ERROR: No valid data found.")

spectral_cols = [f'raw_ch{i}' for i in range(1, 19)]
df['max_spectral_count'] = df[spectral_cols].max(axis=1)
df['k_value'] = df['max_spectral_count'] / (df['S_gain'] * df['raw_lux'] * df['S_time'] * 2.8 * 2.0)
df.replace([np.inf, -np.inf], np.nan, inplace=True)
df.dropna(subset=['k_value'], inplace=True)

df['sweep_id'] = df['sensor'] + '_' + df['date'] + '_' + df['time']

outlier_sweep_ids = set()
print("Finding outlier sweeps for each sensor...")
for sensor_name, sensor_group in df.groupby('sensor'):
    Q1 = sensor_group['k_value'].quantile(0.25)
    Q3 = sensor_group['k_value'].quantile(0.75)
    IQR = Q3 - Q1
    lower_bound = Q1 - (IQR_MULTIPLIER * IQR)
    upper_bound = Q3 + (IQR_MULTIPLIER * IQR)
    outlier_points = sensor_group[(sensor_group['k_value'] < lower_bound) | (sensor_group['k_value'] > upper_bound)]
    high_value_outliers = outlier_points[outlier_points['k_value'] >= MINIMUM_K_VALUE_THRESHOLD]
    if not high_value_outliers.empty:
        outlier_sweep_ids.update(high_value_outliers['sweep_id'].unique())

if not outlier_sweep_ids:
    print("Analysis complete. No significant outliers found.")
    with open(OUTPUT_CSV_FILE, 'w', newline='') as f:
        f.write("No outliers found.\n")
    sys.exit()

df_outliers = df[df['sweep_id'].isin(outlier_sweep_ids)]
df_report = df_outliers.drop_duplicates(subset=['sweep_id'], keep='first').copy()

try:
    df_report['datetime_obj'] = pd.to_datetime(df_report['date'] + ' ' + df_report['time'])
    df_report['timestamp_str'] = df_report['datetime_obj'].dt.strftime('%Y%m%d_%H%M%S')
except Exception as e:
    sys.exit(f"ERROR: Could not parse date/time. Details: {e}")

df_report['image_filename'] = 'image_' + df_report['timestamp_str'] + '_' + df_report['sensor'] + '.jpeg'
print(f"Found {len(df_report)} unique outlier sweeps.")

os.makedirs(Path(OUTPUT_CSV_FILE).parent, exist_ok=True)
columns_to_save = ['timestamp_str', 'sensor', 'raw_lux', 'max_spectral_count', 'k_value', 'image_filename']
df_report[columns_to_save].to_csv(OUTPUT_CSV_FILE, index=False)
print(f"Saved to: {OUTPUT_CSV_FILE}")
print("Run '2_b_review_outliers.py' to review the outliers.")