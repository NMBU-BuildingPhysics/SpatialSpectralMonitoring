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
#include <Preferences.h>

#ifndef DEVICE_NAME
  #error "DEVICE_NAME is not defined. Please #define DEVICE_NAME in your main sketch."
#endif

// Copy to Main/calibration.cpp and replace the placeholder values with the results
// from 03_Python_Suite/02_Absolute_Calibration.

// name, CSV column, wavelength (nm), index in the sensor read-out
const std::vector<ChannelInfo> masterChannelList = {
    { "UVC",  "raw_uvc",  260, 2 },
    { "UVB",  "raw_uvb",  300, 1 },
    { "UVA",  "raw_uva",  360, 0 },
    { "CH1",  "raw_ch1",  410, 0  },
    { "CH2",  "raw_ch2",  435, 1  },
    { "CH3",  "raw_ch3",  460, 2  },
    { "CH4",  "raw_ch4",  485, 3  },
    { "CH5",  "raw_ch5",  510, 4  },
    { "CH6",  "raw_ch6",  535, 5  },
    { "CH13", "raw_ch13", 560, 12 },
    { "CH14", "raw_ch14", 585, 13 },
    { "CH7",  "raw_ch7",  610, 6  },
    { "CH15", "raw_ch15", 645, 14 },
    { "CH8",  "raw_ch8",  680, 7  },
    { "CH16", "raw_ch16", 705, 15 },
    { "CH9",  "raw_ch9",  730, 8  },
    { "CH10", "raw_ch10", 760, 9  },
    { "CH11", "raw_ch11", 810, 10 },
    { "CH12", "raw_ch12", 860, 11 },
    { "CH17", "raw_ch17", 900, 16 },
    { "CH18", "raw_ch18", 940, 17 }
};

struct CalibrationFactorSet {
    const char* deviceName;
    float C_p[NUM_CHANNELS];
};

// C_p per channel in masterChannelList order (UVC, UVB, UVA, 410 nm ... 940 nm)
constexpr CalibrationFactorSet factorData[] = {
    {"sensor01", {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f}},
    {"sensor02", {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f}},
    {"sensor03", {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f}},
    {"sensor04", {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f}},
    {"sensor05", {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f}},
    {"sensor06", {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f}},
    {"sensor07", {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f}},
    {"sensor08", {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f}},
    {"sensor09", {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f}},
    {"sensor10", {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f}},
    {"sensor11", {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f}},
    {"sensor12", {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f}},
};

struct CalibrationDarkCountSet {
    const char* deviceName;
    float S_p_dark[NUM_CHANNELS];
};

// Used only when no dark counts are stored in NVS (serial command CAL DARK)
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
};

// f(T) = a T^2 + b T + c
const std::map<std::string, TempCoeffSet> universalTempCoeffs = {
    {"CH1", {0.0f, 0.0f, 1.0f}},
    {"CH10", {0.0f, 0.0f, 1.0f}},
    {"CH11", {0.0f, 0.0f, 1.0f}},
    {"CH12", {0.0f, 0.0f, 1.0f}},
    {"CH13", {0.0f, 0.0f, 1.0f}},
    {"CH14", {0.0f, 0.0f, 1.0f}},
    {"CH15", {0.0f, 0.0f, 1.0f}},
    {"CH16", {0.0f, 0.0f, 1.0f}},
    {"CH17", {0.0f, 0.0f, 1.0f}},
    {"CH18", {0.0f, 0.0f, 1.0f}},
    {"CH2", {0.0f, 0.0f, 1.0f}},
    {"CH3", {0.0f, 0.0f, 1.0f}},
    {"CH4", {0.0f, 0.0f, 1.0f}},
    {"CH5", {0.0f, 0.0f, 1.0f}},
    {"CH6", {0.0f, 0.0f, 1.0f}},
    {"CH7", {0.0f, 0.0f, 1.0f}},
    {"CH8", {0.0f, 0.0f, 1.0f}},
    {"CH9", {0.0f, 0.0f, 1.0f}},
    {"LUX", {0.0f, 0.0f, 1.0f}},
    {"UVA", {0.0f, 0.0f, 1.0f}},
    {"UVB", {0.0f, 0.0f, 1.0f}},
    {"UVC", {0.0f, 0.0f, 1.0f}},
};

const TempCoeffSet defaultCoeffs = {0.0f, 0.0f, 1.0f};

const TempCoeffSet& getTempCoefficients(const std::string& channelName) {
    auto it = universalTempCoeffs.find(channelName);
    if (it != universalTempCoeffs.end()) {
        return it->second;
    }
    return defaultCoeffs;
}

