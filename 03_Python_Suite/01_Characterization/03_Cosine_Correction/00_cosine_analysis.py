#!/usr/bin/env python3
# ==============================================================================
# Quality Assurance: Cosine Correction Analysis
# ==============================================================================

import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "0_Measurements"
THERMAL_COEFFS_PATH = BASE_DIR.parent / "02_Thermal_Analysis" / "1_a_Generate_temp_Coeffs" / "temp_coeffs.csv"
REFERENCE_TEMPERATURE = 25.0

CAL_TO_COEFF = {
    'cal_uvc': 'UVC', 'cal_uvb': 'UVB', 'cal_uva': 'UVA',
    'cal_410nm': 'CH1',  'cal_435nm': 'CH2',  'cal_460nm': 'CH3',
    'cal_485nm': 'CH4',  'cal_510nm': 'CH5',  'cal_535nm': 'CH6',
    'cal_560nm': 'CH7',  'cal_585nm': 'CH8',  'cal_610nm': 'CH9',
    'cal_645nm': 'CH10', 'cal_680nm': 'CH11', 'cal_705nm': 'CH12',
    'cal_730nm': 'CH13', 'cal_760nm': 'CH14', 'cal_810nm': 'CH15',
    'cal_860nm': 'CH16', 'cal_900nm': 'CH17', 'cal_940nm': 'CH18',
}


def apply_temperature_correction(df, cal_cols, coeffs_df, ref_temp=REFERENCE_TEMPERATURE):
    df = df.copy()
    T = df['temperature'].values
    f_ref_cache = {}
    for col in cal_cols:
        ch = CAL_TO_COEFF.get(col)
        if ch is None or ch not in coeffs_df.index:
            continue
        a, b, c = coeffs_df.loc[ch, ['a', 'b', 'c']]
        if ch not in f_ref_cache:
            f_ref_cache[ch] = a * ref_temp**2 + b * ref_temp + c
        f_T = a * T**2 + b * T + c
        df[col] = df[col] * (f_ref_cache[ch] / f_T)
    return df


sensor_df = pd.read_csv(INPUT_DIR / 'sensor_data.csv')
temp_coeffs_df = pd.read_csv(THERMAL_COEFFS_PATH, index_col='Channel')
wavelength_columns = [col for col in sensor_df.columns if col.startswith('cal_') and col != 'cal_lux']

sensor_df = apply_temperature_correction(sensor_df, wavelength_columns, temp_coeffs_df)

sensor_df_wavelengths = sensor_df[['Angle'] + wavelength_columns]
sensor_by_angle = sensor_df_wavelengths.groupby('Angle')[wavelength_columns].mean()

# Calculate average intensity
average_sensor_intensity = sensor_by_angle.mean(axis=1).values
angles = sensor_by_angle.index.values

# Normalize
reference_value = average_sensor_intensity[angles == 0][0]
average_sensor_intensity = (average_sensor_intensity / reference_value) * 100

# Ideal
ideal_intensity = np.cos(np.deg2rad(angles)) * 100

# Analysis
rmse = np.sqrt(np.mean((average_sensor_intensity - ideal_intensity)**2))
mae = np.mean(np.abs(average_sensor_intensity - ideal_intensity))
correlation = np.corrcoef(average_sensor_intensity, ideal_intensity)[0, 1]

print("=" * 60)
print("COSINE CORRECTION QA ANALYSIS")
print("=" * 60)
print(f"\nRMSE (Root Mean Square Error): {rmse:.2f}%")
print(f"MAE (Mean Absolute Error): {mae:.2f}%")
print(f"Correlation Coefficient: {correlation:.6f}")
print(f"\nAngle | Ideal  | Sensor | Diff   | % Error")
print("-" * 50)
for i, angle in enumerate(angles):
    diff = average_sensor_intensity[i] - ideal_intensity[i]
    pct_err = (diff / ideal_intensity[i]) * 100 if ideal_intensity[i] != 0 else 0
    print(f"{angle:3.0f}° | {ideal_intensity[i]:6.2f} | {average_sensor_intensity[i]:6.2f} | {diff:+6.2f} | {pct_err:+6.2f}%")

print("\n" + "=" * 60)
print("INTERPRETATION:")
print("=" * 60)
if rmse < 3:
    print("✓ EXCELLENT: Sensor follows cosine law very closely (RMSE < 3%)")
elif rmse < 5:
    print("✓ GOOD: Sensor follows cosine law well (RMSE < 5%)")
elif rmse < 10:
    print("⚠ FAIR: Some deviation from cosine law (RMSE < 10%)")
else:
    print("✗ POOR: Significant deviation from cosine law (RMSE > 10%)")

print(f"\nThe sensor correlation with ideal cosine: {correlation:.4f}")
if correlation > 0.99:
    print("Perfect match with cosine law")
elif correlation > 0.98:
    print("Excellent correlation with cosine law")
elif correlation > 0.95:
    print("Very good correlation with cosine law")
else:
    print("Moderate correlation with cosine law")

print("\n" + "=" * 60)
