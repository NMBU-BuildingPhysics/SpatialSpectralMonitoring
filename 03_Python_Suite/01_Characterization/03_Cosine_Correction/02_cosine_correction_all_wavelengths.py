# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Cosine Correction visualization based on measured data
# Generates a grid of polar plots comparing sensor response
# ==============================================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "0_Measurements"
OUTPUT_DIR = BASE_DIR / "02_cosine_correction_all_wavelengths"
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


def create_wavelength_grid(input_csv, output_path):
    try:
        df_sensor = pd.read_csv(input_csv)
    except FileNotFoundError:
        print(f"Error: {input_csv} not found")
        return

    temp_coeffs_df = pd.read_csv(THERMAL_COEFFS_PATH, index_col='Channel')

    # Filter to only calibrated wavelength columns (exclude cal_lux which is derived)
    wavelength_columns = [col for col in df_sensor.columns if col.startswith('cal_') and col != 'cal_lux']

    # Apply temperature correction to each row before averaging
    df_sensor = apply_temperature_correction(df_sensor, wavelength_columns, temp_coeffs_df)

    # Group by angle and calculate mean across all readings for each wavelength
    df_sensor = df_sensor.groupby('Angle')[wavelength_columns].mean()

    # Generate ideal intensity values based on ideal cosine law, normalized to 100 at 0°
    angles = df_sensor.index.values
    ideal_intensity = np.cos(np.deg2rad(angles)) * 100

    # Normalize each wavelength column relative to its own value at 0° (reference)
    ref_idx = list(angles).index(0)
    for col in df_sensor.columns:
        ref_val = df_sensor[col].iloc[ref_idx]
        if ref_val != 0:
            df_sensor[col] = (df_sensor[col] / ref_val) * 100

    angles_deg = df_sensor.index.values
    angles_rad = np.deg2rad(angles_deg)
    full_angles = np.concatenate((-angles_rad[::-1][:-1], angles_rad))
    full_ideal_intensity = np.concatenate((ideal_intensity[::-1][:-1], ideal_intensity))

    nrows, ncols = 7, 3
    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(8, 15),
        subplot_kw={'projection': 'polar'}
    )
    axes_flat = axes.flatten()

    for i, wavelength in enumerate(df_sensor.columns):
        ax = axes_flat[i]

        sensor_values = df_sensor[wavelength].values
        full_sensor_intensity = np.concatenate((sensor_values[::-1][:-1], sensor_values))

        ax.plot(full_angles, full_sensor_intensity, color='blue', linewidth=1.0, label='Sensor')
        ax.plot(full_angles, full_ideal_intensity, color='deeppink', linestyle='--', linewidth=1.2, label='Ideal Value')

        diff = sensor_values - ideal_intensity
        rmse = np.sqrt(np.mean(diff**2))

        theta_pos = np.deg2rad(45)
        r_pos = 200
        ax.text(theta_pos, r_pos, f"RMSE: {rmse:.2f}",
                ha='center', va='center', fontsize=6,
                bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='gray', lw=0.5, alpha=0.8))

        ax.set_theta_zero_location('N')
        ax.set_theta_direction(-1)
        ax.set_thetamin(-90)
        ax.set_thetamax(90)
        ax.set_rmax(110)
        ax.set_yticklabels([])
        ax.grid(True, linestyle='-', color='gray', alpha=0.5, linewidth=0.5)
        ax.spines['polar'].set_linewidth(0.7)
        ax.set_title(f"{wavelength} nm", fontsize=8, y=0.95)

        tick_angles = np.arange(-90, 91, 10)
        tick_labels = [f'{abs(angle)}' if angle % 10 == 0 and angle != 0 else '' for angle in tick_angles]
        ax.set_thetagrids(tick_angles, labels=tick_labels, fontsize=4)

    fig.subplots_adjust(
        top=0.98,
        bottom=0.02,
        wspace=0.2,
        hspace=0.7
    )

    plt.savefig(output_path, dpi=600, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    input_file = INPUT_DIR / 'sensor_data.csv'
    output_file = OUTPUT_DIR / "02_cosine_correction_all_wavelengths.png"
    create_wavelength_grid(input_file, output_file)