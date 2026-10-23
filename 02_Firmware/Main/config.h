/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* Master configuration for this device. Change DEVICE_NAME below
* to match the unit being programmed. The name must exist in the calibration tables in calibration.cpp.
*/

#pragma once

#include <cstdint>
#include <cstddef>

// =========================================================
// ===        MASTER CONFIGURATION FOR THIS DEVICE       ===
// =========================================================
// Use sensor01, sensor02 ... sensor12 (must exist in calibration.cpp)
#define DEVICE_NAME "sensor04"

constexpr int   UPLOAD_STAGGER_PER_DEVICE_MS = 15000;   // sensorNN waits (NN-1) x stagger before FTP

constexpr float AS7265X_BASE_PERIOD_MS   = 2.8f;
constexpr float AS7265X_MODE2_MULTIPLIER = 2.0f;

constexpr int   S_INT_TIME_MIN = 1;
constexpr int   S_INT_TIME_MAX = 255;

constexpr int   S_MAX_ACCUMULATIONS    = 10;   // frames summed at max gain and integration time

constexpr int   TSL_SCOUT_BRIGHT_THRESH   = 1500;     // scout ch0 at 1x / 100 ms
constexpr int   TSL_SCOUT_DAYLIGHT_THRESH =   60;
constexpr int   TSL_SCOUT_DIM_THRESH      =    5;

constexpr float TSL_TARGET_COUNTS         = 50000.0f;

constexpr int   HDR_AVG_CUTOFF = 512;   // AEC units (1/16 line), brackets at or below are averaged

constexpr uint16_t MAX_SAFE_VTS = 65000;   // lower if cam_task stack crashes at long brackets

constexpr bool  DEFAULT_HDR_EARLY_TERM = true;
constexpr float DEFAULT_HDR_ET_PCT     = 98.0f;
constexpr int   DEFAULT_HDR_ET_MIN_EXP = 64;     // AEC units
constexpr float DEFAULT_HDR_ET_RADIUS  = 95.0f;

constexpr long  GMT_OFFSET_SEC      = 3600;   // UTC+1 all year, no DST
constexpr int   DAYLIGHT_OFFSET_SEC = 0;
constexpr int   MQTT_KEEPALIVE_SEC  = 300;

constexpr size_t FTP_CHUNK_SIZE = 8192;
constexpr int   MQTT_MAX_RECONNECT_ATTEMPTS = 5;
constexpr int   NTP_MAX_RETRIES = 60;
constexpr int   WIFI_BOOT_STAGGER_MS = 1500;

constexpr bool  DEFAULT_CAM_TOGGLE   = true;
constexpr bool  DEFAULT_HDR_TOGGLE   = true;
constexpr bool  DEFAULT_JPEG_TOGGLE  = false;
constexpr bool  DEFAULT_WIFI_TOGGLE  = true;

constexpr float DEFAULT_S_WAIT_TIME  = 10.0f;   // minutes
constexpr float DEFAULT_C_WAIT_TIME  = 10.0f;
constexpr float MIN_WAIT_MINUTES     = 0.167f;

constexpr int   DEFAULT_HDR_AVG_FRAMES = 3;
constexpr bool  DEFAULT_HDR_SAT_FILL   = true;

constexpr bool  DEFAULT_CAM_CAL_ENABLE  = true;
constexpr bool  DEFAULT_CAM_VIGN_ENABLE = true;
constexpr bool  DEFAULT_CAM_CROP_ENABLE = false;

constexpr int   DEFAULT_S_GAIN     = 64;     // AS7265x: 1, 4, 16, 64
constexpr int   DEFAULT_U_GAIN     = 2048;   // AS7331: 1-2048, powers of 2
constexpr int   DEFAULT_I_GAIN     = 1;      // TSL2591: 0=LOW, 1=MED, 2=HIGH, 3=MAX

constexpr int   DEFAULT_S_INT_TIME = 100;    // register 1-255 (x 2.8 ms)
constexpr int   DEFAULT_U_INT_TIME = 512;    // ms, powers of 2
constexpr int   DEFAULT_I_INT_TIME = 300;    // ms, 100-600

constexpr int CPU_FREQ_IDLE   = 80;    // MHz
constexpr int CPU_FREQ_ACTIVE = 240;

constexpr int      CAPTURE_TASK_STACK    = 16384;
constexpr int      NETWORK_TASK_STACK    = 16384;
constexpr int      UPLOAD_QUEUE_DEPTH    = 12;
constexpr int      CAPTURE_TASK_CORE     = 1;
constexpr int      NETWORK_TASK_CORE     = 0;
constexpr int      CAPTURE_TASK_PRIORITY = 2;
constexpr int      NETWORK_TASK_PRIORITY = 1;
constexpr uint32_t NTP_RESYNC_INTERVAL   = 86400;
