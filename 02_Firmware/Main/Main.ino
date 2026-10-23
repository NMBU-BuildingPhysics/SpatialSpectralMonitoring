/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* Orchestrates hardware initialization, WiFi connection, and the
* main measurement loop (scheduled + on-demand spectral + camera capture).
*/

#include "config.h"
#include <Preferences.h>
#include <WiFi.h>
#include <Wire.h>
#include <time.h>
#include <climits>
#include <vector>
#include "globals.h"
#include "sensor_init.h"
#include "measurement.h"
#include "comms.h"
#include "camera.h"
#include <esp_task_wdt.h>
#include <esp_log.h>

String deviceName = DEVICE_NAME;
bool cam_toggle  = DEFAULT_CAM_TOGGLE;
bool hdr_toggle  = DEFAULT_HDR_TOGGLE;
bool jpeg_toggle = DEFAULT_JPEG_TOGGLE;
bool wifi_toggle = DEFAULT_WIFI_TOGGLE;
CalibrationProfile active_profile;

time_t nextSensorTrigger = LONG_MAX;
time_t nextCameraTrigger = LONG_MAX;
volatile bool triggerSensorMeasurement = false;
volatile bool triggerCameraCapture     = false;
float S_wait_time = DEFAULT_S_WAIT_TIME;
float C_wait_time = DEFAULT_C_WAIT_TIME;
int   upload_stagger_ms = UPLOAD_STAGGER_PER_DEVICE_MS;

// HDR brackets in OV5640 AEC units (1 unit = 1/16 line)
std::vector<int> exposure_values = {1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072};
int  hdr_avg_frames   = DEFAULT_HDR_AVG_FRAMES;
bool hdr_sat_fill     = DEFAULT_HDR_SAT_FILL;
bool  hdr_early_term    = DEFAULT_HDR_EARLY_TERM;
float hdr_et_pct        = DEFAULT_HDR_ET_PCT;
int   hdr_et_min_exp    = DEFAULT_HDR_ET_MIN_EXP;
float hdr_et_radius_pct = DEFAULT_HDR_ET_RADIUS;

bool cam_cal_enable  = DEFAULT_CAM_CAL_ENABLE;
bool cam_vign_enable = DEFAULT_CAM_VIGN_ENABLE;
bool cam_crop_enable = DEFAULT_CAM_CROP_ENABLE;
const CameraCalibration* cam_cal_colour = nullptr;
float cam_cal_scale_override   = 1.0f;
bool  cam_cal_scale_overridden = false;

int S_gainValue       = DEFAULT_S_GAIN;
int U_gainValue       = DEFAULT_U_GAIN;
int I_gainValue       = DEFAULT_I_GAIN;
int S_integrationTime = DEFAULT_S_INT_TIME;
int U_integrationTime = DEFAULT_U_INT_TIME;
int I_integrationTime = DEFAULT_I_INT_TIME;

char ftp_user[] = FTP_USER;
char ftp_pass[] = FTP_PASS;
WiFiClient      espClient;
PubSubClient    client(espClient);
ESP32_FTPClient ftp(FTP_SERVER, ftp_user, ftp_pass, 5000, 0);
Preferences     preferences;

QueueHandle_t     uploadQueue       = NULL;
SemaphoreHandle_t i2cMutex          = NULL;
SemaphoreHandle_t hdrBufferSem      = NULL;
TaskHandle_t      captureTaskHandle = NULL;
TaskHandle_t      networkTaskHandle = NULL;

