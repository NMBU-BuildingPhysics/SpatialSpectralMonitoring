# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Analyzes the relationship between TSL2591 Lux readings and optimal spectral integration times.
# Reviews identified outlier measurement sweeps and generates visualization outputs.
# ==============================================================================

import pandas as pd
import sys
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from pathlib import Path

base_folder = Path(__file__).parent
OUTLIER_CSV_FILE = base_folder / "2_a_outliers" / "outliers_to_check.csv"
IMAGE_FOLDER = base_folder / "0_measurements" / "image_files"
REVIEW_OUTPUT_FOLDER = base_folder / "2_b_outliers_data"
REVIEW_OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

try:
    df_outliers = pd.read_csv(OUTLIER_CSV_FILE)
    if len(df_outliers) < 2 and "No outliers" in df_outliers.iloc[0, 0]:
        print("No outliers were found. Nothing to review.")
        sys.exit()
except FileNotFoundError:
    sys.exit(f"ERROR: Cannot find '{OUTLIER_CSV_FILE}'. Run '2_a_find_outliers.py' first.")

df_outliers.sort_values(by='timestamp_str', ascending=False, inplace=True)
df_outliers.reset_index(drop=True, inplace=True)

print(f"Reviewing {len(df_outliers)} outliers (newest first)")
print(f"Images location: {IMAGE_FOLDER}\n")

for index, row in df_outliers.iterrows():
    image_path = IMAGE_FOLDER / row['image_filename']
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(f"Outlier #{index + 1} of {len(df_outliers)}", fontsize=16)
    
    if image_path.exists() and image_path.stat().st_size > 0:
        try:
            img = mpimg.imread(image_path)
            ax1.imshow(img)
            ax1.set_title(f"Image: {row['image_filename']}")
        except Exception as e:
            ax1.text(0.5, 0.5, f'Error loading image:\n{e}', ha='center', va='center')
            ax1.set_title("Image (Load Failed)")
    else:
        ax1.text(0.5, 0.5, 'Image not found or empty.', ha='center', va='center')
        ax1.set_title("Image (Missing)")
    ax1.axis('off')
    
    data_text = (f"Timestamp: {row['timestamp_str']}\n"
                 f"Sensor: {row['sensor']}\n\n"
                 f"Raw Lux: {row['raw_lux']:.2f}\n"
                 f"Max Spectral Count: {row['max_spectral_count']}\n"
                 f"K-Value: {row['k_value']:.6f}")
    ax2.text(0.05, 0.5, data_text, ha='left', va='center', fontsize=14, fontfamily='monospace')
    ax2.set_title("Measurement Data")
    ax2.axis('off')
    
    output_image_filename = REVIEW_OUTPUT_FOLDER / f"outlier_{index + 1:03d}_{row['sensor']}.png"
    plt.savefig(output_image_filename)
    plt.close()