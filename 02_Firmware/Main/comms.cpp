/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* All device communication: MQTT connection management, topic subscription,
* message handling, metric publishing, FTP CSV upload, and serial CLI.
*/

#include "comms.h"
#include "measurement.h"
#include "secrets.h"
#include "globals.h"
#include "calibration.h"
#include "selftest.h"
#include <WiFi.h>
#include <esp_task_wdt.h>

static constexpr size_t MAX_MQTT_PAYLOAD = 512;

static char mqtt_server[] = MQTT_SERVER;

void saveCrashReason(const char* reason) {
    preferences.begin("crash-info", false);
    preferences.putString("last_crash", reason);
    preferences.end();
    Serial.printf("CRASH REASON saved to NVS: %s\n", reason);
}

void publishCrashReport(PubSubClient& client, const String& deviceName) {
    preferences.begin("crash-info", true);
    String reason = preferences.getString("last_crash", "");
    preferences.end();
    if (reason.length() > 0) {
        char topic[100];
        snprintf(topic, sizeof(topic), "sensors/%s/crash_report", deviceName.c_str());
        client.publish(topic, reason.c_str(), false);
        Serial.printf("CRASH REPORT published: %s\n", reason.c_str());
        preferences.begin("crash-info", false);
        preferences.remove("last_crash");
        preferences.end();
    }
}

