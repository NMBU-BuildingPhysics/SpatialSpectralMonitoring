/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* Declarations for sensor initialization. Camera mode setup functions
* shared between sensor_init.cpp (definitions) and camera.cpp (consumer).
*/

#pragma once

#include <Arduino.h>
#include "src/sensors/TSL2591.h"
#include "src/sensors/SHT4X.h"
#include "src/sensors/AS7265X.h"
#include "src/sensors/AS7331.h"
#include "esp_camera.h"

extern SHT4X    sht;
extern AS7331   as7331;
extern AS7265X  as7265x;
extern TSL2591  tsl;

void setupOV5640_YUV422_VGA();
void setupOV5640_JPEG_WQXGA();

void setupTSL2591();
void setupAS7331();
void setupAS7265X();
void setupSHT4X();

void tslApplyAndFlush(int time_ms);
