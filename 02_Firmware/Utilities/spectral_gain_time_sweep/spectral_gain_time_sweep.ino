/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* AS7265x gain x integration time sweep built on the Main firmware sources.
* Writes one CSV row per gain/time combination via FTP or serial.
*/

#include "../../Main/config.h"
#include "../../Main/datastructures.h"
#include "../../Main/globals.h"
#include "../../Main/calibration.h"
#include "../../Main/sensor_init.h"
#include "../../Main/measurement.h"
#include "../../Main/comms.h"
#include "../../Main/camera.h"
#include <Wire.h>
#include <climits>

#include "../../Main/src/sensors/SHT4X.cpp"
#include "../../Main/src/sensors/TSL2591.cpp"
#include "../../Main/src/sensors/AS7265X.cpp"
#include "../../Main/src/sensors/AS7331.cpp"
#include "../../Main/calibration.cpp"
#include "../../Main/sensor_init.cpp"
#include "../../Main/measurement.cpp"
#include "../../Main/comms.cpp"
#include "../../Main/camera.cpp"

#include <cmath>

#define SWEEP_DEVICE_NAME    "sensor11"
#define SWEEP_UPLOAD_STAGGER 15000

String deviceName = SWEEP_DEVICE_NAME;
bool cam_toggle  = true;
bool hdr_toggle  = true;
bool jpeg_toggle = false;
bool wifi_toggle = true;
bool verbose_sensor_setup = false;
CalibrationProfile active_profile;

volatile bool triggerSensorMeasurement = false;
volatile bool triggerCameraCapture     = false;
float S_wait_time = 10.0f;
float C_wait_time = 10.0f;

std::vector<int> exposure_values = {
    1, 2, 4, 8, 16, 32, 64, 128, 256, 512,
    1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072
};
int  hdr_avg_frames     = 3;
bool hdr_sat_fill       = true;
bool  hdr_early_term    = true;
float hdr_et_pct        = 98.0f;
int   hdr_et_min_exp    = 64;
float hdr_et_radius_pct = 95.0f;

bool cam_cal_enable  = false;
bool cam_vign_enable = false;
bool cam_crop_enable = false;
const CameraCalibration* cam_cal_colour = nullptr;
float cam_cal_scale_override   = 1.0f;
bool  cam_cal_scale_overridden = false;

int S_gainValue       = 64;
int U_gainValue       = 128;
int I_gainValue       = 1;
int S_integrationTime = 100;
int U_integrationTime = 512;
int I_integrationTime = 300;
time_t nextSensorTrigger = LONG_MAX;
time_t nextCameraTrigger = LONG_MAX;
int    upload_stagger_ms = SWEEP_UPLOAD_STAGGER;

QueueHandle_t     uploadQueue       = NULL;
SemaphoreHandle_t i2cMutex          = NULL;
SemaphoreHandle_t hdrBufferSem      = NULL;
TaskHandle_t      captureTaskHandle = NULL;
TaskHandle_t      networkTaskHandle = NULL;

char ftp_user[] = FTP_USER;
char ftp_pass[] = FTP_PASS;
WiFiClient      espClient;
PubSubClient    client(espClient);
ESP32_FTPClient ftp(FTP_SERVER, ftp_user, ftp_pass, 5000, 0);
Preferences     preferences;

static float measureSmartLux() {
    static constexpr float GAIN_MULTS[] = {1.0f, 25.0f, 428.0f, 9876.0f};
    static constexpr int   GAIN_VALS[]  = {0, 1, 2, 3};

    tsl.Set_GAIN(TSL2591_GAIN_LOW);
    tsl.Set_Integration_Time(TSL2591_TIME_100MS);
    tslApplyAndFlush(100);
    uint16_t scout_ch0 = tsl.all_data;
    I_gainValue       = 0;
    I_integrationTime = 100;

    int gi = 3;
    if      (scout_ch0 > 1500) gi = 0;
    else if (scout_ch0 >   60) gi = 1;
    else if (scout_ch0 >    5) gi = 2;

    int final_time_ms = 600;
    if (scout_ch0 > 0) {
        float est     = static_cast<float>(scout_ch0) * GAIN_MULTS[gi];
        float t_ms    = 100.0f * (25000.0f / est);
        final_time_ms = static_cast<int>(roundf(t_ms / 100.0f)) * 100;
        final_time_ms = constrain(final_time_ms, 100, 600);
    }

    setGain('I', GAIN_VALS[gi]);
    setIntegrationTime('I', final_time_ms);
    float lux = tsl.lux_data;

    return lux;
}