int parseBool(const char* str) {
    if (strcasecmp(str, "ON") == 0 || strcasecmp(str, "TRUE") == 0 || strcasecmp(str, "1") == 0 || strcasecmp(str, "ENABLE") == 0) return 1;
    if (strcasecmp(str, "OFF") == 0 || strcasecmp(str, "FALSE") == 0 || strcasecmp(str, "0") == 0 || strcasecmp(str, "DISABLE") == 0) return 0;
    return -1;
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
    if (length == 0) return;

    size_t safe_len = (length < MAX_MQTT_PAYLOAD) ? length : MAX_MQTT_PAYLOAD;
    char message[MAX_MQTT_PAYLOAD + 1];
    memcpy(message, payload, safe_len);
    message[safe_len] = '\0';

    Serial.printf("MQTT [%s]: %s\n", topic, message);

    if (strncmp(topic, "control/trigger/", 16) == 0) {
        String cmd = String(message);
        cmd.toUpperCase();
        if (cmd == "BOTH" || cmd == "ALL") {
            triggerSensorMeasurement = true;
            triggerCameraCapture = true;
        } else if (cmd == "SENSORS" || cmd == "S") {
            triggerSensorMeasurement = true;
        } else if (cmd == "CAMERA" || cmd == "C") {
            triggerCameraCapture = true;
        } else {
            Serial.println("Invalid trigger. Use S, C, or BOTH/ALL.");
        }
        if (captureTaskHandle) {
            xTaskNotifyGive(captureTaskHandle);
        }
        return;
    }

    auto handleWaitTime = [](const char* msg, float& target, const char* label) {
        float val = atof(msg);
        if (val >= MIN_WAIT_MINUTES) {
            target = val;
            time_t now = time(nullptr);
            int interval = max(1, static_cast<int>(val * 60.0f));
            time_t next = now + (interval - (now % interval));
            if (&target == &S_wait_time) nextSensorTrigger = next;
            if (&target == &C_wait_time) nextCameraTrigger = next;
            Serial.printf("%s interval set to %.2f min (next in %ldm %02lds)\n",
                          label, val,
                          static_cast<long>(next - now) / 60,
                          static_cast<long>(next - now) % 60);
            preferences.begin("sensor-settings", false);
            preferences.putFloat("s_wait_time", S_wait_time);
            preferences.putFloat("c_wait_time", C_wait_time);
            preferences.end();
        } else {
            Serial.printf("Invalid wait time. Must be >= %.3f min.\n", MIN_WAIT_MINUTES);
        }
    };

    if (strcmp(topic, "control/wait_time") == 0) {
        float val = atof(message);
        if (val >= MIN_WAIT_MINUTES) {
            S_wait_time = val;
            C_wait_time = val;
            time_t now = time(nullptr);
            int interval = max(1, static_cast<int>(val * 60.0f));
            time_t next = now + (interval - (now % interval));
            nextSensorTrigger = next;
            nextCameraTrigger = next;
            Serial.printf("ALL intervals set to %.2f min (next in %ldm %02lds)\n",
                          val,
                          static_cast<long>(next - now) / 60,
                          static_cast<long>(next - now) % 60);
            preferences.begin("sensor-settings", false);
            preferences.putFloat("s_wait_time", S_wait_time);
            preferences.putFloat("c_wait_time", C_wait_time);
            preferences.end();
        } else {
            Serial.printf("Invalid wait time. Must be >= %.3f min.\n", MIN_WAIT_MINUTES);
        }
        return;
    }
    if (strcmp(topic, "control/S_wait_time") == 0) {
        handleWaitTime(message, S_wait_time, "Sensor");
        return;
    }
    if (strcmp(topic, "control/C_wait_time") == 0) {
        handleWaitTime(message, C_wait_time, "Camera");
        return;
    }

    if (strcmp(topic, "control/upload_stagger") == 0) {
        int val = atoi(message);
        if (val >= 0) {
            upload_stagger_ms = val;
            preferences.begin("sensor-settings", false);
            preferences.putInt("upload_stagger", upload_stagger_ms);
            preferences.end();
            Serial.printf("Upload stagger set to %d ms/device\n", upload_stagger_ms);
        } else {
            Serial.println("Invalid upload stagger. Must be >= 0 ms.");
        }
        return;
    }

    if (strcmp(topic, "control/exposure_values") == 0) {
        std::vector<int> new_values;
        String payloadStr(message);
        int lastIndex = 0, commaIndex = 0;

        while ((commaIndex = payloadStr.indexOf(',', lastIndex)) != -1) {
            int v = payloadStr.substring(lastIndex, commaIndex).toInt();
            if (v >= 1) new_values.push_back(v);
            lastIndex = commaIndex + 1;
        }
        String last = payloadStr.substring(lastIndex);
        last.trim();
        if (last.length() > 0) {
            int v = last.toInt();
            if (v >= 1) new_values.push_back(v);
        }

        if (!new_values.empty()) {
            exposure_values.swap(new_values);
            Serial.print("Exposures updated: ");
            for (int v : exposure_values) Serial.printf("%d ", v);
            Serial.println();
        }
        return;
    }

    if (strcmp(topic, "control/hdr_toggle") == 0) {
        int val = parseBool(message);
        if (val >= 0) {
            hdr_toggle = val;
            Serial.printf("HDR mode %s.\n", hdr_toggle ? "enabled" : "disabled");
        }
        return;
    }

    if (strcmp(topic, "control/jpeg_toggle") == 0) {
        int val = parseBool(message);
        if (val >= 0) {
            jpeg_toggle = val;
            Serial.printf("JPEG context image %s.\n", jpeg_toggle ? "enabled" : "disabled");
        }
        return;
    }

    if (strcmp(topic, "control/hdr_avg_frames") == 0) {
        int n = atoi(message);
        if (n >= 1 && n <= 8) {
            hdr_avg_frames = n;
            Serial.printf("HDR avg frames: %d\n", n);
        } else {
            Serial.println("Invalid hdr_avg_frames (1-8).");
        }
        return;
    }

    if (strcmp(topic, "control/hdr_sat_fill") == 0) {
        int val = parseBool(message);
        if (val >= 0) {
            hdr_sat_fill = val;
            Serial.printf("HDR sat-fill %s.\n", hdr_sat_fill ? "enabled" : "disabled");
        }
        return;
    }

    if (strcmp(topic, "control/hdr_early_term") == 0) {
        int val = parseBool(message);
        if (val >= 0) {
            hdr_early_term = val;
            Serial.printf("HDR early-term %s.\n", hdr_early_term ? "enabled" : "disabled");
        }
        return;
    }

    if (strcmp(topic, "control/hdr_et_pct") == 0) {
        float pct = atof(message);
        if (pct > 0.0f && pct <= 100.0f) {
            hdr_et_pct = pct;
            Serial.printf("HDR early-term fill threshold: %.1f%%\n", pct);
        } else {
            Serial.println("Invalid hdr_et_pct (must be > 0 and <= 100).");
        }
        return;
    }

    if (strcmp(topic, "control/hdr_et_min_exp") == 0) {
        int n = atoi(message);
        if (n >= 0) {
            hdr_et_min_exp = n;
            Serial.printf("HDR early-term min exposure: %d AEC units\n", n);
        } else {
            Serial.println("Invalid hdr_et_min_exp (must be >= 0).");
        }
        return;
    }

    if (strcmp(topic, "control/cam_cal") == 0) {
        int val = parseBool(message);
        if (val >= 0) {
            cam_cal_enable = val;
            Serial.printf("Camera absolute calibration: %s\n", cam_cal_enable ? "ON" : "OFF");
        }
        return;
    }
    if (strcmp(topic, "control/cam_vign") == 0) {
        int val = parseBool(message);
        if (val >= 0) {
            cam_vign_enable = val;
            Serial.printf("Camera vignetting correction: %s\n", cam_vign_enable ? "ON" : "OFF");
        }
        return;
    }
    if (strcmp(topic, "control/cam_crop") == 0) {
        int val = parseBool(message);
        if (val >= 0) {
            cam_crop_enable = val;
            Serial.printf("Camera fisheye crop: %s\n", cam_crop_enable ? "ON" : "OFF");
        }
        return;
    }

    if (strncmp(topic, "control/cam_cal_scale/", 22) == 0) {
        if (strcasecmp(message, "RESET") == 0) {
            cam_cal_scale_overridden = false;
            Serial.printf("Camera cal scale reset to compiled value (%.4f)\n",
                          cam_cal_colour ? cam_cal_colour->cal_scale : 1.0f);
        } else {
            float val = atof(message);
            if (val > 0.0f) {
                cam_cal_scale_override    = val;
                cam_cal_scale_overridden  = true;
                Serial.printf("Camera cal scale override: %.4f cd/m2 per HDR unit\n", val);
            } else {
                Serial.println("Invalid cal scale. Send a positive float or RESET.");
            }
        }
        return;
    }
}

