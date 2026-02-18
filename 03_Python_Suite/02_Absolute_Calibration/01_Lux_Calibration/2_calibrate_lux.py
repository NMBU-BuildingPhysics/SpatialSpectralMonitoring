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
MEASUREMENTS_FILE = base_folder / "0_Measurements" / "Source - halogenlamp" / "master_light_measurements.csv"
REFERENCE_LUX_VALUE = 29524.5  # Reference lux value from calibrated lux meter
LUX_TEMP_COEFFS = {'a': -8.516361525e-06, 'b': 0.003498332197, 'c': 0.9175974081} # Temperature correction coefficients from 2_temp_coeffs

try:
    df = pd.read_csv(MEASUREMENTS_FILE)
except FileNotFoundError:
    print(f"ERROR: Cannot find '{MEASUREMENTS_FILE}'."); sys.exit()

a, b, c = LUX_TEMP_COEFFS['a'], LUX_TEMP_COEFFS['b'], LUX_TEMP_COEFFS['c']
df['temp_correction_factor'] = (a * df['temperature']**2) + (b * df['temperature']) + c
df['temp_corrected_lux'] = df['illuminance'] / df['temp_correction_factor']

df['lux_factor'] = REFERENCE_LUX_VALUE / df['temp_corrected_lux']

cpp_lines = []
cpp_lines.append("const std::map<std::string, float> universalLuxFactors = {")
for index, row in df.iterrows():
    device_name = row["DeviceName"].lower()
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