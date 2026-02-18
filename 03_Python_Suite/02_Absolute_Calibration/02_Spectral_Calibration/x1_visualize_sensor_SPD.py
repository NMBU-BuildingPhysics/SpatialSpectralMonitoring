# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Sensor calibration and responsivity analysis for AS7265x and AS7331 spectral sensors
# Generates visualization of 21-channel spectral responses (AS7331 UV + AS7265x VIS-NIR) organized by sensor chipset.
# ==============================================================================

import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt

CWD = Path.cwd()
SPD_DIR = CWD / "0_SPD_Reference"
ANALYSIS_PLOTS_DIR = CWD / "x1_Analysis_Plots"
ANALYSIS_PLOTS_DIR.mkdir(exist_ok=True)

AS7265X_FILE = SPD_DIR / "AS7265x" / "SPD_AS7265x.csv"
UVA_FILE = SPD_DIR / "AS7331" / "SPD_AS7331_uva.csv"
UVB_FILE = SPD_DIR / "AS7331" / "SPD_AS7331_uvb.csv"
UVC_FILE = SPD_DIR / "AS7331" / "SPD_AS7331_uvc.csv"

PLOT_X_MIN = 200
PLOT_X_MAX = 1000
OUTPUT_FILENAME = "x1_spectral_sensor_response.png"

CHIP_MAP = {
    'R': 'AS72651', 'S': 'AS72651', 'T': 'AS72651', 
    'U': 'AS72651', 'V': 'AS72651', 'W': 'AS72651',
    'G': 'AS72652', 'H': 'AS72652', 'I': 'AS72652', 
    'J': 'AS72652', 'K': 'AS72652', 'L': 'AS72652',
    'A': 'AS72653', 'B': 'AS72653', 'C': 'AS72653', 
    'D': 'AS72653', 'E': 'AS72653', 'F': 'AS72653',
    'UVA': 'AS7331', 'UVB': 'AS7331', 'UVC': 'AS7331',
}

COLOR_MAP = {
    'AS72651': 'limegreen',
    'AS72652': 'red',
    'AS72653': 'dodgerblue',
    'AS7331':  'darkviolet'
}

CSV_TO_DATASHEET_LETTER_MAP = {
    'ch1': 'A', 'ch2': 'B', 'ch3': 'C', 'ch4': 'D', 'ch5': 'E', 'ch6': 'F',
    'ch7': 'R', 'ch8': 'S', 'ch9': 'T', 'ch10': 'U', 'ch11': 'V', 'ch12': 'W',
    'ch13': 'G', 'ch14': 'H', 'ch15': 'I', 'ch16': 'J', 'ch17': 'K', 'ch18': 'L'
}

DATASHEET_LETTER_TO_WAVELENGTH_MAP = {
    'UVC': 260, 'UVB': 300, 'UVA': 360, 'A': 410, 'B': 435, 'C': 460, 
    'D': 485, 'E': 510, 'F': 535, 'G': 560, 'H': 585, 'I': 645, 'J': 705, 
    'K': 900, 'L': 940, 'R': 610, 'S': 680, 'T': 730, 'U': 760, 'V': 810, 'W': 860,
}


def load_all_spectral_data():
    sensor_files = {
        'uvc_df': pd.read_csv(UVC_FILE),
        'uvb_df': pd.read_csv(UVB_FILE),
        'uva_df': pd.read_csv(UVA_FILE),
        'as7265x_df': pd.read_csv(AS7265X_FILE)
    }
    
    all_channels_data = []
    
    all_channels_data.append({'df': sensor_files['uvc_df'], 'col': sensor_files['uvc_df'].columns[1], 'datasheet_letter': 'UVC'})
    all_channels_data.append({'df': sensor_files['uvb_df'], 'col': sensor_files['uvb_df'].columns[1], 'datasheet_letter': 'UVB'})
    all_channels_data.append({'df': sensor_files['uva_df'], 'col': sensor_files['uva_df'].columns[1], 'datasheet_letter': 'UVA'})

    for csv_col_name in sensor_files['as7265x_df'].columns[1:]:
        if csv_col_name in CSV_TO_DATASHEET_LETTER_MAP:
            datasheet_letter = CSV_TO_DATASHEET_LETTER_MAP[csv_col_name]
            all_channels_data.append({'df': sensor_files['as7265x_df'], 'col': csv_col_name, 'datasheet_letter': datasheet_letter})
            
    for channel in all_channels_data:
        letter = channel['datasheet_letter']
        channel['center_wl'] = DATASHEET_LETTER_TO_WAVELENGTH_MAP.get(letter)
        chip_name = CHIP_MAP.get(letter)
        channel['chip'] = chip_name
        channel['color'] = COLOR_MAP.get(chip_name)

    return sorted(all_channels_data, key=lambda x: x['center_wl'])


def create_datasheet_style_plot(channel_data):
    fig, ax = plt.subplots(figsize=(20, 10))

    for channel in channel_data:
        df = channel['df']
        response_col_name = channel['col']
        
        response_data = df[response_col_name]
        max_response = response_data.max()
        normalized_response = response_data / max_response if max_response > 0 else response_data
        
        ax.plot(df.iloc[:, 0], normalized_response, 
                color=channel['color'], linewidth=2.5)

    ax.set_title('21-Channel Spectral Response (AS7331 + AS7265x)', fontsize=24, pad=20)
    ax.set_xlabel('Wavelength (nm)', fontsize=18)
    ax.set_ylabel('Normalized Response', fontsize=18)
    
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.set_xlim(PLOT_X_MIN, PLOT_X_MAX)
    ax.set_ylim(-0.05, 1.1)
    ax.tick_params(axis='both', which='major', labelsize=14)

    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], color=COLOR_MAP['AS7331'], lw=4, label='AS7331'),
        Line2D([0], [0], color=COLOR_MAP['AS72653'], lw=4, label='AS72653'),
        Line2D([0], [0], color=COLOR_MAP['AS72652'], lw=4, label='AS72652'),
        Line2D([0], [0], color=COLOR_MAP['AS72651'], lw=4, label='AS72651')
    ]
    ax.legend(handles=legend_elements, title='Sensor Chipset', fontsize=16, title_fontsize=18, loc='upper right')

    output_path = ANALYSIS_PLOTS_DIR / OUTPUT_FILENAME
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\n Plot saved successfully to: {output_path}")


if __name__ == "__main__":
    print("--- Starting Datasheet-Style Visualization Script ---")
    try:
        all_channel_data = load_all_spectral_data()
        create_datasheet_style_plot(all_channel_data)
        print("--- Script finished successfully. ---")
    except Exception as e:
        print(f"\n ERROR: An unexpected error occurred: {e}")