const std::map<std::string, float> universalLuxFactors = {
    {"sensor01", 1.0f},
    {"sensor02", 1.0f},
    {"sensor03", 1.0f},
    {"sensor04", 1.0f},
    {"sensor05", 1.0f},
    {"sensor06", 1.0f},
    {"sensor07", 1.0f},
    {"sensor08", 1.0f},
    {"sensor09", 1.0f},
    {"sensor10", 1.0f},
    {"sensor11", 1.0f},
    {"sensor12", 1.0f},
};

const TempCoeffSet universalLuxTempCoeffs = {0.0f, 0.0f, 1.0f};
const TempCoeffSet& getLuxTempCoefficients() {
    return universalLuxTempCoeffs;
}

struct CameraCalibrationEntry {
    const char* deviceName;
    CameraCalibration cal;
};

static const CameraCalibration defaultCameraCal = {
    0.0f, 0.0f, 0.0f,
    320.0f, 240.0f, 320.0f,
    1.0f,
    0, 0, 640, 480,
    640, 480
};

// vign_b, vign_c, vign_d, vign_cx, vign_cy, vign_max_dist, cal_scale (cd/m2 per unit),
// crop_x, crop_y, crop_w, crop_h, src_width, src_height
static constexpr CameraCalibrationEntry cameraCals[] = {
    {"sensor01", {0.0f, 0.0f, 0.0f, 320.0f, 240.0f, 320.0f, 1.0f, 0, 0, 640, 480, 640, 480}},
    {"sensor02", {0.0f, 0.0f, 0.0f, 320.0f, 240.0f, 320.0f, 1.0f, 0, 0, 640, 480, 640, 480}},
    {"sensor03", {0.0f, 0.0f, 0.0f, 320.0f, 240.0f, 320.0f, 1.0f, 0, 0, 640, 480, 640, 480}},
    {"sensor04", {0.0f, 0.0f, 0.0f, 320.0f, 240.0f, 320.0f, 1.0f, 0, 0, 640, 480, 640, 480}},
    {"sensor05", {0.0f, 0.0f, 0.0f, 320.0f, 240.0f, 320.0f, 1.0f, 0, 0, 640, 480, 640, 480}},
    {"sensor06", {0.0f, 0.0f, 0.0f, 320.0f, 240.0f, 320.0f, 1.0f, 0, 0, 640, 480, 640, 480}},
    {"sensor07", {0.0f, 0.0f, 0.0f, 320.0f, 240.0f, 320.0f, 1.0f, 0, 0, 640, 480, 640, 480}},
    {"sensor08", {0.0f, 0.0f, 0.0f, 320.0f, 240.0f, 320.0f, 1.0f, 0, 0, 640, 480, 640, 480}},
    {"sensor09", {0.0f, 0.0f, 0.0f, 320.0f, 240.0f, 320.0f, 1.0f, 0, 0, 640, 480, 640, 480}},
    {"sensor10", {0.0f, 0.0f, 0.0f, 320.0f, 240.0f, 320.0f, 1.0f, 0, 0, 640, 480, 640, 480}},
    {"sensor11", {0.0f, 0.0f, 0.0f, 320.0f, 240.0f, 320.0f, 1.0f, 0, 0, 640, 480, 640, 480}},
    {"sensor12", {0.0f, 0.0f, 0.0f, 320.0f, 240.0f, 320.0f, 1.0f, 0, 0, 640, 480, 640, 480}},
};

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
        profile.C_p.fill(1.0f);
    }

    bool dark_found = false;
    {
        Preferences prefs;
        prefs.begin("calibration", true);
        if (prefs.isKey("dark_counts")) {
            float nvs_dark[NUM_CHANNELS];
            size_t loaded = prefs.getBytes("dark_counts", nvs_dark, sizeof(nvs_dark));
            if (loaded == NUM_CHANNELS * sizeof(float)) {
                std::copy(std::begin(nvs_dark), std::end(nvs_dark), profile.S_p_dark.begin());
                dark_found = true;
            }
        }
        prefs.end();
    }

    if (!dark_found) {
        for (const auto& row : factorDarkCountData) {
            if (strcmp(row.deviceName, deviceName.c_str()) == 0) {
                std::copy(std::begin(row.S_p_dark), std::end(row.S_p_dark), profile.S_p_dark.begin());
                dark_found = true;
                break;
            }
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

const CameraCalibration& getCameraCalibration(const std::string& deviceName) {
    for (const auto& entry : cameraCals) {
        if (strcmp(entry.deviceName, deviceName.c_str()) == 0) {
            return entry.cal;
        }
    }
    return defaultCameraCal;
}
