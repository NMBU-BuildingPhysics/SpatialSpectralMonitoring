/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* Global variable declarations (extern) and compile-time constants.
* Definitions live in Main.ino.
*/

#pragma once

#include "config.h"
#include "secrets.h"
#include <WiFi.h>
#include <PubSubClient.h>
#include <ESP32_FTPClient.h>
#include <Preferences.h>
#include <vector>
#include <time.h>
#include "calibration.h"
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>

constexpr const char* FTP_LANDING  = FTP_LANDING_ZONE;
constexpr const char* NTP_SERVER   = FTP_SERVER;

extern String deviceName;
extern bool   cam_toggle;
extern bool   hdr_toggle;
extern bool   jpeg_toggle;
extern bool   wifi_toggle;
extern CalibrationProfile active_profile;

extern time_t   nextSensorTrigger;
extern time_t   nextCameraTrigger;
extern volatile bool triggerSensorMeasurement;
extern volatile bool triggerCameraCapture;
extern float    S_wait_time;
extern float    C_wait_time;
extern int      upload_stagger_ms;

extern std::vector<int> exposure_values;
extern int  hdr_avg_frames;
extern bool hdr_sat_fill;
extern bool  hdr_early_term;
extern float hdr_et_pct;
extern int   hdr_et_min_exp;
extern float hdr_et_radius_pct;

extern bool cam_cal_enable;
extern bool cam_vign_enable;
extern bool cam_crop_enable;
extern const CameraCalibration* cam_cal_colour;
extern float cam_cal_scale_override;
extern bool  cam_cal_scale_overridden;

extern int S_gainValue;
extern int U_gainValue;
extern int I_gainValue;
extern int S_integrationTime;
extern int U_integrationTime;
extern int I_integrationTime;

extern WiFiClient      espClient;
extern PubSubClient    client;
extern ESP32_FTPClient ftp;
extern Preferences     preferences;

extern QueueHandle_t     uploadQueue;
extern SemaphoreHandle_t i2cMutex;
extern SemaphoreHandle_t hdrBufferSem;
extern TaskHandle_t      captureTaskHandle;
extern TaskHandle_t      networkTaskHandle;
