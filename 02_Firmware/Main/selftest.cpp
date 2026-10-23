/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* Pre-deployment self-test runner (serial command TEST [group]).
* Prints PASS/WARN/FAIL per check and publishes a JSON summary via MQTT.
*/

#include "selftest.h"
#include "globals.h"
#include "sensor_init.h"
#include "measurement.h"
#include "camera.h"
#include "version.h"

#include <esp_task_wdt.h>
#include <esp_camera.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <time.h>
#include <cstring>
#include <cmath>

static int s_pass = 0;
static int s_warn = 0;
static int s_fail = 0;

enum class TS : uint8_t { PASS, WARN, FAIL };

static void report(const char* group, const char* name, TS status, const char* detail) {
    const char* st = (status == TS::PASS) ? "PASS"
                   : (status == TS::WARN) ? "WARN"
                   :                        "FAIL";
    Serial.printf("[SELFTEST:%-7s]  %-30s  %s  %s\n", group, name, st, detail);

    if      (status == TS::PASS) s_pass++;
    else if (status == TS::WARN) s_warn++;
    else                          s_fail++;
}

#define REPORT(group, name, status, fmt, ...) \
    do { char _d[128]; snprintf(_d, sizeof(_d), fmt, ##__VA_ARGS__); \
         report(group, name, status, _d); } while(0)

static void runGroupConfig() {
    Serial.println("[SELFTEST] --- CONFIG ---");

    {
        const int n = static_cast<int>(exposure_values.size());
        bool sorted   = true;
        bool no_zeros = true;
        for (int i = 0; i < n; i++) {
            if (exposure_values[i] <= 0) no_zeros = false;
            if (i > 0 && exposure_values[i] <= exposure_values[i - 1]) sorted = false;
        }
        if (n < 2 || !sorted || !no_zeros) {
            REPORT("CONFIG", "ExposureTable", TS::FAIL,
                   "n=%d sorted=%d no_zeros=%d", n, sorted, no_zeros);
        } else {
            REPORT("CONFIG", "ExposureTable", TS::PASS,
                   "%d entries, sorted asc, all >0 (lo=%d hi=%d)",
                   n, exposure_values.front(), exposure_values.back());
        }
    }

    {
        const bool is_default = (fabsf(active_profile.C_p[0] - 1.0f) < 1e-6f &&
                                 fabsf(active_profile.C_p[1] - 1.0f) < 1e-6f);
        if (is_default) {
            REPORT("CONFIG", "CalibrationProfile", TS::WARN,
                   "DEFAULT profile (C_p all 1.0) — check DEVICE_NAME matches calibration table");
        } else {
            REPORT("CONFIG", "CalibrationProfile", TS::PASS,
                   "device=%s Cp[0]=%.4f Cp[20]=%.4f lux_factor=%.4f",
                   deviceName.c_str(),
                   active_profile.C_p[0],
                   active_profile.C_p[20],
                   active_profile.lux_factor);
        }
    }

    {
        float max_dark = 0.0f;
        for (int i = 0; i < NUM_CHANNELS; i++)
            if (active_profile.S_p_dark[i] > max_dark) max_dark = active_profile.S_p_dark[i];
        if (max_dark < 1e-10f) {
            REPORT("CONFIG", "DarkCountProfile", TS::WARN,
                   "all zeros — run 'CAL DARK' to calibrate dark counts");
        } else {
            REPORT("CONFIG", "DarkCountProfile", TS::PASS,
                   "max_dark=%.6f (loaded from NVS or factory table)", max_dark);
        }
    }

    {
        const float lf = active_profile.lux_factor;
        if (lf <= 0.0f || lf > 1000.0f) {
            REPORT("CONFIG", "LuxFactor", TS::FAIL,
                   "lux_factor=%.4f (out of plausible range [0.001, 1000])", lf);
        } else if (fabsf(lf - 1.0f) < 1e-6f) {
            REPORT("CONFIG", "LuxFactor", TS::WARN,
                   "lux_factor=1.0 (default — check calibration table for %s)",
                   deviceName.c_str());
        } else {
            REPORT("CONFIG", "LuxFactor", TS::PASS, "lux_factor=%.4f", lf);
        }
    }

    {
        if (cam_cal_colour == nullptr) {
            REPORT("CONFIG", "CameraCalibration", TS::FAIL, "cam_cal_colour is null");
        } else {
            const bool is_default_cal = (cam_cal_colour->cal_scale == 1.0f &&
                                         fabsf(cam_cal_colour->vign_b) < 1e-8f);
            if (is_default_cal) {
                REPORT("CONFIG", "CameraCalibration", TS::WARN,
                       "default (identity) camera cal — no device-specific calibration loaded");
            } else {
                REPORT("CONFIG", "CameraCalibration", TS::PASS,
                       "scale=%.3f vign_b=%.5f crop=%ux%u @(%u,%u)",
                       cam_cal_colour->cal_scale,
                       cam_cal_colour->vign_b,
                       cam_cal_colour->crop_w, cam_cal_colour->crop_h,
                       cam_cal_colour->crop_x, cam_cal_colour->crop_y);
            }
        }
    }

    {
        char buf[128];
        snprintf(buf, sizeof(buf),
                 "cam=%d hdr=%d jpeg=%d wifi=%d calEn=%d vignEn=%d cropEn=%d",
                 cam_toggle, hdr_toggle, jpeg_toggle, wifi_toggle,
                 cam_cal_enable, cam_vign_enable, cam_crop_enable);
        report("CONFIG", "ToggleState", TS::PASS, buf);
    }

    {
        bool q_ok    = (uploadQueue       != NULL);
        bool i2c_ok  = (i2cMutex          != NULL);
        bool sem_ok  = (hdrBufferSem       != NULL);
        bool cap_ok  = (captureTaskHandle  != NULL);
        bool net_ok  = (networkTaskHandle  != NULL);
        if (!q_ok || !i2c_ok || !sem_ok || !cap_ok || !net_ok) {
            REPORT("CONFIG", "FreeRTOS_Handles", TS::FAIL,
                   "queue=%d i2cMutex=%d hdrSem=%d captureTask=%d netTask=%d",
                   q_ok, i2c_ok, sem_ok, cap_ok, net_ok);
        } else {
            UBaseType_t spaces = uxQueueSpacesAvailable(uploadQueue);
            REPORT("CONFIG", "FreeRTOS_Handles", TS::PASS,
                   "all handles valid, queue spaces=%u/%d",
                   static_cast<unsigned>(spaces), UPLOAD_QUEUE_DEPTH);
        }
    }

    {
        bool s_ok = (S_wait_time >= MIN_WAIT_MINUTES);
        bool c_ok = (C_wait_time >= MIN_WAIT_MINUTES);
        if (!s_ok || !c_ok) {
            REPORT("CONFIG", "MeasurementIntervals", TS::WARN,
                   "S_wait=%.2f min C_wait=%.2f min (min=%.3f)",
                   S_wait_time, C_wait_time, MIN_WAIT_MINUTES);
        } else {
            REPORT("CONFIG", "MeasurementIntervals", TS::PASS,
                   "S_wait=%.2f min C_wait=%.2f min", S_wait_time, C_wait_time);
        }
    }
}

static void runGroupMemory() {
    Serial.println("[SELFTEST] --- MEMORY ---");

    constexpr size_t HEAP_FAIL_THRESH  =  50 * 1024;
    constexpr size_t HEAP_WARN_THRESH  = 150 * 1024;
    constexpr size_t PSRAM_FAIL_THRESH = 3 * 1024 * 1024;
    constexpr size_t PSRAM_WARN_THRESH = 4 * 1024 * 1024;
    constexpr size_t PSRAM_ALLOC_SIZE  = 1 * 1024 * 1024;

    {
        const size_t free_heap = heap_caps_get_free_size(MALLOC_CAP_8BIT);
        const size_t min_heap  = heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT);
        TS st = (free_heap < HEAP_FAIL_THRESH) ? TS::FAIL
              : (free_heap < HEAP_WARN_THRESH) ? TS::WARN
              :                                   TS::PASS;
        REPORT("MEMORY", "Heap_Free", st,
               "free=%u B min_ever=%u B (fail<%u warn<%u)",
               static_cast<unsigned>(free_heap),
               static_cast<unsigned>(min_heap),
               static_cast<unsigned>(HEAP_FAIL_THRESH),
               static_cast<unsigned>(HEAP_WARN_THRESH));
    }

    {
        const size_t free_psram = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
        const size_t min_psram  = heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM);
        TS st = (free_psram < PSRAM_FAIL_THRESH) ? TS::FAIL
              : (free_psram < PSRAM_WARN_THRESH) ? TS::WARN
              :                                     TS::PASS;
        REPORT("MEMORY", "PSRAM_Free", st,
               "free=%u B min_ever=%u B (fail<3MB warn<4MB)",
               static_cast<unsigned>(free_psram),
               static_cast<unsigned>(min_psram));
    }

    {
        void* p = heap_caps_malloc(PSRAM_ALLOC_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (p == nullptr) {
            REPORT("MEMORY", "PSRAM_Alloc_1MB", TS::FAIL,
                   "malloc(%u) returned null — heap too fragmented",
                   static_cast<unsigned>(PSRAM_ALLOC_SIZE));
        } else {
            memset(p, 0xAB, 64);
            free(p);
            REPORT("MEMORY", "PSRAM_Alloc_1MB", TS::PASS,
                   "alloc+touch+free of %u B OK",
                   static_cast<unsigned>(PSRAM_ALLOC_SIZE));
        }
    }

    {
        uint32_t cpu_mhz = getCpuFrequencyMhz();
        REPORT("MEMORY", "CPU_Frequency", TS::PASS,
               "%u MHz (active=%d idle=%d)", cpu_mhz, CPU_FREQ_ACTIVE, CPU_FREQ_IDLE);
    }
}