void captureTask(void* param);
void networkTask(void* param);

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);  // LED off (active low)
    Serial.begin(115200);

    esp_log_level_set("*", ESP_LOG_DEBUG);

    Serial.println("Sensor name: " + deviceName);
    Serial.printf("Loading calibration profile for '%s'...\n", deviceName.c_str());
    active_profile = getCalibrationProfile(deviceName.c_str());
    if (active_profile.C_p[0] == 1.0f) {
        Serial.println("WARNING: Using default (uncorrected) profile. Check deviceName.");
    } else {
        Serial.println("Calibration profile loaded successfully.");
    }

    cam_cal_colour = &getCameraCalibration(deviceName.c_str());
    Serial.printf("Camera cal loaded: scale=%.2f, vign=[%.5f, %.5f, %.5f], center=(%.0f,%.0f)\n",
                  cam_cal_colour->cal_scale,
                  cam_cal_colour->vign_b, cam_cal_colour->vign_c, cam_cal_colour->vign_d,
                  cam_cal_colour->vign_cx, cam_cal_colour->vign_cy);
    Serial.printf("Camera cal crop: (%u,%u) %ux%u, toggles: cal=%d vign=%d crop=%d\n",
                  cam_cal_colour->crop_x, cam_cal_colour->crop_y,
                  cam_cal_colour->crop_w, cam_cal_colour->crop_h,
                  cam_cal_enable, cam_vign_enable, cam_crop_enable);

    preferences.begin("sensor-settings", false);
    S_wait_time = preferences.getFloat("s_wait_time", S_wait_time);
    C_wait_time = preferences.getFloat("c_wait_time", C_wait_time);
    upload_stagger_ms = preferences.getInt("upload_stagger", upload_stagger_ms);
    preferences.end();

    Wire.begin();

    const esp_task_wdt_config_t wdt_config = {
        .timeout_ms = 360000,
        .idle_core_mask = 0,
        .trigger_panic = true,
    };
    esp_err_t wdt_err = esp_task_wdt_init(&wdt_config);
    if (wdt_err == ESP_ERR_INVALID_STATE) {
        esp_task_wdt_reconfigure(&wdt_config);
    }

    setupTSL2591();
    setupAS7331();
    setupAS7265X();
    setupSHT4X();
    Serial.println("All sensors initialized.");

    if (psramInit()) {
        Serial.println("PSRAM initialized successfully");
    } else {
        Serial.println("PSRAM initialization failed");
    }
    Serial.printf("Free RAM: %d bytes, Free PSRAM: %d bytes\n",
                  heap_caps_get_free_size(MALLOC_CAP_8BIT),
                  heap_caps_get_free_size(MALLOC_CAP_SPIRAM));

    int deviceNum = deviceName.substring(6).toInt();
    if (wifi_toggle && deviceNum > 0) {
        int bootDelay = deviceNum * WIFI_BOOT_STAGGER_MS;
        Serial.printf("WiFi boot stagger: %d ms (device %d)\n", bootDelay, deviceNum);
        delay(bootDelay);
    }

    Serial.println("Connecting to WiFi... (type 'WIFI OFF' to cancel)");
    unsigned long connection_start_time = millis();

    if (wifi_toggle) {
        WiFi.disconnect(true);
        delay(100);
        WiFi.mode(WIFI_STA);
        WiFi.begin(WIFI_SSID, WIFI_PASS);
    }

    while (wifi_toggle && WiFi.status() != WL_CONNECTED && (millis() - connection_start_time) < 60000) {
        if (Serial.available()) {
            handleSerialCommand(Serial.readStringUntil('\n'));
        }
        Serial.print(".");
        delay(500);
    }

    if (wifi_toggle && WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi connected!");
        Serial.print("IP address: ");
        Serial.println(WiFi.localIP());

        // sensorNN expects IP x.x.x.1NN
        {
            int lastOctet  = WiFi.localIP()[3];
            int expectedOctet = 100 + deviceNum;
            if (lastOctet != expectedOctet) {
                Serial.printf("WARNING: Device/IP mismatch! '%s' expects .%d but got .%d\n",
                              deviceName.c_str(), expectedOctet, lastOctet);
            } else {
                Serial.printf("Device/IP check OK: '%s' → .%d\n",
                              deviceName.c_str(), lastOctet);
            }
        }

        setupMqtt(client, deviceName, onMqttMessage);
        configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER, "pool.ntp.org", "time.google.com");

        struct tm timeinfo;
        if (getLocalTime(&timeinfo)) {
            Serial.printf("Current time: %02d:%02d:%02d\n",
                          timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
        } else {
            Serial.println("Waiting for NTP sync...");
        }
    } else {
        Serial.println("\nProceeding in OFFLINE mode.");
    }

    setSpectralLeds(false);

    uploadQueue  = xQueueCreate(UPLOAD_QUEUE_DEPTH, sizeof(UploadItem));
    i2cMutex     = xSemaphoreCreateMutex();
    hdrBufferSem = xSemaphoreCreateBinary();
    xSemaphoreGive(hdrBufferSem);

    xTaskCreatePinnedToCore(captureTask, "capture", CAPTURE_TASK_STACK, NULL,
                            CAPTURE_TASK_PRIORITY, &captureTaskHandle, CAPTURE_TASK_CORE);
    xTaskCreatePinnedToCore(networkTask, "network", NETWORK_TASK_STACK, NULL,
                            NETWORK_TASK_PRIORITY, &networkTaskHandle, NETWORK_TASK_CORE);
    Serial.printf("Tasks created: capture (Core %d), network (Core %d)\n",
                  CAPTURE_TASK_CORE, NETWORK_TASK_CORE);
}

