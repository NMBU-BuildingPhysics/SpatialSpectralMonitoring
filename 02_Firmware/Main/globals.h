/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* This directory contains the source code for the ESP32-S3 microcontroller
* This file contains global variables and constants used across the project
*/

#ifndef GLOBALS_H
#define GLOBALS_H

#include "config.h"
#include "secrets.h"
#include <WiFi.h>   
#include <PubSubClient.h>  
#include <ESP32_FTPClient.h>
#include <Preferences.h>
#include <vector>
#include "calibration.h" 

#define TRIGGER_PIN 4

const int S_INT_TIME_MIN = 2;
const int S_INT_TIME_MAX = 255;
const char* const ftpLandingZone = FTP_LANDING_ZONE;
const char* const ntpServer = FTP_SERVER; // FTP and NTP share the same server address
const long  gmtOffset_sec = 3600;
const int   daylightOffset_sec = 3600;

extern String deviceName;
extern bool cam_toggle;
extern bool hdr_toggle;
extern bool wifi_toggle;
extern CalibrationProfile active_profile;

extern long lastSensorTriggerSecond;
extern long lastCameraTriggerSecond;
extern volatile bool triggerSensorMeasurement;
extern volatile bool triggerCameraCapture;
extern float S_wait_time;
extern float C_wait_time;
extern std::vector<int> exposure_values;

extern int S_gainValue; 
extern int U_gainValue;
extern int I_gainValue;
extern int S_integrationTime;
extern int U_integrationTime;
extern int I_integrationTime;

extern WiFiClient espClient;
extern PubSubClient client;
extern ESP32_FTPClient ftp;
extern Preferences preferences;

#endif