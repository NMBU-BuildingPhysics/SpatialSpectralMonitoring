# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Analyzes the relationship between TSL2591 Lux readings and optimal spectral integration times.
# Merge CSV files from sweep measurements into a single master CSV file.
# ==============================================================================

import os
import csv
import re
from pathlib import Path

base_folder = Path(__file__).parent
dump_folder = base_folder / "1_a_merged_data"
dump_folder.mkdir(exist_ok=True)

headers = [
    "date", "time", "sensor",
    "S_gain", "S_time", "U_gain", "U_time", "I_gain", "I_time",
    "temperature", "humidity", "raw_lux",
    "raw_uvc", "raw_uvb", "raw_uva",
    "raw_ch1", "raw_ch2", "raw_ch3", "raw_ch4", "raw_ch5", "raw_ch6",
    "raw_ch7", "raw_ch8", "raw_ch9", "raw_ch10", "raw_ch11", "raw_ch12",
    "raw_ch13", "raw_ch14", "raw_ch15", "raw_ch16", "raw_ch17", "raw_ch18"
]

output_file = dump_folder / "master_sweep_data1.csv"

with open(output_file, 'w', newline='') as out_csv:
    writer = csv.writer(out_csv)
    writer.writerow(headers)

    for filename in os.listdir(base_folder):
        if filename.startswith("sweep_") and filename.endswith(".csv"):
            match = re.match(r'sweep_(\d{8})_(\d{6})_(sensor\d{2})\.csv', filename)
            if match:
                date_str, time_str, sensor_name = match.groups()
                filepath = base_folder / filename

                with open(filepath, 'r', newline='') as f:
                    reader = csv.reader(f)
                    next(reader, None)
                    for row in reader:
                        if row and len(row) == len(headers) - 3:
                            excel_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                            excel_time = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:]}"
                            writer.writerow([excel_date, excel_time, sensor_name] + row)