void captureTask(void* param) {
    esp_task_wdt_add(NULL);
    Serial.printf("Capture task started on Core %d\n", xPortGetCoreID());

    unsigned long lastOfflineMeasure = 0;
    unsigned long lastOfflineCameraCapture = 0;

    for (;;) {
        esp_task_wdt_reset();

        if (!wifi_toggle) {
            unsigned long now = millis();
            unsigned long offlineInterval = static_cast<unsigned long>(S_wait_time * 60.0f * 1000.0f);

            if (triggerSensorMeasurement || now - lastOfflineMeasure >= offlineInterval) {
                lastOfflineMeasure = now;
                triggerSensorMeasurement = false;
                setCpuFrequencyMhz(CPU_FREQ_ACTIVE);
                Serial.println("--- OFFLINE measurement ---");

                xSemaphoreTake(i2cMutex, portMAX_DELAY);
                FullSensorReading raw = performGoalSeekingMeasurement();
                xSemaphoreGive(i2cMutex);

                if (raw.isValid) {
                    const int eff_s_time = S_integrationTime * raw.num_accumulations;
                    FullSensorReading cal = calibrateReading(
                        raw, active_profile,
                        S_gainValue, U_gainValue,
                        eff_s_time, U_integrationTime);
                    Serial.println(readingToCsv(
                        cal,
                        S_gainValue, eff_s_time,
                        U_gainValue, U_integrationTime,
                        I_gainValue, I_integrationTime,
                        active_profile,
                        nullptr, 0, millis()));
                } else {
                    Serial.println("Offline: invalid reading.");
                }
            }

            if (cam_toggle) {
                unsigned long cameraInterval = static_cast<unsigned long>(C_wait_time * 60.0f * 1000.0f);
                if (triggerCameraCapture || now - lastOfflineCameraCapture >= cameraInterval) {
                    lastOfflineCameraCapture = now;
                    triggerCameraCapture = false;
                    setCpuFrequencyMhz(CPU_FREQ_ACTIVE);
                    Serial.println("--- OFFLINE camera capture ---");

                    if (hdr_toggle) {
                        HdrBuffer hdr = captureHDRMerged();
                        if (hdr.isValid) {
                            Serial.printf("HDR OK: %ux%u px, %d ch, brackets %d/%d\n",
                                          hdr.width, hdr.height, hdr.channels,
                                          hdr.brackets_used, hdr.brackets_total);
                        } else {
                            Serial.println("HDR capture failed.");
                        }
                        if (hdr.data) { hdr.data = nullptr; }

                        if (jpeg_toggle) {
                            freeHDRBuffers();
                            Serial.println("JPEG: Capturing WQXGA auto-exposure context image...");
                            reinitCamera(false);
                            for (int i = 0; i < 10; i++) {
                                camera_fb_t* flush = esp_camera_fb_get();
                                if (flush) esp_camera_fb_return(flush);
                                delay(150);
                            }
                            camera_fb_t* jfb = esp_camera_fb_get();
                            if (jfb) {
                                Serial.printf("JPEG OK: %ux%u px, %u bytes (not uploaded)\n",
                                              jfb->width, jfb->height,
                                              static_cast<unsigned>(jfb->len));
                                esp_camera_fb_return(jfb);
                            } else {
                                Serial.println("JPEG capture failed.");
                            }
                        } else {
                            Serial.println("JPEG: skipped (jpeg_toggle off).");
                        }

                        sensor_t* s = esp_camera_sensor_get();
                        if (s) s->set_reg(s, 0x3008, 0xff, 0x42);
                    } else if (jpeg_toggle) {
                        camera_fb_t* fb = esp_camera_fb_get();
                        if (fb) {
                            Serial.printf("JPEG OK: %ux%u px, %u bytes\n",
                                          fb->width, fb->height,
                                          static_cast<unsigned>(fb->len));
                            esp_camera_fb_return(fb);
                        } else {
                            Serial.println("JPEG capture failed.");
                        }
                    } else {
                        Serial.println("CAM: both HDR and JPEG off — skipping capture.");
                    }
                }
            }

            setCpuFrequencyMhz(CPU_FREQ_IDLE);
            ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000));
            continue;
        }

        struct tm timeinfo;
        if (!getLocalTime(&timeinfo)) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        time_t now_unix = mktime(&timeinfo);

        if (nextSensorTrigger == LONG_MAX) {
            int s_int = max(1, static_cast<int>(S_wait_time * 60.0f));
            int c_int = max(1, static_cast<int>(C_wait_time * 60.0f));
            nextSensorTrigger = now_unix + (s_int - (now_unix % s_int));
            nextCameraTrigger = now_unix + (c_int - (now_unix % c_int));
            Serial.printf("First sensor trigger in %ldm %02lds, camera in %ldm %02lds\n",
                          static_cast<long>(nextSensorTrigger - now_unix) / 60,
                          static_cast<long>(nextSensorTrigger - now_unix) % 60,
                          static_cast<long>(nextCameraTrigger - now_unix) / 60,
                          static_cast<long>(nextCameraTrigger - now_unix) % 60);
        }

        bool isSensorScheduled = (now_unix >= nextSensorTrigger);
        bool sensorTriggered = triggerSensorMeasurement || isSensorScheduled;
        bool isCameraScheduled = (now_unix >= nextCameraTrigger);
        bool cameraTriggered = triggerCameraCapture || isCameraScheduled;

        if (!sensorTriggered && !cameraTriggered) {
            setCpuFrequencyMhz(CPU_FREQ_IDLE);
            ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000));
            continue;
        }

        setCpuFrequencyMhz(CPU_FREQ_ACTIVE);

        UploadItem pendingCsvItem = {};
        bool hasPendingCsv = false;

        if (sensorTriggered) {
            struct tm triggerTime = timeinfo;  // timestamp at trigger, not after the measurement

            if (isSensorScheduled) {
                int sensor_interval_sec = max(1, static_cast<int>(S_wait_time * 60.0f));
                nextSensorTrigger = now_unix + (sensor_interval_sec
                                  - (now_unix % sensor_interval_sec));
                Serial.printf("--- SENSOR: scheduled at %02d:%02d:%02d (next in %ldm %02ds) ---\n",
                              triggerTime.tm_hour, triggerTime.tm_min, triggerTime.tm_sec,
                              sensor_interval_sec / 60, sensor_interval_sec % 60);
            } else {
                Serial.println("--- SENSOR: on-demand trigger ---");
            }

            xSemaphoreTake(i2cMutex, portMAX_DELAY);
            FullSensorReading raw = performGoalSeekingMeasurement();
            xSemaphoreGive(i2cMutex);

            if (raw.isValid) {
                const int eff_s_time = S_integrationTime * raw.num_accumulations;
                FullSensorReading cal = calibrateReading(
                    raw, active_profile,
                    S_gainValue, U_gainValue,
                    eff_s_time, U_integrationTime);

                UploadItem item = {};
                item.type = UploadType::CSV;
                String csvStr = readingToCsv(
                    cal,
                    S_gainValue, eff_s_time,
                    U_gainValue, U_integrationTime,
                    I_gainValue, I_integrationTime,
                    active_profile,
                    &triggerTime,
                    WiFi.RSSI(),
                    millis());
                Serial.println(csvStr);
                strncpy(item.csv.csv, csvStr.c_str(), sizeof(item.csv.csv) - 1);
                item.csv.csv[sizeof(item.csv.csv) - 1] = '\0';

                strftime(item.csv.filename, sizeof(item.csv.filename), "%Y%m%d_%H%M%S", &triggerTime);
                snprintf(item.csv.filename + strlen(item.csv.filename),
                         sizeof(item.csv.filename) - strlen(item.csv.filename),
                         "_%s.csv", deviceName.c_str());
                item.csv.temperature = cal.temperature;
                item.csv.humidity = cal.humidity;
                item.csv.cal_lux = cal.cal_lux;
                item.csv.num_accumulations = cal.num_accumulations;

                // Queue the CSV after the HDR so one upload stagger covers both files
                if (cameraTriggered && cam_toggle && (hdr_toggle || jpeg_toggle)) {
                    pendingCsvItem = item;
                    hasPendingCsv  = true;
                    Serial.println("CSV deferred — will enqueue after HDR/JPEG.");
                } else {
                    if (xQueueSend(uploadQueue, &item, pdMS_TO_TICKS(5000)) != pdTRUE) {
                        Serial.println("WARNING: Upload queue full — CSV dropped.");
                    }
                }
            }
            triggerSensorMeasurement = false;
        }

        if (cameraTriggered) {
            if (isCameraScheduled) {
                int camera_interval_sec = max(1, static_cast<int>(C_wait_time * 60.0f));
                nextCameraTrigger = now_unix + (camera_interval_sec
                                 - (now_unix % camera_interval_sec));
                Serial.printf("--- CAMERA: scheduled at %02d:%02d:%02d (next in %ldm %02ds) ---\n",
                              timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec,
                              camera_interval_sec / 60, camera_interval_sec % 60);
            } else {
                Serial.println("--- CAMERA: on-demand trigger ---");
            }

            if (cam_toggle && hdr_toggle) {
                // hdrBufferSem is given back by the network task after the upload
                if (xSemaphoreTake(hdrBufferSem, pdMS_TO_TICKS(30000)) == pdTRUE) {
                    EncodedHDR encodedHdr = captureAndEncodeHDR(timeinfo);
                    powerDownCamera();

                    if (encodedHdr.valid) {
                        UploadItem item = {};
                        item.type = UploadType::HDR;
                        item.hdr.data = encodedHdr.data;
                        item.hdr.len = encodedHdr.len;
                        strncpy(item.hdr.filename, encodedHdr.filename, sizeof(item.hdr.filename) - 1);
                        item.hdr.filename[sizeof(item.hdr.filename) - 1] = '\0';
                        item.hdr.brackets_used = encodedHdr.brackets_used;
                        item.hdr.brackets_total = encodedHdr.brackets_total;

                        if (hasPendingCsv) {
                            if (xQueueSend(uploadQueue, &pendingCsvItem, pdMS_TO_TICKS(5000)) != pdTRUE) {
                                Serial.println("WARNING: Upload queue full — deferred CSV dropped.");
                            }
                            hasPendingCsv = false;
                        }
                        if (xQueueSend(uploadQueue, &item, pdMS_TO_TICKS(5000)) != pdTRUE) {
                            Serial.println("WARNING: Upload queue full — HDR dropped.");
                            freeHDRBuffers();
                            xSemaphoreGive(hdrBufferSem);
                        }
                    } else {
                        freeHDRBuffers();
                        xSemaphoreGive(hdrBufferSem);
                    }
                } else {
                    Serial.println("WARNING: HDR buffer busy — skipping capture.");
                }
            }

            if (cam_toggle && jpeg_toggle) {
                CapturedJPEG jpeg = captureContextJPEG(timeinfo);
                powerDownCamera();

                if (jpeg.valid) {
                    UploadItem item = {};
                    item.type = UploadType::JPEG;
                    item.jpeg.data = jpeg.data;
                    item.jpeg.len = jpeg.len;
                    strncpy(item.jpeg.filename, jpeg.filename, sizeof(item.jpeg.filename) - 1);
                    item.jpeg.filename[sizeof(item.jpeg.filename) - 1] = '\0';
                    item.jpeg.fb = jpeg._fb;
                    jpeg._fb = nullptr;
                    jpeg.data = nullptr;
                    jpeg.valid = false;

                    if (xQueueSend(uploadQueue, &item, pdMS_TO_TICKS(5000)) != pdTRUE) {
                        Serial.println("WARNING: Upload queue full — JPEG dropped.");
                        if (item.jpeg.fb) {
                            esp_camera_fb_return(static_cast<camera_fb_t*>(item.jpeg.fb));
                        }
                    }
                }
            }

            if (cam_toggle && !hdr_toggle && !jpeg_toggle) {
                Serial.println("CAM: both HDR and JPEG off — skipping capture.");
            }

            powerDownCamera();
            triggerCameraCapture = false;
        }

        if (hasPendingCsv) {
            if (xQueueSend(uploadQueue, &pendingCsvItem, pdMS_TO_TICKS(5000)) != pdTRUE) {
                Serial.println("WARNING: Upload queue full — CSV dropped.");
            }
            hasPendingCsv = false;
        }
    }
}

