/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* This directory contains the source code for the ESP32-S3 microcontroller
* This file contains general utility functions used across the project
*/


#ifndef FUNCTIONS_H
#define FUNCTIONS_H

#include "datastructures.h"
#include "calibration.h"
#include "globals.h"

using MqttCallback = void (*)(char*, uint8_t*, unsigned int);
String sensorReadingToCsv(
    const FullSensorReading &reading,
    int S_gain, int S_time,
    int U_gain, int U_time,
    int I_gain, int I_time,
    const CalibrationProfile &profile);
FullSensorReading performSmartMeasurement();
void callback(char* topic, byte* payload, unsigned int length);
void setupMqtt(PubSubClient& client, const String& deviceName, MqttCallback callback);
void publishHealthStatus(PubSubClient& client, const String& deviceName);
void handleMqtt(PubSubClient& client, const String& deviceName);
void publishMetric(PubSubClient& client, const String& deviceName, const char* metric, float value, int decimals, bool retain = false);
void publishMetric(PubSubClient& client, const String& deviceName, const char* metric, unsigned int value, bool retain = false);
void ledLight(bool toggle);
void processSerialCommand(String command);
void setCameraExposure(int exposure_value);
void capture_LDR_image(const char* baseDir, int exposure, ESP32_FTPClient &ftp, struct tm timeinfo);
void updateGain(char sensorType, int gainValue);
void updateIntegrationTime(char sensorType, int integrationTime);
void photo_send(const char * fileName, const char* uploadDir, ESP32_FTPClient &ftp);
FullSensorReading applyCalibration(const FullSensorReading& reading, const CalibrationProfile& profile, int s_gain, int u_gain, int s_time_reg_val, int u_time_ms);
void uploadCsvData(ESP32_FTPClient &ftp, const char* uploadDir, const char* fileName, const FullSensorReading& data, int s_gain, int u_gain, int i_gain, int s_time, int u_time, int i_time);

#endif