static void reconnectMqtt(PubSubClient& client, const String& deviceName) {
    Serial.print("Attempting MQTT connection...");

    char status_topic[50];
    snprintf(status_topic, sizeof(status_topic), "sensors/%s/status", deviceName.c_str());

    if (client.connect(deviceName.c_str(), MQTT_USER, MQTT_PASS,
                       status_topic, 1, true, "offline")) {
        Serial.println("connected");
        client.publish(status_topic, "online", true);
        client.subscribe("control/S_wait_time");
        client.subscribe("control/C_wait_time");
        client.subscribe("control/wait_time");
        client.subscribe("control/upload_stagger");
        client.subscribe("control/exposure_values");
        client.subscribe("control/hdr_toggle");
        client.subscribe("control/jpeg_toggle");
        client.subscribe("control/hdr_avg_frames");
        client.subscribe("control/hdr_sat_fill");
        client.subscribe("control/hdr_early_term");
        client.subscribe("control/hdr_et_pct");
        client.subscribe("control/hdr_et_min_exp");
        client.subscribe("control/cam_cal");
        client.subscribe("control/cam_vign");
        client.subscribe("control/cam_crop");
        client.subscribe(("control/trigger/" + deviceName).c_str());
        client.subscribe("control/trigger/all");
        client.subscribe(("control/cam_cal_scale/" + deviceName).c_str());

        char cal_topic[64];
        snprintf(cal_topic, sizeof(cal_topic), "sensors/%s/cam_calibration", deviceName.c_str());
        char cal_payload[64];
        snprintf(cal_payload, sizeof(cal_payload),
                 "{\"cal\":%s,\"vign\":%s,\"crop\":%s}",
                 cam_cal_enable  ? "true" : "false",
                 cam_vign_enable ? "true" : "false",
                 cam_crop_enable ? "true" : "false");
        client.publish(cal_topic, cal_payload, true);
    } else {
        Serial.printf("failed, rc=%d\n", client.state());
    }
}

void setupMqtt(PubSubClient& client, const String& deviceName, MqttCallback cb) {
    client.setServer(mqtt_server, 1883);
    client.setCallback(cb);
    client.setKeepAlive(MQTT_KEEPALIVE_SEC);
}

void maintainMqtt() {
    if (client.connected()) {
        client.loop();
    }
}

bool isUploadDeadlineImminent() {
    time_t now = time(nullptr);
    time_t earliest = (nextSensorTrigger < nextCameraTrigger)
                    ? nextSensorTrigger : nextCameraTrigger;
    return now >= (earliest - 15);
}

void handleMqtt(PubSubClient& client, const String& deviceName) {
    static unsigned long lastReconnectAttempt = 0;
    static unsigned long reconnectInterval = 5000;
    static int consecutiveFailures = 0;
    static int totalMqttFailures = 0;

    if (!client.connected() && wifi_toggle) {
        unsigned long now = millis();
        if (now - lastReconnectAttempt > reconnectInterval) {
            lastReconnectAttempt = now;

            if (totalMqttFailures >= MQTT_MAX_RECONNECT_ATTEMPTS * 3) {
                Serial.printf("CRITICAL: %d total MQTT failures — rebooting to recover.\n",
                              totalMqttFailures);
                saveCrashReason("MQTT: max reconnect failures exhausted");
                delay(1000);
                ESP.restart();
            }

            if (consecutiveFailures >= MQTT_MAX_RECONNECT_ATTEMPTS) {
                Serial.printf("MQTT: %d consecutive failures — resetting WiFi\n",
                              consecutiveFailures);
                WiFi.disconnect(true);
                delay(100);
                WiFi.mode(WIFI_STA);
                WiFi.begin(WIFI_SSID, WIFI_PASS);
                consecutiveFailures = 0;
                totalMqttFailures = 0;
                reconnectInterval = 5000;
                return;
            }

            reconnectMqtt(client, deviceName);

            if (client.connected()) {
                consecutiveFailures = 0;
                totalMqttFailures = 0;
                reconnectInterval = 5000;
            } else {
                consecutiveFailures++;
                totalMqttFailures++;
                reconnectInterval = min(reconnectInterval * 2, 60000UL);
                Serial.printf("MQTT: failure %d/%d (total: %d/%d), next retry in %lus\n",
                              consecutiveFailures, MQTT_MAX_RECONNECT_ATTEMPTS,
                              totalMqttFailures, MQTT_MAX_RECONNECT_ATTEMPTS * 3,
                              reconnectInterval / 1000);
            }
        }
    } else if (client.connected()) {
        client.loop();
    }
}

