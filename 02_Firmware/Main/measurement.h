/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* Auto-exposure spectral measurement, temperature-corrected calibration,
* CSV formatting, gain/integration time configuration, and AS7265x LED control.
*/

#pragma once

#include <Arduino.h>
#include <time.h>
#include "datastructures.h"
#include "calibration.h"

FullSensorReading performGoalSeekingMeasurement();
FullSensorReading measureSpectralFixed();
FullSensorReading performCalibrationCapture(
    bool isDark,
    int& out_s_gain, int& out_s_time,
    int& out_u_gain, int& out_u_time,
    int& out_i_gain, int& out_i_time);
FullSensorReading calibrateReading(
    const FullSensorReading& reading,
    const CalibrationProfile& profile,
    int s_gain, int u_gain,
    int s_time_reg_val, int u_time_ms);

String readingToCsv(
    const FullSensorReading& reading,
    int S_gain, int S_time,
    int U_gain, int U_time,
    int I_gain, int I_time,
    const CalibrationProfile& profile,
    const struct tm* timeinfo = nullptr,
    int rssi = 0,
    unsigned long uptime_ms = 0);
void printCsvHeader();

void setGain(char sensorType, int gainValue);
void setIntegrationTime(char sensorType, int integrationTime);

void setSpectralLeds(bool on);
