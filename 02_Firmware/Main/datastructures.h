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

#pragma once

#include <cstdint>
#include <cstddef>

struct HdrBuffer {
  float* data = nullptr;
  uint16_t width = 0;
  uint16_t height = 0;
  uint8_t channels = 3;
  bool isValid = false;
  int brackets_used  = 0;
  int brackets_total = 0;
};

struct FullSensorReading {
  float temperature = 0.0;
  float humidity = 0.0;
  bool isValid = false;

  uint16_t tsl_ch0 = 0;
  uint16_t tsl_ch1 = 0;
  float raw_lux = 0.0;
  uint16_t raw_uva = 0, raw_uvb = 0, raw_uvc = 0;
  uint16_t raw_spectral[18] = {0};

  uint8_t num_accumulations = 1;
  uint16_t spectral_peak = 0;

  float cal_lux = 0.0;
  float cal_uva = 0.0, cal_uvb = 0.0, cal_uvc = 0.0;
  float cal_spectral[18] = {0.0};
};

struct EncodedHDR;
struct CapturedJPEG;

struct CsvPayload {
    char  csv[2400];
    char  filename[64];
    float temperature;
    float humidity;
    float cal_lux;
    uint8_t num_accumulations;
};

enum class UploadType : uint8_t { CSV, HDR, JPEG };

struct UploadItem {
    UploadType type;
    union {
        CsvPayload   csv;
        struct {
            uint8_t* data;
            size_t   len;
            char     filename[72];
            int      brackets_used;
            int      brackets_total;
        } hdr;
        struct {
            uint8_t* data;
            size_t   len;
            char     filename[72];
            void*    fb;
        } jpeg;
    };
};