static void runGroupSensor() {
    Serial.println("[SELFTEST] --- SENSOR ---");

    constexpr int TEST_S_GAIN = 64;
    constexpr int TEST_U_GAIN = 2048;
    constexpr int TEST_I_GAIN = 0;
    constexpr int TEST_S_TIME = 50;
    constexpr int TEST_U_TIME = 512;
    constexpr int TEST_I_TIME = 300;

    FullSensorReading reading;

    if (xSemaphoreTake(i2cMutex, pdMS_TO_TICKS(10000)) != pdTRUE) {
        report("SENSOR", "I2C_Mutex", TS::FAIL,
               "could not acquire i2cMutex within 10s — captureTask may be stuck");
        return;
    }

    const int orig_S_gain = S_gainValue;
    const int orig_U_gain = U_gainValue;
    const int orig_I_gain = I_gainValue;
    const int orig_S_time = S_integrationTime;
    const int orig_U_time = U_integrationTime;
    const int orig_I_time = I_integrationTime;

    setGain('I', TEST_I_GAIN);
    setIntegrationTime('I', TEST_I_TIME);
    setGain('S', TEST_S_GAIN);
    setIntegrationTime('S', TEST_S_TIME);
    setGain('U', TEST_U_GAIN);
    setIntegrationTime('U', TEST_U_TIME);

    esp_task_wdt_reset();
    reading = measureSpectralFixed();
    esp_task_wdt_reset();

    setSpectralLeds(true);
    delay(200);
    setSpectralLeds(false);

    setGain('I', orig_I_gain);
    setIntegrationTime('I', orig_I_time);
    setGain('S', orig_S_gain);
    setIntegrationTime('S', orig_S_time);
    setGain('U', orig_U_gain);
    setIntegrationTime('U', orig_U_time);

    xSemaphoreGive(i2cMutex);

    if (!reading.isValid) {
        report("SENSOR", "Measurement_Valid", TS::FAIL,
               "measureSpectralFixed() returned isValid=false — check serial log above for which sensor timed out");
    } else {
        report("SENSOR", "Measurement_Valid", TS::PASS, "all sensors responded within timeout");
    }

    {
        const float T = reading.temperature;
        const float RH = reading.humidity;
        const bool temp_phys_ok  = (T > -20.0f && T < 80.0f);
        const bool humid_phys_ok = (RH >= 0.0f && RH <= 100.0f);
        const bool temp_warn     = (T > 45.0f);
        const bool temp_low_warn = (T < 5.0f);

        if (!temp_phys_ok || !humid_phys_ok) {
            REPORT("SENSOR", "SHT4X_TempHumidity", TS::FAIL,
                   "T=%.1f degC RH=%.1f%% — outside physical range (T:-20..80, RH:0..100)",
                   T, RH);
        } else if (temp_warn) {
            REPORT("SENSOR", "SHT4X_TempHumidity", TS::WARN,
                   "T=%.1f degC RH=%.1f%% — temperature HIGH (>45C), check enclosure ventilation",
                   T, RH);
        } else if (temp_low_warn) {
            REPORT("SENSOR", "SHT4X_TempHumidity", TS::WARN,
                   "T=%.1f degC RH=%.1f%% — temperature LOW (<5C), check environment",
                   T, RH);
        } else {
            REPORT("SENSOR", "SHT4X_TempHumidity", TS::PASS,
                   "T=%.1f degC RH=%.1f%%", T, RH);
        }
    }

    {
        const float lux = reading.raw_lux;
        const uint16_t ch0 = reading.tsl_ch0;
        const uint16_t ch1 = reading.tsl_ch1;
        if (ch0 == 0 && ch1 == 0 && lux == 0.0f) {
            report("SENSOR", "TSL2591_Lux", TS::WARN,
                   "lux=0.0 ch0=0 ch1=0 — dark room or sensor not responding (no error if covered)");
        } else if (ch0 == 65535 && ch1 == 65535) {
            report("SENSOR", "TSL2591_Lux", TS::WARN,
                   "ch0=65535 ch1=65535 — saturated at LOW gain (extremely bright scene)");
        } else {
            REPORT("SENSOR", "TSL2591_Lux", TS::PASS,
                   "lux=%.1f ch0=%u ch1=%u", lux, ch0, ch1);
        }
    }

    {
        const uint16_t peak = reading.spectral_peak;
        const float lux     = reading.raw_lux;
        bool any_nonzero = false;
        for (int i = 0; i < 18; i++) {
            if (reading.raw_spectral[i] > 0) { any_nonzero = true; break; }
        }
        if (!any_nonzero && lux > 5.0f) {
            REPORT("SENSOR", "AS7265X_Spectral", TS::FAIL,
                   "all 18 channels = 0 but lux=%.1f — AS7265X may not be responding", lux);
        } else if (!any_nonzero) {
            REPORT("SENSOR", "AS7265X_Spectral", TS::WARN,
                   "all channels = 0 (dark room — consistent with lux=%.1f)", lux);
        } else if (peak == 65535) {
            REPORT("SENSOR", "AS7265X_Spectral", TS::WARN,
                   "peak=65535 SATURATED at gain=%d time=%d — try lower gain for bright scenes",
                   TEST_S_GAIN, TEST_S_TIME);
        } else {
            REPORT("SENSOR", "AS7265X_Spectral", TS::PASS,
                   "peak=%u accum=%u (18ch, gain=%d time_reg=%d)",
                   peak, reading.num_accumulations, TEST_S_GAIN, TEST_S_TIME);
        }
    }

    {
        const uint16_t uva = reading.raw_uva;
        const uint16_t uvb = reading.raw_uvb;
        const uint16_t uvc = reading.raw_uvc;
        const bool any_uv = (uva > 0 || uvb > 0 || uvc > 0);
        if (uva == 65535 || uvb == 65535 || uvc == 65535) {
            REPORT("SENSOR", "AS7331_UV", TS::WARN,
                   "uva=%u uvb=%u uvc=%u — one or more channels SATURATED",
                   uva, uvb, uvc);
        } else if (!any_uv) {
            REPORT("SENSOR", "AS7331_UV", TS::WARN,
                   "uva=0 uvb=0 uvc=0 — no UV detected (normal indoors, warn if outdoors/UV source)");
        } else {
            REPORT("SENSOR", "AS7331_UV", TS::PASS,
                   "uva=%u uvb=%u uvc=%u (gain=%d time=%dms)",
                   uva, uvb, uvc, TEST_U_GAIN, TEST_U_TIME);
        }
    }

    report("SENSOR", "SpectralLEDs", TS::PASS, "LED toggle (on 200ms off) completed without crash");
}

