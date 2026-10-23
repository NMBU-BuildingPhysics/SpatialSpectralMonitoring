/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* OV5640 camera management, bracketed HDR capture with on-device
* pixel-level merge, Radiance .hdr encoding, and FTP upload.
*/

#pragma once

#include "datastructures.h"
#include <cstddef>
#include <cstdint>

class ESP32_FTPClient;

void setupOV5640_YUV422_VGA();
void setupOV5640_JPEG_WQXGA();
void reinitCamera(bool hdrMode);

void freeHDRBuffers();
void freeHDRAccumBuffers();

void powerDownCamera();

HdrBuffer captureHDRMerged();
size_t encodeRadianceHdr(const HdrBuffer& hdr, uint8_t* outBuf, struct tm timeinfo);

struct EncodedHDR {
    uint8_t* data = nullptr;
    size_t   len  = 0;
    char     filename[72] = {};
    int      brackets_used  = 0;
    int      brackets_total = 0;
    bool     valid = false;
};

struct CapturedJPEG {
    uint8_t* data = nullptr;
    size_t   len  = 0;
    char     filename[72] = {};
    bool     valid = false;
    void*    _fb = nullptr;
};

EncodedHDR captureAndEncodeHDR(struct tm timeinfo);

bool uploadEncodedHDR(ESP32_FTPClient& ftp, const char* baseDir, const EncodedHDR& hdr);

CapturedJPEG captureContextJPEG(struct tm timeinfo);

bool uploadContextJPEG(ESP32_FTPClient& ftp, const char* baseDir, CapturedJPEG& jpeg);

void releaseJPEG(CapturedJPEG& jpeg);
