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

#include "config.h"
#include "calibration.h"
#include <string.h>
#include <algorithm>
#include <map>
#include <vector>

#ifndef DEVICE_NAME
  #error "DEVICE_NAME is not defined. Please #define DEVICE_NAME in your main sketch."
#endif

//  MASTER CHANNEL LIST (FOR RE-SORTING)
const std::vector<ChannelInfo> masterChannelList = {
    { "UVC",  "raw_uvc",  260, 2 }, // C (AS7331)
    { "UVB",  "raw_uvb",  300, 1 }, // B (AS7331)
    { "UVA",  "raw_uva",  360, 0 }, // A (AS7331)
    { "CH1",  "raw_ch1",  410, 0  }, // A (AS72653)
    { "CH2",  "raw_ch2",  435, 1  }, // B (AS72653)
    { "CH3",  "raw_ch3",  460, 2  }, // C (AS72653)
    { "CH4",  "raw_ch4",  485, 3  }, // D (AS72653)
    { "CH5",  "raw_ch5",  510, 4  }, // E (AS72653)
    { "CH6",  "raw_ch6",  535, 5  }, // F (AS72653)
    { "CH13", "raw_ch13", 560, 12 }, // G (AS72652)
    { "CH14", "raw_ch14", 585, 13 }, // H (AS72652)
    { "CH7",  "raw_ch7",  610, 6  }, // R (AS72651)
    { "CH15", "raw_ch15", 645, 14 }, // I (AS72652)
    { "CH8",  "raw_ch8",  680, 7  }, // S (AS72651)
    { "CH16", "raw_ch16", 705, 15 }, // J (AS72652)
    { "CH9",  "raw_ch9",  730, 8  }, // T (AS72651)
    { "CH10", "raw_ch10", 760, 9  }, // U (AS72651)
    { "CH11", "raw_ch11", 810, 10 }, // V (AS72651)
    { "CH12", "raw_ch12", 860, 11 }, // W (AS72651)
    { "CH17", "raw_ch17", 900, 16 }, // K (AS72652)
    { "CH18", "raw_ch18", 940, 17 }  // L (AS72652)
};

struct CalibrationFactorSet {
    const char* deviceName;
    float C_p[NUM_CHANNELS];
};

constexpr CalibrationFactorSet factorData[] = {
    {"sensor01",    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor02",    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor03",    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor04",    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor05",    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor06",    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor07",    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor08",    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor09",    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor10",    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor11",    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor12",    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},

struct CalibrationDarkCountSet {
    const char* deviceName;
    float S_p_dark[NUM_CHANNELS];
};

constexpr CalibrationDarkCountSet factorDarkCountData[] = {
    {"sensor01", {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor02", {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor03", {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor04", {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor05", {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor06", {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor07", {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor08", {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor09", {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor10", {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor11", {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},
    {"sensor12", {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}},

// THERMAL FACTOR TABLE
const std::map<std::string, TempCoeffSet> universalTempCoeffs = {
    {"CH1", {0.0f, 0.0f, 0.0f}},
    {"CH10", {0.0f, 0.0f, 0.0f}},
    {"CH11", {0.0f, 0.0f, 0.0f}},
    {"CH12", {0.0f, 0.0f, 0.0f}},
    {"CH13", {0.0f, 0.0f, 0.0f}},
    {"CH14", {0.0f, 0.0f, 0.0f}},
    {"CH15", {0.0f, 0.0f, 0.0f}},
    {"CH16", {0.0f, 0.0f, 0.0f}},
    {"CH17", {0.0f, 0.0f, 0.0f}},
    {"CH18", {0.0f, 0.0f, 0.0f}},
    {"CH2", {0.0f, 0.0f, 0.0f}},
    {"CH3", {0.0f, 0.0f, 0.0f}},
    {"CH4", {0.0f, 0.0f, 0.0f}},
    {"CH5", {0.0f, 0.0f, 0.0f}},
    {"CH6", {0.0f, 0.0f, 0.0f}},
    {"CH7", {0.0f, 0.0f, 0.0f}},
    {"CH8", {0.0f, 0.0f, 0.0f}},
    {"CH9", {0.0f, 0.0f, 0.0f}},
    {"UVA", {0.0f, 0.0f, 0.0f}},
    {"UVB", {0.0f, 0.0f, 0.0f}},
    {"UVC", {0.0f, 0.0f, 0.0f}},
};

const TempCoeffSet defaultCoeffs = {0.0f, 0.0f, 0.0f};

const TempCoeffSet& getTempCoefficients(const std::string& channelName) {
    auto it = universalTempCoeffs.find(channelName);
    if (it != universalTempCoeffs.end()) {
        return it->second;
    }
    return defaultCoeffs;
}

// LUX CALIBRATION FACTOR MAP
const std::map<std::string, float> universalLuxFactors = {
    {"sensor01", 0.0f},
    {"sensor02", 0.0f},
    {"sensor03", 0.0f},
    {"sensor04", 0.0f},
    {"sensor05", 0.0f},
    {"sensor06", 0.0f},
    {"sensor07", 0.0f},
    {"sensor08", 0.0f},
    {"sensor09", 0.0f},
    {"sensor10", 0.0f},
    {"sensor11", 0.0f},
    {"sensor12", 0.0f},
};

const TempCoeffSet universalLuxTempCoeffs = {0.0f, 0.0f, 0.0f};
const TempCoeffSet& getLuxTempCoefficients() {
    return universalLuxTempCoeffs;
}

const AutoIntModel universalAutoIntModel = {
    .coeff_a = 0.0f,
    .coeff_b = 0.0f
};

const AutoIntModel& getAutoIntegrationModel() {
    return universalAutoIntModel;
}

constexpr bool strings_equal(const char* a, const char* b) {
    return *a == *b && (*a == '\0' || strings_equal(a + 1, b + 1));
}

constexpr bool is_device_in_table(const char* name) {
    for (const auto& entry : factorData) {
        if (strings_equal(name, entry.deviceName)) {
            return true;
        }
    }
    return false;
}

static_assert(is_device_in_table(DEVICE_NAME), 
              "FATAL_ERROR: DEVICE_NAME not found in calibration.h. Please check spelling or add a new entry to the factorData table.Remember to use 01, 02 -> 12 etc.for sensors");

CalibrationProfile getCalibrationProfile(const std::string& deviceName) {
    CalibrationProfile profile;
    bool found = false;

    for (const auto& row : factorData) {
        if (strcmp(row.deviceName, deviceName.c_str()) == 0) {
            std::copy(std::begin(row.C_p), std::end(row.C_p), profile.C_p.begin());
            found = true;
            break;
        }
    }
    if (!found) {
        profile.C_p.fill(0.0f);
    }

    bool dark_found = false;
    for (const auto& row : factorDarkCountData) {
        if (strcmp(row.deviceName, deviceName.c_str()) == 0) {
            std::copy(std::begin(row.S_p_dark), std::end(row.S_p_dark), profile.S_p_dark.begin());
            dark_found = true;
            break;
        }
    }
    if (!dark_found) {
        profile.S_p_dark.fill(0.0f);
    }

    auto it = universalLuxFactors.find(deviceName);
    if (it != universalLuxFactors.end()) {
        profile.lux_factor = it->second;
    }
    return profile;
}