void publishHealthStatus(PubSubClient& client, const String& deviceName) {
    char buf[20];
    snprintf(buf, sizeof(buf), "%ld", WiFi.RSSI());
    char topic[100];
    snprintf(topic, sizeof(topic), "sensors/%s/rssi", deviceName.c_str());
    client.publish(topic, buf, true);

    float uptime_hours = static_cast<float>(millis()) / 3600000.0f;
    publishMetric(client, deviceName, "uptime_hours", uptime_hours, 2, true);
}

void publishMetric(PubSubClient& client, const String& deviceName,
                   const char* metric, float value, int decimals, bool retain) {
    char topic[100], payload[20], fmt[8];
    snprintf(topic, sizeof(topic), "sensors/%s/%s", deviceName.c_str(), metric);
    snprintf(fmt, sizeof(fmt), "%%.%df", decimals);
    snprintf(payload, sizeof(payload), fmt, value);
    client.publish(topic, payload, retain);
}

void publishMetric(PubSubClient& client, const String& deviceName,
                   const char* metric, unsigned int value, bool retain) {
    char topic[100], payload[20];
    snprintf(topic, sizeof(topic), "sensors/%s/%s", deviceName.c_str(), metric);
    snprintf(payload, sizeof(payload), "%u", value);
    client.publish(topic, payload, retain);
}

bool uploadCsvReading(ESP32_FTPClient& ftp, const char* uploadDir, const char* fileName,
                      const FullSensorReading& data,
                      int s_gain, int u_gain, int i_gain,
                      int s_time, int u_time, int i_time) {
    if (!data.isValid) {
        Serial.println("Cannot upload CSV: invalid sensor data.");
        return false;
    }

    char csv[2400];
    int off = 0;

    off += snprintf(csv + off, sizeof(csv) - off,
        "%d,%d,%d,%d,%d,%d,%.2f,%.2f,%u,%u,%.2f,%.2f,",
        s_gain, s_time, u_gain, u_time, i_gain, i_time,
        data.temperature, data.humidity,
        data.tsl_ch0, data.tsl_ch1, data.raw_lux, data.cal_lux);

    const uint16_t raw_uv[] = {data.raw_uva, data.raw_uvb, data.raw_uvc};
    for (const auto& ch : masterChannelList) {
        uint16_t val = (strncmp(ch.name, "UV", 2) == 0)
                       ? raw_uv[ch.native_index]
                       : data.raw_spectral[ch.native_index];
        off += snprintf(csv + off, sizeof(csv) - off, "%u,", val);
    }

    const float cal_uv[] = {data.cal_uva, data.cal_uvb, data.cal_uvc};
    for (size_t i = 0; i < masterChannelList.size(); ++i) {
        const auto& ch = masterChannelList[i];
        float val = (strncmp(ch.name, "UV", 2) == 0)
                    ? cal_uv[ch.native_index]
                    : data.cal_spectral[i - 3];
        off += snprintf(csv + off, sizeof(csv) - off, "%.4f%s",
            val, (i < masterChannelList.size() - 1) ? "," : "\n");
    }

    char tmpName[72];
    snprintf(tmpName, sizeof(tmpName), "%s.tmp", fileName);

    for (int attempt = 1; attempt <= 6; attempt++) {
        esp_task_wdt_reset();

        if (isUploadDeadlineImminent()) {
            Serial.println("CSV upload aborted: next measurement cycle is imminent.");
            return false;
        }

        if (WiFi.status() != WL_CONNECTED) {
            Serial.printf("FTP CSV: WiFi down, attempt %d/6 — waiting 5s...\n", attempt);
            for (int i = 0; i < 10; i++) { delay(500); esp_task_wdt_reset(); }
            continue;
        }

        ftp.OpenConnection();
        ftp.ChangeWorkDir(uploadDir);
        ftp.InitFile("Type A");
        ftp.NewFile(tmpName);
        ftp.Write(csv);
        ftp.CloseFile();

        char fromBuf[72], toBuf[72];
        strncpy(fromBuf, tmpName, sizeof(fromBuf));  fromBuf[sizeof(fromBuf)-1] = '\0';
        strncpy(toBuf, fileName, sizeof(toBuf));      toBuf[sizeof(toBuf)-1] = '\0';
        ftp.RenameFile(fromBuf, toBuf);

        if (!ftp.isConnected()) {
            ftp.CloseConnection();
            Serial.printf("FTP CSV: data error on attempt %d/6 — retrying\n", attempt);
            continue;
        }
        ftp.CloseConnection();
        Serial.printf("Uploaded CSV: %s\r\n", fileName);
        return true;
    }
    Serial.printf("CRITICAL: CSV upload failed after 6 attempts: %s — rebooting.\n", fileName);
    saveCrashReason("CSV upload failed after 6 attempts");
    delay(1000);
    ESP.restart();
    return false;
}