static void stCamSetAEC(sensor_t* s, int aec_val, uint16_t vts_override = 0) {
    if (vts_override > 0) {
        s->set_reg(s, 0x380e, 0xff, (vts_override >> 8) & 0xFF);
        s->set_reg(s, 0x380f, 0xff,  vts_override       & 0xFF);
    }
    unsigned int aec = static_cast<unsigned int>(aec_val < 0 ? 0 : aec_val);
    s->set_reg(s, 0x3500, 0x0f, (aec >> 16) & 0x0F);
    s->set_reg(s, 0x3501, 0xff, (aec >> 8)  & 0xFF);
    s->set_reg(s, 0x3502, 0xff,  aec        & 0xFF);
}

static int stFrameDiversity(const uint8_t* buf, size_t len, int n_samples) {
    if (!buf || len == 0 || n_samples <= 0) return 0;
    const uint8_t ref = buf[0];
    int diff = 0;
    size_t step = len / static_cast<size_t>(n_samples);
    if (step < 1) step = 1;
    for (size_t i = 0; i < len && diff < n_samples; i += step) {
        if (buf[i] != ref) diff++;
    }
    return diff;
}

static void runGroupCamera() {
    Serial.println("[SELFTEST] --- CAMERA ---");
    esp_task_wdt_reset();

    if (xSemaphoreTake(hdrBufferSem, pdMS_TO_TICKS(30000)) != pdTRUE) {
        report("CAMERA", "HDR_Semaphore", TS::FAIL,
               "could not acquire hdrBufferSem within 30s — HDR capture in progress?");
        return;
    }
    report("CAMERA", "HDR_Semaphore", TS::PASS, "acquired — no concurrent capture");

    bool cam_tests_failed = false;

    {
        reinitCamera(true);
        delay(300);

        sensor_t* s = esp_camera_sensor_get();
        if (!s) {
            report("CAMERA", "VGA_Init", TS::FAIL, "esp_camera_sensor_get() returned null after reinitCamera(HDR)");
            cam_tests_failed = true;
        } else {
            int rb_3503 = s->get_reg(s, 0x3503, 0xff);
            REPORT("CAMERA", "VGA_Init", TS::PASS,
                   "sensor ptr OK  0x3503=0x%02X (expect 0x07=manual AEC/AGC/VTS)",
                   rb_3503 >= 0 ? rb_3503 : 0xFF);
        }

        if (!cam_tests_failed) {
            sensor_t* s2 = esp_camera_sensor_get();

            int vts_hi = s2->get_reg(s2, 0x380e, 0xff);
            int vts_lo = s2->get_reg(s2, 0x380f, 0xff);
            const uint16_t default_vts = (vts_hi < 0 || vts_lo < 0)
                                       ? 984u
                                       : static_cast<uint16_t>((vts_hi << 8) | vts_lo);

            for (int i = 0; i < 3; i++) {
                camera_fb_t* f = esp_camera_fb_get();
                if (f) esp_camera_fb_return(f);
                delay(60);
            }

            stCamSetAEC(s2, 16, 0);
            delay(70);
            { camera_fb_t* stale = esp_camera_fb_get(); if (stale) esp_camera_fb_return(stale); }
            delay(70);

            camera_fb_t* fb_lo = esp_camera_fb_get();
            if (!fb_lo) {
                report("CAMERA", "Bracket_Short_AEC16", TS::FAIL,
                       "esp_camera_fb_get() returned null");
            } else {
                const uint16_t W = fb_lo->width;
                const uint16_t H = fb_lo->height;
                const size_t expected_len = static_cast<size_t>(W) * H * 2;
                const int diversity = stFrameDiversity(fb_lo->buf, fb_lo->len, 128);
                esp_camera_fb_return(fb_lo);

                if (W != 640 || H != 480) {
                    REPORT("CAMERA", "Bracket_Short_AEC16", TS::FAIL,
                           "unexpected dimensions %ux%u (expected 640x480)", W, H);
                } else if (diversity == 0) {
                    REPORT("CAMERA", "Bracket_Short_AEC16", TS::WARN,
                           "%ux%u len=%u but all sampled bytes identical — very dark or hardware issue",
                           W, H, static_cast<unsigned>(expected_len));
                } else {
                    REPORT("CAMERA", "Bracket_Short_AEC16", TS::PASS,
                           "%ux%u len=%u diversity=%d/128 OK",
                           W, H, static_cast<unsigned>(expected_len), diversity);
                }
            }

            esp_task_wdt_reset();

            constexpr uint16_t LONG_VTS = 4300;
            constexpr int      LONG_AEC = 65536;
            stCamSetAEC(s2, LONG_AEC, LONG_VTS);
            delay(220);
            { camera_fb_t* stale = esp_camera_fb_get(); if (stale) esp_camera_fb_return(stale); }
            delay(220);

            camera_fb_t* fb_hi = esp_camera_fb_get();
            if (!fb_hi) {
                report("CAMERA", "Bracket_Long_AEC65536", TS::FAIL,
                       "esp_camera_fb_get() returned null");
            } else {
                const uint16_t W = fb_hi->width;
                const uint16_t H = fb_hi->height;
                const int diversity = stFrameDiversity(fb_hi->buf, fb_hi->len, 128);
                esp_camera_fb_return(fb_hi);

                if (W != 640 || H != 480) {
                    REPORT("CAMERA", "Bracket_Long_AEC65536", TS::FAIL,
                           "unexpected dimensions %ux%u", W, H);
                } else if (diversity == 0) {
                    REPORT("CAMERA", "Bracket_Long_AEC65536", TS::WARN,
                           "%ux%u diversity=0 — all bytes identical (fully saturated or stuck DMA?)",
                           W, H);
                } else {
                    REPORT("CAMERA", "Bracket_Long_AEC65536", TS::PASS,
                           "%ux%u AEC=%d VTS=%u diversity=%d/128 OK",
                           W, H, LONG_AEC, LONG_VTS, diversity);
                }
            }

            s2->set_reg(s2, 0x380e, 0xff, (default_vts >> 8) & 0xFF);
            s2->set_reg(s2, 0x380f, 0xff,  default_vts       & 0xFF);
        }

        powerDownCamera();
        report("CAMERA", "VGA_PowerDown", TS::PASS, "standby register 0x3008=0x42 written");
        esp_task_wdt_reset();
    }

    {
        reinitCamera(false);

        sensor_t* sj = esp_camera_sensor_get();
        if (!sj) {
            report("CAMERA", "JPEG_Init", TS::FAIL,
                   "esp_camera_sensor_get() returned null after reinitCamera(JPEG)");
        } else {
            report("CAMERA", "JPEG_Init", TS::PASS, "sensor ptr OK JPEG mode");

            for (int i = 0; i < 6; i++) {
                camera_fb_t* f = esp_camera_fb_get();
                if (f) esp_camera_fb_return(f);
                delay(150);
                esp_task_wdt_reset();
            }

            camera_fb_t* jfb = esp_camera_fb_get();
            if (!jfb) {
                report("CAMERA", "JPEG_Capture", TS::FAIL, "esp_camera_fb_get() returned null");
            } else {
                const uint16_t W   = jfb->width;
                const uint16_t H   = jfb->height;
                const size_t   len = jfb->len;
                const bool magic_ok = (len >= 2 && jfb->buf[0] == 0xFF && jfb->buf[1] == 0xD8);
                const bool size_ok  = (len > 10000);

                esp_camera_fb_return(jfb);

                if (!magic_ok) {
                    REPORT("CAMERA", "JPEG_Capture", TS::FAIL,
                           "%ux%u len=%u — missing JPEG SOI magic (expected FF D8)",
                           W, H, static_cast<unsigned>(len));
                } else if (!size_ok) {
                    REPORT("CAMERA", "JPEG_Capture", TS::WARN,
                           "%ux%u len=%u — suspiciously small (< 10 KB), check lens/aperture",
                           W, H, static_cast<unsigned>(len));
                } else {
                    REPORT("CAMERA", "JPEG_Capture", TS::PASS,
                           "%ux%u len=%u magic=FFD8 OK",
                           W, H, static_cast<unsigned>(len));
                }
            }
        }

        powerDownCamera();
        report("CAMERA", "JPEG_PowerDown", TS::PASS, "camera powered down after tests");
        esp_task_wdt_reset();
    }

    xSemaphoreGive(hdrBufferSem);
    report("CAMERA", "HDR_Semaphore_Released", TS::PASS, "hdrBufferSem returned");
}

