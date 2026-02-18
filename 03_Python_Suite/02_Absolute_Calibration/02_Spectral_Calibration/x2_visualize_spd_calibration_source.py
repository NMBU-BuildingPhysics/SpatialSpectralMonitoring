# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Sensor calibration and responsivity analysis for AS7265x and AS7331 spectral sensors
# Loads, normalizes, and visualizes sensor spectral response curves with crosstalk
# ==============================================================================

import pandas as pd
import numpy as np
import sys
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.colors import Normalize

def load_spd_data(filepath, file_description):
    print(f"  - Loading {file_description} from: {filepath.name}")
    try:
        df = pd.read_csv(filepath)
        df.rename(columns={df.columns[0]: 'Wavelength'}, inplace=True)
        return df
    except FileNotFoundError:
        print(f"\nFATAL ERROR: Cannot find required data file: {filepath}")
        sys.exit(1)
    except Exception as e:
        print(f"\nFATAL ERROR: Could not read or process file {filepath}. Error: {e}")
        sys.exit(1)

CWD = Path.cwd()
SPD_DIR = CWD / "0_SPD_Reference"
ANALYSIS_PLOTS_DIR = CWD / "x2_Analysis_Plots"
ANALYSIS_PLOTS_DIR.mkdir(exist_ok=True)

SUN2000_FILE = SPD_DIR / "Sun2000" / "SPD_sun2000_Simulator.csv"  #Change to correct calibration source
AS7265X_FILE = SPD_DIR / "AS7265x" / "SPD_AS7265x.csv"
UVA_FILE = SPD_DIR / "AS7331" / "SPD_AS7331_uva.csv"
UVB_FILE = SPD_DIR / "AS7331" / "SPD_AS7331_uvb.csv"
UVC_FILE = SPD_DIR / "AS7331" / "SPD_AS7331_uvc.csv"

CSV_TO_DATASHEET_LETTER_MAP = {
    'ch1': 'A', 'ch2': 'B', 'ch3': 'C', 'ch4': 'D', 'ch5': 'E', 'ch6': 'F',
    'ch7': 'R', 'ch8': 'S', 'ch9': 'T', 'ch10': 'U', 'ch11': 'V', 'ch12': 'W',
    'ch13': 'G', 'ch14': 'H', 'ch15': 'I', 'ch16': 'J', 'ch17': 'K', 'ch18': 'L'
}

DATASHEET_LETTER_TO_WAVELENGTH_MAP = {
    'UVC': 260, 'UVB': 300, 'UVA': 360,
    'A': 410, 'B': 435, 'C': 460, 'D': 485, 'E': 510, 'F': 535,
    'G': 560, 'H': 585, 'I': 645, 'J': 705, 'K': 900, 'L': 940,
    'R': 610, 'S': 680, 'T': 730, 'U': 760, 'V': 810, 'W': 860,
}

print(f"Loading SPD data from base folder: {SPD_DIR}\n")
source_df = load_spd_data(SUN2000_FILE, "Reference Light Source")
source_max_val = source_df.iloc[:, 1].max()
source_df['Normalized'] = source_df.iloc[:, 1] / source_max_val if source_max_val > 0 else 0.0

sensor_files = {
    'uvc_df': load_spd_data(UVC_FILE, "AS7331 UVC Sensor"),
    'uvb_df': load_spd_data(UVB_FILE, "AS7331 UVB Sensor"),
    'uva_df': load_spd_data(UVA_FILE, "AS7331 UVA Sensor"),
    'as7265x_df': load_spd_data(AS7265X_FILE, "AS7265x VIS-NIR Sensor")
}

all_channels_data = []
all_channels_data.append({'df': sensor_files['uvc_df'], 'col': sensor_files['uvc_df'].columns[1], 'center_wl': DATASHEET_LETTER_TO_WAVELENGTH_MAP['UVC']})
all_channels_data.append({'df': sensor_files['uvb_df'], 'col': sensor_files['uvb_df'].columns[1], 'center_wl': DATASHEET_LETTER_TO_WAVELENGTH_MAP['UVB']})
all_channels_data.append({'df': sensor_files['uva_df'], 'col': sensor_files['uva_df'].columns[1], 'center_wl': DATASHEET_LETTER_TO_WAVELENGTH_MAP['UVA']})

for csv_col_name in sensor_files['as7265x_df'].columns[1:]:
    if csv_col_name in CSV_TO_DATASHEET_LETTER_MAP:
        datasheet_letter = CSV_TO_DATASHEET_LETTER_MAP[csv_col_name]
        if datasheet_letter in DATASHEET_LETTER_TO_WAVELENGTH_MAP:
            center_wl = DATASHEET_LETTER_TO_WAVELENGTH_MAP[datasheet_letter]
            all_channels_data.append({'df': sensor_files['as7265x_df'], 'col': csv_col_name, 'center_wl': center_wl})

all_channels_data.sort(key=lambda x: x['center_wl'])
print("\nAll data loaded and sorted. Generating final visualization...")

fig, ax = plt.subplots(figsize=(20, 10))
min_wl, max_wl = 260, 940
cmap = cm.viridis
norm = Normalize(vmin=min_wl, vmax=max_wl)

ax.fill_between(
    source_df['Wavelength'], 0, source_df['Normalized'],
    color='grey', alpha=0.35, label='Reference Source (SUN2000)'
)
ax.plot(
    source_df['Wavelength'], source_df['Normalized'],
    color='dimgrey', linewidth=1.5
)

for channel in all_channels_data:
    df, center_wl, response_col_name = channel['df'], channel['center_wl'], channel['col']
    response_data = df[response_col_name]
    max_response = response_data.max()
    normalized_response = response_data / max_response if max_response > 0 else response_data
    ax.plot(
        df['Wavelength'], normalized_response, label=f"{center_wl} nm",
        color=cmap(norm(center_wl)), linewidth=2.5
    )

ax.set_title('Combined Spectral Response of All Sensor Channels', fontsize=22, pad=20)
ax.set_xlabel('Wavelength (nm)', fontsize=16, labelpad=10)
ax.set_ylabel('Normalized Response', fontsize=16, labelpad=10)
ax.grid(True, which='major', linestyle='--', linewidth=0.7, alpha=0.8)
ax.set_xlim(200, 1100)
ax.set_ylim(-0.02, 1.1)

handles, labels = ax.get_legend_handles_labels()
try:
    source_idx = labels.index('Reference Source (SUN2000)')
    order = [source_idx] + [i for i, _ in enumerate(labels) if i != source_idx]
    ax.legend(
        [handles[idx] for idx in order], [labels[idx] for idx in order],
        title='Sensor Channels', bbox_to_anchor=(1.02, 1), loc='upper left',
        borderaxespad=0., fontsize=11, title_fontsize=13, ncol=2
    )
except ValueError:
    ax.legend(
        title='Sensor Channels', bbox_to_anchor=(1.02, 1), loc='upper left',
        borderaxespad=0., fontsize=11, title_fontsize=13, ncol=2
    )

output_filename = ANALYSIS_PLOTS_DIR / 'x2_spd_visualization_with_source.png'
plt.tight_layout(rect=[0, 0, 0.85, 1])
plt.savefig(output_filename, dpi=300)
plt.close(fig)

print(f"\nVisualization script finished successfully!")
print(f"Final plot with outlined reference saved to '{output_filename}'")