static void performUploadStagger() {
    if (!wifi_toggle || WiFi.status() != WL_CONNECTED) return;
    int devNum = deviceName.substring(6).toInt();
    unsigned long staggerMs = static_cast<unsigned long>(max(0, devNum - 1))
                              * static_cast<unsigned long>(upload_stagger_ms);
    if (staggerMs > 0) {
        Serial.printf("Upload stagger: %s -> %lu ms delay before FTP\n",
                      deviceName.c_str(), staggerMs);
        while (staggerMs > 0) {
            if (WiFi.status() != WL_CONNECTED) {
                Serial.println("Stagger aborted: WiFi lost.");
                break;
            }
            unsigned long chunk = min(staggerMs, 30000UL);
            delay(chunk);
            maintainMqtt();
            staggerMs -= chunk;
        }
    }
}

static void uploadSweepCsv(const std::vector<String>& rows, const char* fileName) {
    if (rows.empty()) {
        Serial.println("No valid sweep points — skipping CSV upload.");
        return;
    }

    const size_t BUF_SIZE = 300 + rows.size() * 400;
    char* buf = static_cast<char*>(heap_caps_malloc(BUF_SIZE, MALLOC_CAP_SPIRAM));
    if (!buf) {
        Serial.println("ERROR: PSRAM alloc failed for CSV buffer — printing to serial.");
        for (const auto& r : rows) Serial.println(r);
        return;
    }

    int off = 0;
    off += snprintf(buf + off, BUF_SIZE - off,
        "S_gain,S_time,U_gain,U_time,I_gain,I_time,"
        "temperature,humidity,tsl_ch0,tsl_ch1,raw_lux,cal_lux,"
        "raw_uvc,raw_uvb,raw_uva,"
        "raw_ch1,raw_ch2,raw_ch3,raw_ch4,raw_ch5,raw_ch6,"
        "raw_ch7,raw_ch8,raw_ch9,raw_ch10,raw_ch11,raw_ch12,"
        "raw_ch13,raw_ch14,raw_ch15,raw_ch16,raw_ch17,raw_ch18,"
        "cal_uvc,cal_uvb,cal_uva,"
        "cal_410nm,cal_435nm,cal_460nm,cal_485nm,cal_510nm,cal_535nm,"
        "cal_560nm,cal_585nm,cal_610nm,cal_645nm,cal_680nm,cal_705nm,"
        "cal_730nm,cal_760nm,cal_810nm,cal_860nm,cal_900nm,cal_940nm\n");

    for (const auto& row : rows) {
        size_t rlen = row.length();
        if (off + static_cast<int>(rlen) + 2 < static_cast<int>(BUF_SIZE)) {
            memcpy(buf + off, row.c_str(), rlen);
            off += static_cast<int>(rlen);
            buf[off++] = '\n';
        } else {
            Serial.println("WARNING: CSV buffer full — truncating output.");
            break;
        }
    }
    buf[off] = '\0';

    if (wifi_toggle && WiFi.status() == WL_CONNECTED) {
        char tmpName[84];
        snprintf(tmpName, sizeof(tmpName), "%s.tmp", fileName);

        bool uploaded = false;
        bool deadlineAborted = false;
        for (int attempt = 1; attempt <= 6 && !uploaded; attempt++) {
            if (isUploadDeadlineImminent()) {
                Serial.println("CSV upload aborted: next measurement imminent.");
                deadlineAborted = true;
                break;
            }
            if (WiFi.status() != WL_CONNECTED) {
                Serial.printf("FTP CSV: WiFi down, attempt %d/6 -- waiting 5s...\n", attempt);
                for (int i = 0; i < 10; i++) { delay(500); maintainMqtt(); }
                continue;
            }

            ftp.OpenConnection();
            ftp.ChangeWorkDir(FTP_LANDING);
            ftp.InitFile("Type A");
            ftp.NewFile(tmpName);
            ftp.Write(buf);
            ftp.CloseFile();

            char fromBuf[84], toBuf[84];
            strncpy(fromBuf, tmpName, sizeof(fromBuf));
            fromBuf[sizeof(fromBuf)-1] = '\0';
            strncpy(toBuf, fileName, sizeof(toBuf));
            toBuf[sizeof(toBuf)-1] = '\0';
            ftp.RenameFile(fromBuf, toBuf);
            ftp.CloseConnection();
            uploaded = true;
        }

        if (uploaded) {
            Serial.printf("Uploaded: %s (%d bytes, %d points)\n",
                          fileName, off, static_cast<int>(rows.size()));

            char topic[100];
            snprintf(topic, sizeof(topic), "sensors/%s/new_csv", deviceName.c_str());
            client.publish(topic, fileName);
        } else if (deadlineAborted) {
            Serial.printf("CSV skipped (deadline): %s\n", fileName);
        } else {
            Serial.printf("CRITICAL: CSV upload failed after 6 attempts: %s -- rebooting.\n", fileName);
            heap_caps_free(buf);
            saveCrashReason("Sweep CSV upload failed after 6 attempts");
            delay(1000);
            ESP.restart();
        }
    } else {
        Serial.printf("--- CSV: %s ---\n", fileName);
        Serial.print(buf);
        Serial.println("--- END CSV ---");
    }

    heap_caps_free(buf);
}