static void runGroupNetwork(PubSubClient& client) {
    Serial.println("[SELFTEST] --- NETWORK ---");

    if (!wifi_toggle) {
        report("NETWORK", "WiFi_Toggle", TS::WARN,
               "wifi_toggle=false — network tests skipped (send 'WIFI ON' to enable)");
        return;
    }

    {
        const bool connected = (WiFi.status() == WL_CONNECTED);
        if (!connected) {
            report("NETWORK", "WiFi_Status", TS::FAIL,
                   "not connected — all remaining network tests skipped");
            return;
        }
        const int rssi = WiFi.RSSI();
        const String ip = WiFi.localIP().toString();
        TS st = (rssi < -80) ? TS::WARN : TS::PASS;
        REPORT("NETWORK", "WiFi_Status", st,
               "connected IP=%s RSSI=%d dBm%s",
               ip.c_str(), rssi,
               (rssi < -80) ? " (WEAK — risk of upload failures)" : "");
    }

    {
        const bool mqtt_ok = client.connected();
        if (!mqtt_ok) {
            report("NETWORK", "MQTT_Status", TS::WARN,
                   "MQTT client not connected (broker may be unavailable or reconnect pending)");
        } else {
            report("NETWORK", "MQTT_Status", TS::PASS, "connected to broker");
        }
    }

    {
        struct tm ti;
        const bool ntp_ok = getLocalTime(&ti, 2000);
        if (!ntp_ok) {
            report("NETWORK", "NTP_Sync", TS::FAIL,
                   "getLocalTime() timed out — NTP server may be unreachable");
        } else {
            char ts[32];
            strftime(ts, sizeof(ts), "%Y-%m-%dT%H:%M:%S", &ti);
            const int year = ti.tm_year + 1900;
            if (year < 2024) {
                REPORT("NETWORK", "NTP_Sync", TS::WARN,
                       "time=%s — year < 2024, NTP sync may be stale", ts);
            } else {
                REPORT("NETWORK", "NTP_Sync", TS::PASS, "time=%s", ts);
            }
        }
    }

    {
        WiFiClient ftpProbe;
        const bool tcp_ok = ftpProbe.connect(FTP_SERVER, 21, 3000);
        if (!tcp_ok) {
            REPORT("NETWORK", "FTP_TCP_Connect", TS::FAIL,
                   "TCP connect to %s:21 failed (server down or firewall?)", FTP_SERVER);
        } else {
            unsigned long t = millis();
            while (ftpProbe.available() == 0 && millis() - t < 1500) delay(10);
            String banner = ftpProbe.available() ? ftpProbe.readStringUntil('\n') : "";
            ftpProbe.stop();
            banner.trim();
            if (banner.startsWith("220")) {
                REPORT("NETWORK", "FTP_TCP_Connect", TS::PASS,
                       "TCP OK port 21, banner: %.60s", banner.c_str());
            } else if (banner.length() == 0) {
                REPORT("NETWORK", "FTP_TCP_Connect", TS::WARN,
                       "TCP OK port 21 but no banner received within 1.5s");
            } else {
                REPORT("NETWORK", "FTP_TCP_Connect", TS::WARN,
                       "TCP OK port 21, unexpected banner: %.60s", banner.c_str());
            }
        }
    }
}

