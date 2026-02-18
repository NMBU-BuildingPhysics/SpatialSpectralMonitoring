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

OUTPUT_DIR.mkdir(exist_ok=True)

sensor_df = pd.read_csv(INPUT_DIR / 'sensor_data.csv')
sensor_df.set_index('Angle', inplace=True)

average_sensor_intensity = sensor_df.mean(axis=1).values

data = {
    'Angle θ (°)': sensor_df.index.values,
    'Ideal intensity': [100, 98, 94, 87, 77, 64, 50, 34, 17, 0],
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