static FullSensorReading readCombinedPoint(int s_gain, int s_time, int u_gain, int u_time) {
    FullSensorReading reading;
    float temp_ignore;

    setGain('S', s_gain);
    setIntegrationTime('S', s_time);
    setGain('U', u_gain);
    setIntegrationTime('U', u_time);

    unsigned long s_period_ms = static_cast<unsigned long>(
        S_integrationTime * AS7265X_BASE_PERIOD_MS * AS7265X_MODE2_MULTIPLIER);
    unsigned long u_period_ms = static_cast<unsigned long>(U_integrationTime);

    delay(max(s_period_ms, u_period_ms));

    bool as7265x_ready = false;
    bool as7331_ready  = false;
    unsigned long deadline = millis() + max(s_period_ms, u_period_ms) + 300;
    do {
        if (!as7265x_ready) as7265x_ready = as7265x.Get_DataStatus();
        if (!as7331_ready)  as7331_ready  = (as7331.Get_Status() & 0x0008) != 0;
        if (as7265x_ready && as7331_ready) break;
        if (millis() >= deadline) break;
        maintainMqtt();
        delay(10);
    } while (true);

    if (!sht.Measure(&reading.temperature, &reading.humidity, SHT4X_REG_MEASURE_HIGH)) {
        Serial.printf("  s=%d/%d u=%d/%d -> SHT4x FAIL\n", s_gain, s_time, u_gain, u_time);
        reading.isValid = false;
        return reading;
    }
    reading.temperature /= 1000.0f;
    reading.humidity    /= 1000.0f;

    if (!as7265x_ready || !as7331_ready) {
        Serial.printf("  s=%d/%d u=%d/%d -> TIMEOUT (spec=%d uv=%d)\n",
                      s_gain, s_time, u_gain, u_time, as7265x_ready, as7331_ready);
        reading.isValid = false;
        return reading;
    }

    as7331.Get_All(&temp_ignore, &reading.raw_uva, &reading.raw_uvb, &reading.raw_uvc);
    as7265x.Get_Channel_Raw(reading.raw_spectral);
    reading.num_accumulations = 1;

    reading.spectral_peak = 0;
    for (int i = 0; i < 18; i++)
        if (reading.raw_spectral[i] > reading.spectral_peak)
            reading.spectral_peak = reading.raw_spectral[i];

    reading.tsl_ch0 = tsl.all_data;
    reading.tsl_ch1 = tsl.ir_data;
    reading.isValid = true;

    Serial.printf("  s=%2d/%3d u=%4d/%5d -> spec=%5u  uva=%5u uvb=%5u uvc=%5u\n",
                  s_gain, s_time, u_gain, u_time,
                  reading.spectral_peak,
                  reading.raw_uva, reading.raw_uvb, reading.raw_uvc);
    return reading;
}