void networkTask(void* param) {
    esp_task_wdt_add(NULL);
    Serial.printf("Network task started on Core %d\n", xPortGetCoreID());

    bool networkInitialized = false;
    unsigned long lastWifiAttempt = 0;
    int ntp_init_retries = 0;
    time_t lastNtpResync = 0;

    for (;;) {
        esp_task_wdt_reset();

        if (Serial.available()) {
            handleSerialCommand(Serial.readStringUntil('\n'));
        }

        if (!wifi_toggle) {
            networkInitialized = false;
            ntp_init_retries = 0;
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        if (WiFi.status() != WL_CONNECTED) {
            networkInitialized = false;
            unsigned long nowMs = millis();
            int devNum = deviceName.substring(6).toInt();
            unsigned long wifiRetryInterval = 10000UL + (static_cast<unsigned long>(devNum) * 500UL);
            if (nowMs - lastWifiAttempt > wifiRetryInterval) {
                Serial.print("Reconnecting WiFi...");
                WiFi.disconnect(true);
                vTaskDelay(pdMS_TO_TICKS(100));
                WiFi.mode(WIFI_STA);
                WiFi.begin(WIFI_SSID, WIFI_PASS);
                lastWifiAttempt = nowMs;
            }
            vTaskDelay(pdMS_TO_TICKS(200));
            continue;
        }

        if (!networkInitialized) {
            setupMqtt(client, deviceName, onMqttMessage);
            configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER, "pool.ntp.org", "time.google.com");

            handleMqtt(client, deviceName);
            if (client.connected()) {
                publishCrashReport(client, deviceName);
            }

            struct tm ti;
            if (!getLocalTime(&ti)) {
                ntp_init_retries++;
                Serial.printf("Waiting for NTP time... (attempt %d/%d)\n",
                              ntp_init_retries, NTP_MAX_RETRIES);
                if (ntp_init_retries >= NTP_MAX_RETRIES) {
                    Serial.println("CRITICAL: NTP sync failed — rebooting to recover.");
                    saveCrashReason("NTP sync failed at init");
                    delay(1000);
                    ESP.restart();
                }
                vTaskDelay(pdMS_TO_TICKS(2000));
                continue;
            }
            ntp_init_retries = 0;
            networkInitialized = true;
            lastNtpResync = mktime(&ti);
            nextSensorTrigger = LONG_MAX;
            nextCameraTrigger = LONG_MAX;
            Serial.printf("Network initialized — time: %02d:%02d:%02d\n",
                          ti.tm_hour, ti.tm_min, ti.tm_sec);
        }

        handleMqtt(client, deviceName);

        {
            struct tm now_tm;
            if (getLocalTime(&now_tm)) {
                time_t now_t = mktime(&now_tm);
                if (lastNtpResync > 0 && (now_t - lastNtpResync) >= static_cast<time_t>(NTP_RESYNC_INTERVAL)) {
                    configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);
                    lastNtpResync = now_t;
                    Serial.println("NTP: periodic resync triggered (24h).");
                }
            }
        }

        UploadItem item;
        if (xQueueReceive(uploadQueue, &item, pdMS_TO_TICKS(100)) == pdTRUE) {
            static unsigned long lastStaggerTime = 0;
            int devNum = deviceName.substring(6).toInt();
            unsigned long staggerMs = static_cast<unsigned long>(max(0, devNum - 1))
                                      * static_cast<unsigned long>(upload_stagger_ms);
            unsigned long nowMs = millis();
            if (staggerMs > 0 && (lastStaggerTime == 0 || (nowMs - lastStaggerTime) > 300000UL)) {
                lastStaggerTime = nowMs;
                Serial.printf("Upload stagger: %s → %lu ms delay before FTP\n",
                              deviceName.c_str(), staggerMs);
                while (staggerMs > 0) {
                    if (WiFi.status() != WL_CONNECTED) {
                        Serial.println("Stagger aborted: WiFi lost.");
                        break;
                    }
                    unsigned long chunk = min(staggerMs, 30000UL);
                    vTaskDelay(pdMS_TO_TICKS(chunk));
                    esp_task_wdt_reset();
                    if (client.connected()) client.loop();
                    staggerMs -= chunk;
                }
            }

            switch (item.type) {
                case UploadType::CSV: {
                    publishHealthStatus(client, deviceName);
                    publishMetric(client, deviceName, "temperature",  item.csv.temperature, 1, true);
                    publishMetric(client, deviceName, "humidity",     item.csv.humidity, 0, true);
                    publishMetric(client, deviceName, "illuminance",  item.csv.cal_lux, 0, true);

                    char tmpName[72];
                    snprintf(tmpName, sizeof(tmpName), "%s.tmp", item.csv.filename);

                    bool uploaded = false;
                    for (int attempt = 1; attempt <= 6 && !uploaded; attempt++) {
                        esp_task_wdt_reset();

                        if (isUploadDeadlineImminent()) {
                            Serial.println("CSV upload aborted: next measurement imminent.");
                            break;
                        }
                        if (WiFi.status() != WL_CONNECTED) {
                            Serial.printf("FTP CSV: WiFi down, attempt %d/6 — waiting 5s...\n", attempt);
                            for (int i = 0; i < 10; i++) {
                                vTaskDelay(pdMS_TO_TICKS(500));
                                esp_task_wdt_reset();
                            }
                            continue;
                        }

                        ftp.OpenConnection();
                        ftp.ChangeWorkDir(FTP_LANDING);
                        ftp.InitFile("Type A");
                        ftp.NewFile(tmpName);
                        ftp.Write(item.csv.csv);
                        ftp.CloseFile();

                        char fromBuf[72], toBuf[72];
                        strncpy(fromBuf, tmpName, sizeof(fromBuf));
                        fromBuf[sizeof(fromBuf)-1] = '\0';
                        strncpy(toBuf, item.csv.filename, sizeof(toBuf));
                        toBuf[sizeof(toBuf)-1] = '\0';
                        ftp.RenameFile(fromBuf, toBuf);
                        if (ftp.isConnected()) {
                            ftp.CloseConnection();
                            uploaded = true;
                        } else {
                            ftp.CloseConnection();
                            Serial.printf("FTP CSV: data error on attempt %d/6 — retrying\n", attempt);
                        }
                    }

                    if (uploaded) {
                        Serial.printf("Uploaded CSV: %s\n", item.csv.filename);
                        char topic[100];
                        snprintf(topic, sizeof(topic), "sensors/%s/new_csv", deviceName.c_str());
                        client.publish(topic, item.csv.filename);
                    } else {
                        Serial.printf("WARNING: CSV upload failed after 6 attempts: %s — discarding.\n",
                                      item.csv.filename);
                    }
                    break;
                }

                case UploadType::HDR: {
                    EncodedHDR hdr;
                    hdr.data = item.hdr.data;
                    hdr.len = item.hdr.len;
                    strncpy(hdr.filename, item.hdr.filename, sizeof(hdr.filename) - 1);
                    hdr.filename[sizeof(hdr.filename) - 1] = '\0';
                    hdr.brackets_used = item.hdr.brackets_used;
                    hdr.brackets_total = item.hdr.brackets_total;
                    hdr.valid = true;

                    uploadEncodedHDR(ftp, FTP_LANDING, hdr);

                    freeHDRBuffers();
                    xSemaphoreGive(hdrBufferSem);
                    break;
                }

                case UploadType::JPEG: {
                    CapturedJPEG jpeg;
                    jpeg.data = item.jpeg.data;
                    jpeg.len = item.jpeg.len;
                    strncpy(jpeg.filename, item.jpeg.filename, sizeof(jpeg.filename) - 1);
                    jpeg.filename[sizeof(jpeg.filename) - 1] = '\0';
                    jpeg._fb = item.jpeg.fb;
                    jpeg.valid = true;

                    uploadContextJPEG(ftp, FTP_LANDING, jpeg);
                    break;
                }
            }
        }
    }
}

void loop() {
    vTaskDelay(pdMS_TO_TICKS(10000));
}
