/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* This directory contains the source code for the ESP32-S3 microcontroller
* This file contains calibration profiles for different sensor units
*/

#pragma once

#include <string>
#include <array>
#include <vector>
#include <cstdint>

constexpr int NUM_CHANNELS = 21;

struct CalibrationProfile {
    std::array<float, NUM_CHANNELS> C_p;
    std::array<float, NUM_CHANNELS> S_p_dark;
    float lux_factor = 1.0f;
};

struct TempCoeffSet {
    float a, b, c;
};

struct CameraCalibration {
    float vign_b;
    float vign_c;
    float vign_d;
    float vign_cx;
    float vign_cy;
    float vign_max_dist;

    float cal_scale;

    uint16_t crop_x;
    uint16_t crop_y;
    uint16_t crop_w;
    uint16_t crop_h;

    uint16_t src_width;
    uint16_t src_height;
};

struct ChannelInfo {
    const char* name;
    const char* csv_col_name;
    int wavelength;
    int native_index;
};

extern const std::vector<ChannelInfo> masterChannelList;
CalibrationProfile getCalibrationProfile(const std::string& deviceName);
const TempCoeffSet& getTempCoefficients(const std::string& channelName);
const TempCoeffSet& getLuxTempCoefficients();
const CameraCalibration& getCameraCalibration(const std::string& deviceName);