static void performGainTimeSweep(struct tm triggerTime, bool haveTime) {
    const int SWEEP_STEPS = 24;
    const int s_gains[24] = {
         1,  1,  1,  1,  1,  1,  1,  1,
        16, 16, 16, 16, 16, 16, 16, 16,
        64, 64, 64, 64, 64, 64, 64, 64
    };
    const int s_times[24] = {
          1,   4,  12,  36, 100, 170, 220, 255,
          1,   4,  12,  36, 100, 170, 220, 255,
          1,   4,  12,  36, 100, 170, 220, 255
    };
    const int u_gains[24] = {
            1,    1,    1,    1,
           16,   16,   16,   16,
           64,   64,   64,   64,
          256,  256,  256,  256,
         1024, 1024, 1024, 1024,
         2048, 2048, 2048, 2048
    };
    const int u_times[24] = {
         1,  4, 16, 64,
         1,  4, 16, 64,
         1,  4, 16, 64,
         1,  4, 16, 64,
         1,  4, 16, 64,
         1,  4, 16, 64
    };

    Serial.println("\n=== Starting Combined Gain x Integration-Time Characterisation Sweep ===");
    Serial.printf("  %d co-varied (S_gain, S_time, U_gain, U_time) steps\n", SWEEP_STEPS);

    float raw_lux        = measureSmartLux();
    uint16_t sweep_tsl_ch0 = tsl.all_data;
    uint16_t sweep_tsl_ch1 = tsl.ir_data;

    float sweep_temperature = 25.0f;
    float sweep_humidity = 50.0f;
    if (sht.Measure(&sweep_temperature, &sweep_humidity, SHT4X_REG_MEASURE_HIGH)) {
        sweep_temperature /= 1000.0f;
        sweep_humidity /= 1000.0f;
    }

    const TempCoeffSet& lux_tc = getLuxTempCoefficients();
    float lux_temp_factor = (lux_tc.a * sweep_temperature * sweep_temperature)
                          + (lux_tc.b * sweep_temperature)
                          + lux_tc.c;
    if (fabsf(lux_temp_factor) < 1e-6f) lux_temp_factor = 1.0f;
    float calibrated_lux = (raw_lux / lux_temp_factor) * active_profile.lux_factor;

    std::vector<String> csv_rows;
    csv_rows.reserve(SWEEP_STEPS);

    for (int i = 0; i < SWEEP_STEPS; i++) {
        FullSensorReading raw = readCombinedPoint(s_gains[i], s_times[i], u_gains[i], u_times[i]);
        if (!raw.isValid) continue;

        raw.tsl_ch0 = sweep_tsl_ch0;
        raw.tsl_ch1 = sweep_tsl_ch1;
        raw.raw_lux = raw_lux;
        raw.cal_lux = calibrated_lux;

        FullSensorReading cal = calibrateReading(
            raw, active_profile,
            s_gains[i], u_gains[i],
            s_times[i], u_times[i]);

        csv_rows.push_back(readingToCsv(
            cal,
            s_gains[i], s_times[i],
            u_gains[i], u_times[i],
            I_gainValue, I_integrationTime,
            active_profile));
    }

    char fileName[80];
    if (haveTime) {
        char ts[20];
        strftime(ts, sizeof(ts), "%Y%m%d_%H%M%S", &triggerTime);
        snprintf(fileName, sizeof(fileName), "sweep_%s_%s.csv", ts, deviceName.c_str());
    } else {
        snprintf(fileName, sizeof(fileName), "sweep_%lu_%s.csv",
                 millis(), deviceName.c_str());
    }

    if (wifi_toggle && WiFi.status() == WL_CONNECTED && client.connected()) {
        publishHealthStatus(client, deviceName);
        publishMetric(client, deviceName, "temperature",  sweep_temperature, 1, true);
        publishMetric(client, deviceName, "humidity",     sweep_humidity, 0, true);
        publishMetric(client, deviceName, "illuminance",  calibrated_lux, 0, true);
    }

    EncodedHDR enc;
    CapturedJPEG jpeg;
    bool haveHdr  = false;
    bool haveJpeg = false;

    if (cam_toggle) {
        Serial.println("\n--- Camera capture ---");
        if (hdr_toggle) {
            enc = captureAndEncodeHDR(triggerTime);
            if (enc.valid) {
                char hdrName[72];
                snprintf(hdrName, sizeof(hdrName), "sweep_%s", enc.filename);
                strncpy(enc.filename, hdrName, sizeof(enc.filename) - 1);
                enc.filename[sizeof(enc.filename) - 1] = '\0';
                Serial.printf("HDR: %s (%zu bytes, %d/%d brackets)\n",
                              enc.filename, enc.len,
                              enc.brackets_used, enc.brackets_total);
                haveHdr = true;
            } else {
                Serial.println("HDR capture failed.");
            }

            if (jpeg_toggle) {
                jpeg = captureContextJPEG(triggerTime);
                if (jpeg.valid) {
                    char jpegName[72];
                    snprintf(jpegName, sizeof(jpegName), "sweep_%s", jpeg.filename);
                    strncpy(jpeg.filename, jpegName, sizeof(jpeg.filename) - 1);
                    jpeg.filename[sizeof(jpeg.filename) - 1] = '\0';
                    Serial.printf("JPEG: %s (%zu bytes)\n", jpeg.filename, jpeg.len);
                    haveJpeg = true;
                } else {
                    Serial.println("JPEG context capture failed.");
                }
            }
        } else {
            camera_fb_t* fb = esp_camera_fb_get();
            if (fb) {
                Serial.printf("JPEG: %zu bytes\n", fb->len);
                esp_camera_fb_return(fb);
            } else {
                Serial.println("JPEG capture failed.");
            }
        }
    }

    performUploadStagger();
    uploadSweepCsv(csv_rows, fileName);

    if (haveHdr) {
        if (wifi_toggle && WiFi.status() == WL_CONNECTED) {
            uploadEncodedHDR(ftp, FTP_LANDING, enc);
        }
    }

    if (haveJpeg) {
        if (wifi_toggle && WiFi.status() == WL_CONNECTED) {
            uploadContextJPEG(ftp, FTP_LANDING, jpeg);
        } else {
            releaseJPEG(jpeg);
        }
    }

    if (cam_toggle && hdr_toggle) {
        freeHDRBuffers();
        powerDownCamera();
    }

    Serial.printf("\n=== Sweep complete: %d/%d rows ===\n",
                  static_cast<int>(csv_rows.size()), SWEEP_STEPS);
    Serial.println("Send 'S' to sweep again.\n");
}

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);
    Serial.begin(115200);

    Serial.printf("\n\n=== Gain × Integration-Time Sweep — %s ===\n", SWEEP_DEVICE_NAME);
    Serial.printf("  24 co-varied (S_gain, S_time, U_gain, U_time) steps\n");

    active_profile = getCalibrationProfile(SWEEP_DEVICE_NAME);
    if (active_profile.C_p[0] == 1.0f)
        Serial.println("WARNING: Default (uncorrected) calibration profile active.");
    else
        Serial.println("Calibration profile loaded.");

    cam_cal_colour = &getCameraCalibration(SWEEP_DEVICE_NAME);

    preferences.begin("sensor-settings", false);
    S_wait_time = preferences.getFloat("s_wait_time", S_wait_time);
    C_wait_time = preferences.getFloat("c_wait_time", C_wait_time);
    upload_stagger_ms = preferences.getInt("upload_stagger", upload_stagger_ms);
    preferences.end();
    Serial.printf("Sweep interval: %.1f min\n", S_wait_time);

    Wire.begin();
    setupTSL2591();
    setupAS7331();
    setupAS7265X();
    setupSHT4X();
    Serial.println("All sensors initialised.");

    if (psramInit()) {
        Serial.printf("PSRAM OK — free: %u bytes\n",
                      heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    } else {
        Serial.println("WARNING: PSRAM init failed — sweep CSV may not fit in heap.");
    }

    if (cam_toggle) {
        if (hdr_toggle) {
            setupOV5640_YUV422_VGA();
            Serial.println("Camera: YUV422 VGA (HDR mode).");
        } else {
            setupOV5640_JPEG_WQXGA();
            Serial.println("Camera: JPEG WQXGA.");
        }
    }

    Serial.println("Connecting to WiFi... (type 'WIFI OFF' to cancel)");
    unsigned long connection_start_time = millis();

    if (wifi_toggle) {
        WiFi.disconnect(true, true);
        delay(100);
        WiFi.mode(WIFI_STA);
        WiFi.begin(WIFI_SSID, WIFI_PASS);
    }

    while (wifi_toggle && WiFi.status() != WL_CONNECTED && (millis() - connection_start_time) < 60000) {
        if (Serial.available()) handleSerialCommand(Serial.readStringUntil('\n'));
        Serial.print(".");
        delay(500);
    }

    if (wifi_toggle && WiFi.status() == WL_CONNECTED) {
        Serial.printf("\nWiFi connected! IP: %s\n", WiFi.localIP().toString().c_str());
        setupMqtt(client, deviceName, onMqttMessage);
        configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);

        Serial.print("NTP sync");
        struct tm ntpInfo;
        for (int i = 0; i < 10; i++) {
            if (getLocalTime(&ntpInfo)) break;
            Serial.print(".");
            delay(500);
        }
        if (getLocalTime(&ntpInfo)) {
            time_t now_unix = time(nullptr);
            int interval_sec = max(1, static_cast<int>(S_wait_time * 60.0f));
            time_t secs_into = now_unix % interval_sec;
            nextSensorTrigger = now_unix + (interval_sec - secs_into);
            long secs_to = (long)(nextSensorTrigger - now_unix);
            Serial.printf(" OK (%02d:%02d:%02d) -- first sweep in %ldm %02lds\n",
                          ntpInfo.tm_hour, ntpInfo.tm_min, ntpInfo.tm_sec,
                          secs_to / 60, secs_to % 60);
        } else {
            Serial.println(" TIMEOUT -- millis() scheduling.");
        }
    } else {
        Serial.println("\nProceeding in OFFLINE mode.");
    }

    setSpectralLeds(false);
    Serial.println("\nReady. Send 'S' via serial or MQTT trigger to start sweep.\n");
}