static void publishSelfTestSummary(PubSubClient& client, const String& deviceName,
                                   int pass, int warn, int fail, unsigned long elapsed_ms) {
    if (!client.connected()) return;

    char topic[80];
    snprintf(topic, sizeof(topic), "sensors/%s/selftest", deviceName.c_str());

    const char* result = (fail > 0) ? "FAIL" : (warn > 0) ? "WARN" : "PASS";

    char payload[200];
    snprintf(payload, sizeof(payload),
             "{\"pass\":%d,\"warn\":%d,\"fail\":%d,\"result\":\"%s\","
             "\"elapsed_ms\":%lu,\"fw\":\"%s\"}",
             pass, warn, fail, result, elapsed_ms, FIRMWARE_VERSION);

    client.publish(topic, payload, false);
    Serial.printf("[SELFTEST] MQTT published to %s: %s\n", topic, payload);
}

void runSelfTest(PubSubClient& client, const String& deviceName, const char* group) {
    setCpuFrequencyMhz(CPU_FREQ_ACTIVE);
    esp_task_wdt_reset();

    s_pass = 0; s_warn = 0; s_fail = 0;

    const unsigned long start_ms = millis();
    String grp = String(group);
    grp.toUpperCase();
    grp.trim();
    const bool runAll     = (grp == "ALL" || grp.length() == 0);
    const bool runConfig  = runAll || (grp == "CONFIG");
    const bool runMemory  = runAll || (grp == "MEMORY");
    const bool runSensor  = runAll || (grp == "SENSOR");
    const bool runCamera  = runAll || (grp == "CAMERA");
    const bool runNetwork = runAll || (grp == "NETWORK");

    if (!runConfig && !runMemory && !runSensor && !runCamera && !runNetwork) {
        Serial.printf("[SELFTEST] Unknown group '%s'. Valid: ALL|CONFIG|MEMORY|SENSOR|CAMERA|NETWORK\n",
                      group);
        return;
    }

    Serial.println("[SELFTEST] ================================================================");
    Serial.printf ("[SELFTEST] DEVICE:   %s\n",              deviceName.c_str());
    Serial.printf ("[SELFTEST] FIRMWARE: %s\n",              FIRMWARE_VERSION);
    Serial.printf ("[SELFTEST] UPTIME:   %lu ms\n",          millis());
    Serial.printf ("[SELFTEST] GROUP(S): %s\n",              group);
    Serial.printf ("[SELFTEST] CORE:     %d\n",              xPortGetCoreID());
    Serial.printf ("[SELFTEST] FREE_HEAP: %u B  FREE_PSRAM: %u B\n",
                   heap_caps_get_free_size(MALLOC_CAP_8BIT),
                   heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    Serial.println("[SELFTEST] ================================================================");

    if (runConfig)  { runGroupConfig();               esp_task_wdt_reset(); }
    if (runMemory)  { runGroupMemory();               esp_task_wdt_reset(); }
    if (runSensor)  { runGroupSensor();               esp_task_wdt_reset(); }
    if (runCamera)  { runGroupCamera();               esp_task_wdt_reset(); }
    if (runNetwork) { runGroupNetwork(client);        esp_task_wdt_reset(); }

    const unsigned long elapsed_ms = millis() - start_ms;
    const char* overall = (s_fail > 0) ? "FAIL"
                        : (s_warn > 0) ? "PASS (with warnings)"
                        :                "PASS";

    Serial.println("[SELFTEST] ================================================================");
    Serial.printf ("[SELFTEST] SUMMARY   pass=%d  warn=%d  fail=%d  elapsed=%lu ms\n",
                   s_pass, s_warn, s_fail, elapsed_ms);
    Serial.printf ("[SELFTEST] RESULT    %s\n", overall);
    Serial.println("[SELFTEST] ================================================================");

    publishSelfTestSummary(client, deviceName, s_pass, s_warn, s_fail, elapsed_ms);
}
