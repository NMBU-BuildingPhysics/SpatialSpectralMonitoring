# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Absolute lux calibration workflow for spectral sensor array.
# Calibrates lux measurements using pre-determined temperature coefficients.
# ==============================================================================

import pandas as pd
import sys
from pathlib import Path

base_folder = Path(__file__).parent
MEASUREMENTS_FILE = base_folder / "0_Measurements" / "sensor_data.csv"
LUX_TEMP_COEFFS = {'a': 2.594556194e-06, 'b': 0.002965622208, 'c': 0.9260917036} # Temperature correction coefficients from 2_temp_coeffs
MAX_TIMESTAMP_DELTA_MINUTES = 5  # Fallback to reference mean if no match within this window

try:
    df = pd.read_csv(MEASUREMENTS_FILE)
except FileNotFoundError:
    print(f"ERROR: Cannot find '{MEASUREMENTS_FILE}'."); sys.exit()

# Load reference lux from restructured_cal file
ref_files = sorted((base_folder / "0_Measurements").glob("restructured_cal-all*.csv"))
if not ref_files:
    print("ERROR: No 'restructured_cal-all*.csv' reference file found in 0_Measurements."); sys.exit()
ref_file = ref_files[-1]  # Use the most recent file
print(f"Using reference file: {ref_file.name}")
try:
    df_ref = pd.read_csv(ref_file).copy()
except FileNotFoundError:
    print(f"ERROR: Cannot find '{ref_file}'."); sys.exit()
print(f"Loaded {len(df_ref)} reference rows.")

# Parse timestamps
df_ref['_ts'] = pd.to_datetime(df_ref['Modify Time'])
ref_date = df_ref['_ts'].dt.date.iloc[0]
df = df.copy()
df['_ts'] = pd.to_datetime(ref_date.strftime('%Y-%m-%d') + ' ' + df['time'].str.strip())

# Sort both by timestamp for merge_asof
df_ref_sorted = df_ref[['_ts', 'Photopic Lux']].sort_values('_ts').reset_index(drop=True)
df_sorted = df.sort_values('_ts').reset_index(drop=True)

# Match each sensor row to the nearest reference timestamp
df_merged = pd.merge_asof(df_sorted, df_ref_sorted.rename(columns={'_ts': '_ts_ref', 'Photopic Lux': 'ref_lux'}),
                          left_on='_ts', right_on='_ts_ref', direction='nearest')

# Compute match delta and fall back to reference mean where delta exceeds tolerance
tolerance = pd.Timedelta(minutes=MAX_TIMESTAMP_DELTA_MINUTES)
ref_mean_lux = df_ref_sorted['Photopic Lux'].mean()
df_merged['delta'] = (df_merged['_ts'] - df_merged['_ts_ref']).abs()
df_merged['ref_lux'] = df_merged['ref_lux'].astype(float)
outside = df_merged['delta'] > tolerance
if outside.any():
    bad_devices = df_merged.loc[outside, 'device'].unique()
    print(f"WARNING: {outside.sum()} row(s) for {list(bad_devices)} have no reference within "
          f"{MAX_TIMESTAMP_DELTA_MINUTES} min — using reference mean ({ref_mean_lux:.0f} lux) as fallback.")
    df_merged.loc[outside, 'ref_lux'] = ref_mean_lux

print(f"Timestamp match delta — median: {df_merged.loc[~outside, 'delta'].median()}, "
      f"max (within tolerance): {df_merged.loc[~outside, 'delta'].max()}")

a, b, c = LUX_TEMP_COEFFS['a'], LUX_TEMP_COEFFS['b'], LUX_TEMP_COEFFS['c']
df_merged['temp_correction_factor'] = (a * df_merged['temperature']**2) + (b * df_merged['temperature']) + c
df_merged['temp_corrected_lux'] = df_merged['raw_lux'] / df_merged['temp_correction_factor']

df_merged['lux_factor'] = df_merged['ref_lux'] / df_merged['temp_corrected_lux']

df_avg = df_merged.groupby("device", sort=True)["lux_factor"].mean().reset_index()

cpp_lines = []
cpp_lines.append("const std::map<std::string, float> universalLuxFactors = {")
for _, row in df_avg.iterrows():
    device_name = row["device"].lower()
    cpp_lines.append(f'    {{"{device_name}", {row["lux_factor"]:.5f}f}},')
cpp_lines.append("};")
cpp_code_block = "\n".join(cpp_lines)

output_message = ("\n\n" + "="*70 + "\n=== C++ LUX CALIBRATION FACTOR MAP ===\n" + "="*70 + "\n" +
    cpp_code_block + "\n" + "="*70)
print(output_message)

output_folder = base_folder / "2_Results"
output_folder.mkdir(exist_ok=True)
output_file = output_folder / "calibration_results.txt"
with open(output_file, 'w') as f:
    f.write(output_message)
print(f"\nCalibration results saved to: {output_file}")