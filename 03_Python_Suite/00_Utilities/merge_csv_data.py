# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# CSV Merger: Merges multiple sensor data CSV files into a single file with a unified format.
# ==============================================================================

import os
import glob
import csv

# The headers for the final merged CSV file, as specified.
headers = [
    "date", "time", "sensor",
    "S_gain", "S_time", "U_gain", "U_time", "I_gain", "I_time",
    "temperature", "humidity", "cal_lux",
    "raw_uvc", "raw_uvb", "raw_uva",
    "raw_ch1", "raw_ch2", "raw_ch3", "raw_ch4", "raw_ch5", "raw_ch6",
    "raw_ch13", "raw_ch14", "raw_ch7", "raw_ch15", "raw_ch8", "raw_ch16",
    "raw_ch9", "raw_ch10", "raw_ch11", "raw_ch12", "raw_ch17", "raw_ch18",
    "cal_260nm", "cal_300nm", "cal_360nm", "cal_410nm", "cal_435nm", "cal_460nm",
    "cal_485nm", "cal_510nm", "cal_535nm", "cal_560nm", "cal_585nm", "cal_610nm",
    "cal_645nm", "cal_680nm", "cal_705nm", "cal_730nm", "cal_760nm", "cal_810nm",
    "cal_860nm", "cal_900nm", "cal_940nm"
]

output_filename = 'merged_sensor_data.csv'

def merge_sensor_files():
    """
    Finds, parses, and merges sensor CSV files into a single file.
    """
    csv_files = sorted(glob.glob('*_sensor*.csv'))

    if not csv_files:
        print("No sensor CSV files found in this directory.")
        return

    print(f"Found {len(csv_files)} files to merge. Starting process...")

    with open(output_filename, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.writer(outfile)
        writer.writerow(headers)

        for filename in csv_files:
            print(f"  -> Processing {filename}")
            try:
                base_name = os.path.splitext(os.path.basename(filename))[0]
                parts = base_name.split('_')
                
                date_str = parts[0]  # "20250730"
                time_str = parts[1]  # "090000"
                sensor_id = parts[2] # "sensor01"

                formatted_date = f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"
                formatted_time = f"{time_str[0:2]}:{time_str[2:4]}:{time_str[4:6]}"

                with open(filename, 'r', encoding='utf-8') as infile:
                    reader = csv.reader(infile)

                    for data_row in reader:
                        if not data_row:
                            continue

                        full_row = [formatted_date, formatted_time, sensor_id] + data_row
                        writer.writerow(full_row)

            except IndexError:
                print(f"    [WARNING] Could not parse filename '{filename}'. Skipping.")
            except Exception as e:
                print(f"    [ERROR] An error occurred while processing file '{filename}': {e}. Skipping.")

    print(f"\nSuccess! All files have been merged into '{output_filename}'.")

if __name__ == "__main__":
    merge_sensor_files()