static void printHelp(const char* topic) {
    String t = String(topic);
    t.toUpperCase();
    t.trim();

    if (t.length() == 0) {
        Serial.println("----------------------------------------------------");
        Serial.println("  HELP  --  type HELP <topic> for details");
        Serial.println("----------------------------------------------------");
        Serial.println("  DEVICE   Identity, status, triggers");
        Serial.println("  SENSOR   Spectral sensors, gain, time, cal");
        Serial.println("  CAMERA   Camera, HDR bracketing, JPEG");
        Serial.println("  NETWORK  WiFi, upload stagger");
        Serial.println("  TEST     Pre-deployment self-test runner");
        Serial.println("----------------------------------------------------");
        Serial.println("  Examples:  HELP SENSOR  |  HDR ?  |  CAM -HELP");
        Serial.println("----------------------------------------------------");
        return;
    }

    if (t == "DEVICE") {
        Serial.println("----------------------------------------------------");
        Serial.println("  HELP: DEVICE");
        Serial.println("----------------------------------------------------");
        Serial.println("  WHO / NAME / ME    Device name, MAC, IP");
        Serial.println("  HEALTH             WiFi, MQTT, uptime");
        Serial.println("  SENSOR             Trigger measurement now");
        Serial.println("  CAM / CAMERA       Trigger camera capture now");
        Serial.println("  BOTH / RUN         Trigger sensor + camera");
        Serial.println("  HEAD / HEADER      Print CSV column header");
        Serial.println("----------------------------------------------------");
        return;
    }

    if (t == "SENSOR" || t == "SENS" || t == "SEN" || t == "S" || t == "U" || t == "I") {
        Serial.println("----------------------------------------------------");
        Serial.println("  HELP: SENSOR");
        Serial.println("----------------------------------------------------");
        Serial.println("  SENSOR             Trigger one measurement now");
        Serial.println("  S WAIT <min>       Measurement interval (minutes)");
        Serial.println("  -- AS7265x spectral (S) --");
        Serial.println("  S GAIN <v>         Gain  (1 | 4 | 16 | 64)");
        Serial.println("  S TIME <v>         Integration register  (1-255)");
        Serial.println("  -- AS7331 UV (U) --");
        Serial.println("  U GAIN <v>         Gain  (1..2048, powers of 2)");
        Serial.println("  U TIME <v>         Integration time ms  (1-16384)");
        Serial.println("  -- TSL2591 illuminance (I) --");
        Serial.println("  I GAIN <v>         Gain index  (0=LOW .. 3=MAX)");
        Serial.println("  I TIME <v>         Integration time ms  (100-600)");
        Serial.println("  -- Calibration --");
        Serial.println("  CAL                One calibration reading");
        Serial.println("  CAL DARK           Dark count capture (cover sensors)");
        Serial.println("----------------------------------------------------");
        return;
    }

    if (t == "CAMERA" || t == "CAM" || t == "HDR" || t == "JPEG") {
        Serial.println("----------------------------------------------------");
        Serial.println("  HELP: CAMERA");
        Serial.println("----------------------------------------------------");
        Serial.println("  CAM ON/OFF         Enable / disable camera");
        Serial.println("  CAM                Trigger capture now");
        Serial.println("  C WAIT <min>       Camera capture interval (minutes)");
        Serial.println("  -- Calibration --");
        Serial.println("  CAM CAL ON/OFF     Absolute luminance scale");
        Serial.println("  CAM VIGN ON/OFF    Vignetting correction");
        Serial.println("  CAM CROP ON/OFF    Fisheye ROI crop");
        Serial.println("  CAM SCALE <float>  Override cal_scale (cd/m2 per unit)");
        Serial.println("  CAM SCALE RESET    Restore compiled cal_scale");
        Serial.println("  -- HDR --");
        Serial.println("  HDR ON/OFF         Enable / disable HDR merge");
        Serial.println("  HDR AVG <1-8>      Frames averaged per short bracket");
        Serial.println("  HDR SATFILL ON/OFF Fill saturated pixels");
        Serial.println("  HDR EARLYTERM ON/OFF          Stop when scene is filled");
        Serial.println("  HDR EARLYTERM PCT <0-100>     Fill threshold (%)");
        Serial.println("  HDR EARLYTERM MIN <aec>       Min AEC before ET check");
        Serial.println("  HDR EARLYTERM RADIUS <10-100> Center ROI radius (%)");
        Serial.println("  -- JPEG --");
        Serial.println("  JPEG ON/OFF        Enable / disable context JPEG");
        Serial.println("----------------------------------------------------");
        return;
    }

    if (t == "NETWORK" || t == "NET" || t == "WIFI" || t == "STAGGER") {
        Serial.println("----------------------------------------------------");
        Serial.println("  HELP: NETWORK");
        Serial.println("----------------------------------------------------");
        Serial.println("  WIFI ON/OFF        Enable / disable WiFi");
        Serial.println("  STAGGER <ms>       Per-device FTP upload delay (ms)");
        Serial.println("----------------------------------------------------");
        return;
    }

    if (t == "TEST") {
        Serial.println("----------------------------------------------------");
        Serial.println("  HELP: TEST  (pre-deployment self-test runner)");
        Serial.println("----------------------------------------------------");
        Serial.println("  TEST               Run all groups");
        Serial.println("  TEST ALL           Same as TEST");
        Serial.println("  TEST CONFIG        Config & calibration checks");
        Serial.println("  TEST MEMORY        Heap & PSRAM allocation");
        Serial.println("  TEST SENSOR        I2C sensors + plausibility");
        Serial.println("  TEST CAMERA        Camera init + 2-bracket smoke");
        Serial.println("  TEST NETWORK       WiFi, MQTT, NTP, FTP TCP");
        Serial.println("  Output:  [SELFTEST:GROUP]  name  PASS|WARN|FAIL");
        Serial.println("----------------------------------------------------");
        return;
    }

    Serial.printf("Unknown help topic '%s'. ", topic);
    Serial.println("Topics: DEVICE | SENSOR | CAMERA | NETWORK | TEST");
}

