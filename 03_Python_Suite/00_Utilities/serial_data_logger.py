# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Serial data logger: Logs data from a serial port to a CSV file.
# Reads data from a connected device, processes it, and saves it in a structured format.
# ==============================================================================

import serial
import csv
import time
import os

serial_port = 'COM17' # Update this to your serial port
baud_rate = 115200
folder_path = 'read_data' 
csv_filename = 'Sensor_data.csv'
full_path = os.path.join(folder_path, csv_filename)

os.makedirs(folder_path, exist_ok=True)
time.sleep(2)
ser = serial.Serial(serial_port, baud_rate, timeout=1)

with open(full_path, 'a', newline='') as csvfile:
    writer = csv.writer(csvfile)

    print(f"Logging data to {full_path}... (Ctrl+C to stop)")

    try:
        while True:
            line = ser.readline().decode('utf-8').strip()
            if line:
                print(">>", line)
                row = line.split(',')
                writer.writerow(row)
                csvfile.flush()
    except KeyboardInterrupt:
        print("\nLogging stopped by user.")
    finally:
        ser.close()
