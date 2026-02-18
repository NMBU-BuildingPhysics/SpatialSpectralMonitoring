# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Narrowband validation analysis for spectral sensor calibration
# Merge and interpolate the reference spectral power distribution (SPD) files for AS7265x and AS7331 sensors
# ==============================================================================

import pandas as pd
import numpy as np
from pathlib import Path

SPD_DIR = Path.cwd() / "0_SPD_Reference"
OUTPUT_FILE = Path.cwd() / "x1_Analysis_Plots" / "full_sensor_response.csv"
OUTPUT_FILE.parent.mkdir(exist_ok=True)

WAVELENGTH_MIN = 200
WAVELENGTH_MAX = 1100
WAVELENGTH_STEP = 1

def interpolate_and_normalize(wavelength, response, new_wavelength_axis):
    interpolated = np.interp(new_wavelength_axis, wavelength, response)
    max_val = interpolated.max()
    if max_val > 0:
        interpolated /= max_val
    return interpolated

def process_sensor_file(filepath, prefix, new_wavelength_axis):
    if not filepath.exists():
        print(f"Warning: File not found, skipping: {filepath}")
        return {}
    
    print(f"  -> Processing {filepath.name}...")
    df = pd.read_csv(filepath)
    original_wl = df.iloc[:, 0]
    
    interpolated_data = {}
    for col_name in df.columns[1:]:
        original_response = df[col_name]
        interpolated_response = interpolate_and_normalize(
            original_wl, original_response, new_wavelength_axis
        )
        
        if 'AS7265x' in prefix:
            final_col_name = f"AS7265x_{col_name.upper()}"
        else:
            final_col_name = f"AS7331_{col_name.upper()}"
        
        interpolated_data[final_col_name] = interpolated_response
    
    return interpolated_data

def main():
    print("--- Starting: Merging sensor response files ---")
    
    new_wavelength_axis = np.arange(WAVELENGTH_MIN, WAVELENGTH_MAX + WAVELENGTH_STEP, WAVELENGTH_STEP)
    
    files_to_process = {
        'AS7265x': SPD_DIR / "AS7265x" / "SPD_AS7265x.csv",
        'AS7331_UVA': SPD_DIR / "AS7331" / "SPD_AS7331_uva.csv",
        'AS7331_UVB': SPD_DIR / "AS7331" / "SPD_AS7331_uvb.csv",
        'AS7331_UVC': SPD_DIR / "AS7331" / "SPD_AS7331_uvc.csv"
    }
    
    all_interpolated_data = {}
    for prefix, filepath in files_to_process.items():
        sensor_data = process_sensor_file(filepath, prefix, new_wavelength_axis)
        all_interpolated_data.update(sensor_data)
    
    if not all_interpolated_data:
        print("ERROR: No data was processed. Please check file paths.")
        return
    
    final_df = pd.DataFrame(all_interpolated_data, index=new_wavelength_axis)
    final_df.index.name = 'Wavelength'
    
    sorted_columns = sorted(final_df.columns, key=lambda x: (
        'AS7331' not in x,
        int(x.split('_CH')[-1]) if '_CH' in x else (0 if 'UVC' in x else (1 if 'UVB' in x else 2))
    ))
    final_df = final_df[sorted_columns]
    
    final_df.to_csv(OUTPUT_FILE)
    print(f"\nSuccess! Merged data saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()