void loop() {
    if (wifi_toggle && WiFi.status() == WL_CONNECTED) {
        handleMqtt(client, deviceName);
    }

    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim();
        String upper = cmd;
        upper.toUpperCase();
        if (upper == "S") {
            triggerSensorMeasurement = true;
            Serial.println("Sweep triggered.");
        } else {
            handleSerialCommand(cmd);
        }
    }

    static unsigned long lastSweepMs = 0;
    bool timerFired = false;
    bool ntpValid   = (time(nullptr) > 1000000000LL);
    if (wifi_toggle && WiFi.status() == WL_CONNECTED && ntpValid && nextSensorTrigger != LONG_MAX) {
        time_t now_unix = time(nullptr);
        if (now_unix >= nextSensorTrigger) {
            timerFired = true;
            int interval_sec = max(1, static_cast<int>(S_wait_time * 60.0f));
            nextSensorTrigger = now_unix + (interval_sec - (now_unix % interval_sec));
            nextCameraTrigger = nextSensorTrigger;
        }
    } else {
        unsigned long now = millis();
        unsigned long sweepInterval = static_cast<unsigned long>(S_wait_time * 60.0f * 1000.0f);
        if (now - lastSweepMs >= sweepInterval) {
            timerFired    = true;
            lastSweepMs   = now;
        }
    }

    if (triggerSensorMeasurement || timerFired) {
        triggerSensorMeasurement = false;

        struct tm triggerTime;
        bool haveTime = wifi_toggle && getLocalTime(&triggerTime);
        if (!haveTime) memset(&triggerTime, 0, sizeof(triggerTime));

        if (timerFired && haveTime) {
            struct tm nextTm;
            time_t nextTrigger = nextSensorTrigger;
            localtime_r(&nextTrigger, &nextTm);
            time_t now_unix = time(nullptr);
            Serial.printf("--- SWEEP: scheduled at %02d:%02d:%02d (next at %02d:%02d:%02d, %ldm %02lds) ---\n",
                          triggerTime.tm_hour, triggerTime.tm_min, triggerTime.tm_sec,
                          nextTm.tm_hour, nextTm.tm_min, nextTm.tm_sec,
                          static_cast<long>(nextSensorTrigger - now_unix) / 60,
                          static_cast<long>(nextSensorTrigger - now_unix) % 60);
        } else if (!timerFired) {
            Serial.println("--- SWEEP: on-demand trigger ---");
        }

        performGainTimeSweep(triggerTime, haveTime);
    }

    delay(20);
}
