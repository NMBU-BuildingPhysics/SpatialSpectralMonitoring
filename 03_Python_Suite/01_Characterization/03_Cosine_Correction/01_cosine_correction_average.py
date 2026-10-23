# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Cosine Correction visualization based on measured data.
# Generates a half-circle polar plot comparing average sensor response across all wavelengths
# against an ideal cosine (Lambertian) distribution.
# ==============================================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "0_Measurements"
OUTPUT_DIR = BASE_DIR / "01_cosine_correction_average"
THERMAL_COEFFS_PATH = BASE_DIR.parent / "02_Thermal_Analysis" / "1_a_Generate_temp_Coeffs" / "temp_coeffs.csv"
REFERENCE_TEMPERATURE = 25.0

OUTPUT_DIR.mkdir(exist_ok=True)

# Mapping from calibrated column names to thermal coefficient channel names
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
    """Correct cal values in-place to the reference temperature using polynomial model."""
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

# Filter to only calibrated wavelength columns (exclude cal_lux which is derived)
wavelength_columns = [col for col in sensor_df.columns if col.startswith('cal_') and col != 'cal_lux']

# Apply temperature correction to each row before averaging
sensor_df = apply_temperature_correction(sensor_df, wavelength_columns, temp_coeffs_df)

# Group by angle and calculate mean across all readings and wavelengths
sensor_df_wavelengths = sensor_df[['Angle'] + wavelength_columns]
sensor_by_angle = sensor_df_wavelengths.groupby('Angle')[wavelength_columns].mean()

# Calculate average intensity across all wavelengths for each angle
average_sensor_intensity = sensor_by_angle.mean(axis=1).values
angles = sensor_by_angle.index.values

# Normalize sensor to angle 0° as reference (100%)
reference_value = average_sensor_intensity[angles == 0][0]
average_sensor_intensity = (average_sensor_intensity / reference_value) * 100

# Generate ideal intensity values based on ideal cosine law, normalized to 100 at 0°
ideal_intensity = np.cos(np.deg2rad(angles)) * 100

data = {
    'Angle θ (°)': angles,
    'Ideal intensity': ideal_intensity,
    'Sensor': average_sensor_intensity
}
df = pd.DataFrame(data)


def create_half_polar_plot(df, output_path):
    angles_rad = np.deg2rad(df['Angle θ (°)'])
    full_angles = np.concatenate((-angles_rad[::-1][:-1], angles_rad))
    full_ideal_intensity = np.concatenate((df['Ideal intensity'][::-1][:-1], df['Ideal intensity']))
    full_sensor_intensity = np.concatenate((df['Sensor'][::-1][:-1], df['Sensor']))

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={'projection': 'polar'})

    ax.plot(full_angles, full_sensor_intensity, color='blue', linewidth=2.5, label='Sensor')
    ax.plot(full_angles, full_ideal_intensity, color='deeppink', linestyle='--', linewidth=2.5, label='Ideal Value')

    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)
    ax.set_thetamin(-90)
    ax.set_thetamax(90)

    tick_angles = np.arange(-90, 91, 10)
    tick_labels = [f'{abs(angle)}' for angle in tick_angles]
    ax.set_thetagrids(tick_angles, labels=tick_labels)

    ax.set_rmax(100)
    ax.set_rticks([0, 25, 50, 75, 100])
    ax.set_yticklabels([])
    ax.grid(True, linestyle='-', color='gray', alpha=0.5)

    for r, label in zip([0, 25, 50, 75, 100], ['', '25%', '50%', '75%', '']):
        ax.text(np.deg2rad(0), r, label, ha='center', va='center', fontsize=10)

    ax.set_title("Light Intensity Distribution", pad=-50, fontsize=16)
    ax.legend(loc='lower center', bbox_to_anchor=(0.5, 0.15), ncol=2, frameon=False, fontsize=12)

    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    output_file = OUTPUT_DIR / "01_cosine_correction_average.png"
    create_half_polar_plot(df, output_file)