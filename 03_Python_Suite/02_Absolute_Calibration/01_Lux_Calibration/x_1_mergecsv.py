# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Absolute lux calibration workflow for spectral sensor array.
# Helper script for preprocessing: merges multiple sensor CSV files into a single CSV file for temperature sweep data.
# ==============================================================================

import os
import csv
from pathlib import Path

base_folder = Path(__file__).parent
measurement_folder = base_folder / "0_Measurements"
sensor_time_frame = "20250721_113804"
headers = [
    "sensor",
    "S_gain", "S_time", "U_gain", "U_time", "I_gain", "I_time",
    "temperature", "humidity", "illuminance",
    "raw_uvc", "raw_uvb", "raw_uva",
    "raw_ch1", "raw_ch2", "raw_ch3", "raw_ch4", "raw_ch5", "raw_ch6", "raw_ch7", "raw_ch8", "raw_ch9",
    "raw_ch10", "raw_ch11", "raw_ch12", "raw_ch13", "raw_ch14", "raw_ch15", "raw_ch16", "raw_ch17", "raw_ch18",
    "cal_uvc", "cal_uvb", "cal_uva",
    "cal_ch1", "cal_ch2", "cal_ch3", "cal_ch4", "cal_ch5", "cal_ch6", "cal_ch7", "cal_ch8", "cal_ch9",
    "cal_ch10", "cal_ch11", "cal_ch12", "cal_ch13", "cal_ch14", "cal_ch15", "cal_ch16", "cal_ch17", "cal_ch18"
]

output_file = os.path.join(base_folder, "x_1_mergeCSV/lux_temp_sweep_data.csv")

with open(output_file, 'w', newline='') as out_csv:
    writer = csv.writer(out_csv)
    writer.writerow(headers)

    for i in range(1, 13):  # sensor01 to sensor12
        sensor_name = f"sensor{str(i).zfill(2)}"
        filename = f"{sensor_time_frame}_{sensor_name}.csv"
        filepath = os.path.join(measurement_folder, filename)

        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                for line in f:
                    if line.strip():
                        data = line.strip().split(',')
                        writer.writerow([sensor_name] + data)
        else:
            print(f"Warning: {filename} not found.")