void handleSerialCommand(String command) {
    command.trim();
    command.toUpperCase();

    if (command == "HELP" || command == "?" || command == "H") {
        printHelp(""); return;
    }
    if (command.startsWith("HELP ")) {
        printHelp(command.substring(5).c_str()); return;
    }
    if (command.endsWith(" HELP") || command.endsWith(" -HELP") || command.endsWith(" ?")) {
        int ls = command.lastIndexOf(' ');
        String pfx = (ls > 0) ? command.substring(0, ls) : command;
        pfx.trim();
        if      (pfx == "CAM" || pfx == "CAMERA" || pfx == "HDR" || pfx == "JPEG")
            printHelp("CAMERA");
        else if (pfx == "SENSOR" || pfx == "SENS" || pfx == "SEN" || pfx == "S" || pfx == "U" || pfx == "I")
            printHelp("SENSOR");
        else if (pfx == "WIFI" || pfx == "NET" || pfx == "NETWORK" || pfx == "STAGGER")
            printHelp("NETWORK");
        else if (pfx == "TEST")
            printHelp("TEST");
        else if (pfx == "WHO" || pfx == "HEALTH" || pfx == "DEVICE")
            printHelp("DEVICE");
        else
            printHelp("");
        return;
    }

    if (command == "HEALTH") {
        publishHealthStatus(client, deviceName);
        bool wifiOk = WiFi.status() == WL_CONNECTED;
        Serial.println("--- HEALTH ---");
        Serial.printf("WiFi    : %s\n", wifiOk ? "connected" : "disconnected");
        if (wifiOk) {
            Serial.printf("IP      : %s\n", WiFi.localIP().toString().c_str());
            Serial.printf("RSSI    : %ld dBm\n", WiFi.RSSI());
        }
        Serial.printf("MQTT    : %s\n", client.connected() ? "connected" : "disconnected");
        Serial.printf("Uptime  : %.2f h\n", static_cast<float>(millis()) / 3600000.0f);
        Serial.println("--------------");
        return;
    }

    if (command == "WHO" || command == "NAME" || command == "ME") {
        Serial.printf("Device : %s\n", deviceName.c_str());
        Serial.printf("MAC    : %s\n", WiFi.macAddress().c_str());
        Serial.printf("IP     : %s\n",
                       WiFi.status() == WL_CONNECTED
                           ? WiFi.localIP().toString().c_str()
                           : "not connected");
        return;
    }

    if (command == "BOTH" || command == "RUN" || command == "TRIGGER") {
        triggerSensorMeasurement = true;
        triggerCameraCapture = true;
        if (captureTaskHandle) xTaskNotifyGive(captureTaskHandle);
        Serial.println("Queued SENSOR and CAMERA action.");
        return;
    }

    if (command == "SENS" || command == "SENSOR" || command == "SEN") {
        triggerSensorMeasurement = true;
        if (captureTaskHandle) xTaskNotifyGive(captureTaskHandle);
        Serial.println("Queued SENSOR action.");
        return;
    }

    if (command == "CAL DARK") {
        Serial.println("--- CAL DARK: cover all sensors completely before proceeding ---");
        int og, ot, ug, ut, ig, it;
        FullSensorReading r = performCalibrationCapture(true, og, ot, ug, ut, ig, it);
        if (!r.isValid) {
            Serial.println("ERROR: Dark measurement failed.");
            return;
        }

        // Normalise by gain x time so the dark counts apply at any measurement setting
        constexpr float DARK_S_DENOM =
            64.0f * (255.0f * AS7265X_BASE_PERIOD_MS * AS7265X_MODE2_MULTIPLIER / 1000.0f);
        constexpr float DARK_U_DENOM = 2048.0f * (16384.0f / 1000.0f);

        float dark[NUM_CHANNELS];
        const uint16_t raw_uv[] = {r.raw_uva, r.raw_uvb, r.raw_uvc};
        for (int i = 0; i < NUM_CHANNELS; i++) {
            const auto& ch = masterChannelList[static_cast<size_t>(i)];
            const bool is_uv = (strncmp(ch.name, "UV", 2) == 0);
            float raw = is_uv ? static_cast<float>(raw_uv[ch.native_index])
                              : static_cast<float>(r.raw_spectral[ch.native_index]);
            dark[i] = raw / (is_uv ? DARK_U_DENOM : DARK_S_DENOM);
        }

        char buf[640];
        int off = 0;
        off += snprintf(buf + off, sizeof(buf) - off, "{\"%s\", {", deviceName.c_str());
        for (int i = 0; i < NUM_CHANNELS; i++) {
            off += snprintf(buf + off, sizeof(buf) - off,
                "%.8ff%s", dark[i], (i < NUM_CHANNELS - 1) ? ", " : "}}");
        }
        Serial.println("--- CAL DARK RESULT (paste into factorDarkCountData) ---");
        Serial.println(buf);
        Serial.println("---------------------------------------------------------");

        Serial.println("Overwrite NVS dark counts? (y/n):");
        unsigned long prompt_start = millis();
        String response = "";
        while (millis() - prompt_start < 15000UL) {
            if (Serial.available()) {
                response = Serial.readStringUntil('\n');
                response.trim();
                break;
            }
            delay(100);
        }

        if (response.length() == 0) {
            Serial.println("Timeout — dark counts NOT saved to NVS.");
        } else if (response.equalsIgnoreCase("y")) {
            preferences.begin("calibration", false);
            preferences.putBytes("dark_counts", dark, sizeof(dark));
            preferences.end();
            for (int i = 0; i < NUM_CHANNELS; i++) active_profile.S_p_dark[i] = dark[i];
            Serial.println("Dark counts saved to NVS and active profile updated.");
        } else {
            Serial.println("Dark counts NOT saved to NVS.");
        }
        return;
    }

    if (command == "CAL") {
        Serial.println("--- CAL: measuring at default settings ---");
        int og, ot, ug, ut, ig, it;
        FullSensorReading r = performCalibrationCapture(false, og, ot, ug, ut, ig, it);
        if (!r.isValid) {
            Serial.println("ERROR: Calibration measurement failed.");
            return;
        }
        FullSensorReading cal = calibrateReading(r, active_profile, og, ug, ot, ut);
        Serial.println("--- CAL READING ---");
        Serial.print(readingToCsv(cal, og, ot, ug, ut, ig, it, active_profile, nullptr, 0, millis()));
        return;
    }

    if (command == "HEAD" || command == "HEADER") {
        printCsvHeader();
        return;
    }

    if (command == "CAM" || command == "CAMERA") {
        triggerCameraCapture = true;
        if (captureTaskHandle) xTaskNotifyGive(captureTaskHandle);
        Serial.println("Queued CAMERA action.");
        return;
    }

    if (command.startsWith("CAM ")) {
        String val = command.substring(4);
        val.trim();
        if (val.startsWith("CAL ")) {
            int b = parseBool(val.substring(4).c_str());
            if (b >= 0) { cam_cal_enable = b; Serial.printf("Camera abs cal: %s\n", cam_cal_enable ? "ON" : "OFF"); }
            return;
        }
        if (val.startsWith("VIGN ")) {
            int b = parseBool(val.substring(5).c_str());
            if (b >= 0) { cam_vign_enable = b; Serial.printf("Camera vignetting: %s\n", cam_vign_enable ? "ON" : "OFF"); }
            return;
        }
        if (val.startsWith("CROP ")) {
            int b = parseBool(val.substring(5).c_str());
            if (b >= 0) { cam_crop_enable = b; Serial.printf("Camera crop: %s\n", cam_crop_enable ? "ON" : "OFF"); }
            return;
        }
        if (val.startsWith("SCALE ") || val == "SCALE") {
            String sub = val.startsWith("SCALE ") ? val.substring(6) : String("");
            sub.trim();
            if (sub.equalsIgnoreCase("RESET") || sub.isEmpty()) {
                cam_cal_scale_overridden = false;
                Serial.printf("Camera cal scale reset to compiled value (%.4f)\n",
                              cam_cal_colour ? cam_cal_colour->cal_scale : 1.0f);
            } else {
                float sv = sub.toFloat();
                if (sv > 0.0f) {
                    cam_cal_scale_override   = sv;
                    cam_cal_scale_overridden = true;
                    Serial.printf("Camera cal scale override: %.4f cd/m2 per HDR unit\n", sv);
                } else {
                    Serial.println("Usage: CAM SCALE <positive_float>  |  CAM SCALE RESET");
                }
            }
            return;
        }
        int b = parseBool(val.c_str());
        if (b >= 0) cam_toggle = b;
        Serial.printf("Camera toggle: %s\n", cam_toggle ? "ON" : "OFF");
        return;
    }

    if (command.startsWith("HDR ")) {
        String val = command.substring(4);
        val.trim();
        if (val.startsWith("AVG ")) {
            int n = val.substring(4).toInt();
            if (n >= 1 && n <= 8) {
                hdr_avg_frames = n;
                Serial.printf("HDR avg frames: %d\n", n);
            } else {
                Serial.println("Invalid HDR AVG (1-8).");
            }
            return;
        }
        if (val.startsWith("SATFILL ")) {
            int b = parseBool(val.substring(8).c_str());
            if (b >= 0) {
                hdr_sat_fill = b;
                Serial.printf("HDR sat-fill: %s\n", hdr_sat_fill ? "ON" : "OFF");
            }
            return;
        }
        if (val.startsWith("EARLYTERM ")) {
            String sub = val.substring(10);
            sub.trim();
            if (sub.startsWith("PCT ")) {
                float pct = sub.substring(4).toFloat();
                if (pct > 0.0f && pct <= 100.0f) {
                    hdr_et_pct = pct;
                    Serial.printf("HDR early-term fill threshold: %.1f%%\n", pct);
                } else {
                    Serial.println("Invalid HDR EARLYTERM PCT (must be > 0 and <= 100).");
                }
                return;
            }
            if (sub.startsWith("MIN ")) {
                int n = sub.substring(4).toInt();
                if (n >= 0) {
                    hdr_et_min_exp = n;
                    Serial.printf("HDR early-term min exposure: %d AEC units\n", n);
                } else {
                    Serial.println("Invalid HDR EARLYTERM MIN (1-20).");
                }
                return;
            }
            if (sub.startsWith("RADIUS ")) {
                float r = sub.substring(7).toFloat();
                if (r > 10.0f && r <= 100.0f) {
                    hdr_et_radius_pct = r;
                    Serial.printf("HDR early-term center radius: %.1f%%\n", r);
                } else {
                    Serial.println("Invalid HDR EARLYTERM RADIUS (10-100).");
                }
                return;
            }
            int b = parseBool(sub.c_str());
            if (b >= 0) {
                hdr_early_term = b;
                Serial.printf("HDR early-term: %s\n", hdr_early_term ? "ON" : "OFF");
            }
            return;
        }
        int b = parseBool(val.c_str());
        if (b >= 0) hdr_toggle = b;
        Serial.printf("HDR toggle: %s\n", hdr_toggle ? "ON" : "OFF");
        return;
    }

    if (command.startsWith("JPEG ")) {
        String val = command.substring(5);
        val.trim();
        int b = parseBool(val.c_str());
        if (b >= 0) jpeg_toggle = b;
        Serial.printf("JPEG toggle: %s\n", jpeg_toggle ? "ON" : "OFF");
        return;
    }

    if (command.startsWith("WIFI ")) {
        String val = command.substring(5);
        val.trim();
        int b = parseBool(val.c_str());
        if (b >= 0) {
            wifi_toggle = b;
            if (wifi_toggle && WiFi.status() != WL_CONNECTED) {
                WiFi.mode(WIFI_STA);
                WiFi.begin(WIFI_SSID, WIFI_PASS);
            } else if (!wifi_toggle) {
                WiFi.disconnect(true);
                WiFi.mode(WIFI_OFF);
            }
        }
        Serial.printf("Wi-Fi: %s\n", wifi_toggle ? "ON" : "OFF");
        return;
    }

    if (command.length() > 6 && command.charAt(1) == ' ') {
        char sensor = command.charAt(0);
        String action = command.substring(2);

        if (action.startsWith("GAIN ")) {
            setGain(sensor, action.substring(5).toInt());
            return;
        }
        if (action.startsWith("TIME ")) {
            setIntegrationTime(sensor, action.substring(5).toInt());
            return;
        }
        if (action.startsWith("WAIT ")) {
            float val = action.substring(5).toFloat();
            if (sensor == 'S') {
                S_wait_time = val;
                time_t now = time(nullptr);
                int interval = max(1, static_cast<int>(val * 60.0f));
                nextSensorTrigger = now + (interval - (now % interval));
                Serial.printf("Sensor wait: %.2f min\n", val);
            } else if (sensor == 'C') {
                C_wait_time = val;
                time_t now = time(nullptr);
                int interval = max(1, static_cast<int>(val * 60.0f));
                nextCameraTrigger = now + (interval - (now % interval));
                Serial.printf("Camera wait: %.2f min\n", val);
            } else {
                Serial.println("WAIT: use S or C.");
            }
            return;
        }
    }

    if (command.startsWith("STAGGER ")) {
        int val = command.substring(8).toInt();
        if (val >= 0) {
            upload_stagger_ms = val;
            Serial.printf("Upload stagger set to %d ms/device\n", upload_stagger_ms);
        } else {
            Serial.println("Invalid stagger. Must be >= 0 ms.");
        }
        return;
    }

    if (command == "TEST" || command.startsWith("TEST ")) {
        String grp = (command.length() > 4) ? command.substring(5) : "ALL";
        grp.trim();
        if (grp.length() == 0) grp = "ALL";
        runSelfTest(client, deviceName, grp.c_str());
        return;
    }

    Serial.printf("Unknown command: '%s'  --  type HELP for available commands.\n", command.c_str());
}
