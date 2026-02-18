/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* This directory contains the source code for the ESP32-S3 microcontroller
* This file contains data structures used across the project
*/

#ifndef DATASTRUCTURES_H
#define DATASTRUCTURES_H

#include <cstdint>

struct FullSensorReading {
  float temperature = 0.0;
  float humidity = 0.0;
  bool isValid = false;


  float raw_lux = 0.0;
  uint16_t raw_uva = 0, raw_uvb = 0, raw_uvc = 0;
  uint16_t raw_spectral[18] = {0};

  uint16_t dark_uva = 0, dark_uvb = 0, dark_uvc = 0;
  uint16_t dark_spectral[18] = {0};
  
  float cal_lux = 0.0; 
  float cal_uva = 0.0, cal_uvb = 0.0, cal_uvc = 0.0;
  float cal_spectral[18] = {0.0};
};

#endif