/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
* 
* Description:
* This sketch performs a parallel characterization sweep for the AS7265x
*/

#include "config.h"
#include <Preferences.h>
#include <WiFi.h>
#include "globals.h"
#include "sensors.h"
#include "functions.h"
#include "datastructures.h"
#include "calibration.h"
#include "Wire.h"
#include "time.h"
#include "secrets.h"
#include <vector>

const int LOGGING_INTERVAL_MINUTES = 10;
const int AS7265X_TEST_GAIN = 16;
const int AS7331_TEST_GAIN = 32;
const int TSL2591_TEST_GAIN = 0;
const int TSL2591_FIXED_TIME = 300;

const std::vector<int> s_time_sweep_values = { 20, 40, 80, 120, 160, 200, 230, 255 };
const std::vector<int> u_time_sweep_values = { 16, 32, 64, 128, 256, 512, 1024, 2048 };

String deviceName = DEVICE_NAME;
long lastSensorTriggerSecond = -1;
volatile bool triggerSensorMeasurement = false;
bool wifi_toggle = true;
float S_wait_time = 10.0;
WiFiClient espClient;
PubSubClient client(espClient);
ESP32_FTPClient ftp(FTP_SERVER, FTP_USER, FTP_PASS, 5000, 0);
Preferences preferences;

int S_gainValue = AS7265X_TEST_GAIN;
int U_gainValue = AS7331_TEST_GAIN;
int I_gainValue = TSL2591_TEST_GAIN;
int S_integrationTime;
int U_integrationTime;
int I_integrationTime = TSL2591_FIXED_TIME;

float C_wait_time = 10.0;
bool cam_toggle = true;
volatile bool triggerCameraCapture = false;
CalibrationProfile active_profile;

void performMeasurementSweep();
void uploadSweepCsv(const std::vector<String>& csv_rows, const char* fileName);
void callback(char* topic, byte* payload, unsigned int length);

void callback(char* topic, byte* payload, unsigned int length) {
    char message[length + 1];
    memcpy(message, payload, length);
    message[length] = '\0';
    if (length == 0) return;

    Serial.printf("Message on topic: %s. Payload: %s\n", topic, message);

    String topicStr = String(topic);
    if (topicStr.startsWith("control/trigger/")) {
        String command = String(message);
        command.toUpperCase();
        if (command == "SENSORS" || command == "S" || command == "BOTH" || command == "ALL" || command == "SWEEP") {
            triggerSensorMeasurement = true;
            Serial.println("INFO: MQTT command received. Triggering measurement sweep.");
        }
    }
    else if (strcmp(topic, "control/wait_time") == 0 || strcmp(topic, "control/S_wait_time") == 0) {
        float new_wait_time = atof(message);
        if (new_wait_time >= 0.167) {
            S_wait_time = new_wait_time;
            Serial.printf("Sweep interval updated to: %.2f minutes\n", S_wait_time);
            preferences.begin("sweep-settings", false);
            preferences.putFloat("s_wait_time", S_wait_time);
            preferences.end();
        }
    }
}

void uploadSweepCsv(const std::vector<String>& csv_rows, const char* fileName) {
    if (csv_rows.empty()) { return; }
    static char csvBuffer[4096];
    int offset = 0;
    offset = snprintf(csvBuffer, sizeof(csvBuffer), "S_gain,S_time,U_gain,U_time,I_gain,I_time,temperature,humidity,tsl_ch0,tsl_ch1,raw_uvc,raw_uvb,raw_uva,raw_ch1,raw_ch2,raw_ch3,raw_ch4,raw_ch5,raw_ch6,raw_ch7,raw_ch8,raw_ch9,raw_ch10,raw_ch11,raw_ch12,raw_ch13,raw_ch14,raw_ch15,raw_ch16,raw_ch17,raw_ch18\n");
    for(const auto& row : csv_rows) {
        if (offset + row.length() < sizeof(csvBuffer) - 1) {
            strcat(csvBuffer, row.c_str());
            offset += row.length();
        }
    }

    ftp.OpenConnection();
    ftp.ChangeWorkDir(ftpLandingZone);
    ftp.InitFile("Type A");
    ftp.NewFile(fileName);
    ftp.Write(csvBuffer);
    ftp.CloseFile();
    ftp.CloseConnection();
    Serial.printf("Uploaded sweep data to: %s\n", fileName);
}

void performMeasurementSweep() {
    if (WiFi.status() != WL_CONNECTED) { Serial.println("ERROR: WiFi disconnected, aborting sweep."); return; }
    struct tm timeinfo;
    if (!getLocalTime(&timeinfo)) { Serial.println("ERROR: Could not get time."); return; }

    publishHealthStatus(client, deviceName);

    char time_str[20];
    strftime(time_str, sizeof(time_str), "%Y%m%d_%H%M%S", &timeinfo);
    char baseFileName[64];
    snprintf(baseFileName, sizeof(baseFileName), "%s_%s", time_str, deviceName.c_str());

    std::vector<String> collected_csv_rows;

    if (s_time_sweep_values.size() != u_time_sweep_values.size()) {
        Serial.println("ERROR: Sweep value lists have different sizes. Aborting.");
        return;
    }

    for (size_t i = 0; i < s_time_sweep_values.size(); ++i) {
        int s_time = s_time_sweep_values[i];
        int u_time = u_time_sweep_values[i];

        Serial.printf("  Testing S_time: %-3d, U_time: %d\n", s_time, u_time);
        updateIntegrationTime('S', s_time);
        updateIntegrationTime('U', u_time);

        unsigned long s_wait_ms = (unsigned long)(S_integrationTime * 2.8 * 2.0);
        unsigned long u_wait_ms = (unsigned long)U_integrationTime;
        delay(max(s_wait_ms, u_wait_ms) + 20);

        FullSensorReading reading;
        float temp_ignore;
        if (!sht.Measure(&reading.temperature, &reading.humidity, SHT4X_REG_MEASURE_HIGH)) continue;
        reading.temperature /= 1000.0;
        reading.humidity /= 1000.0;
        tsl.Get_ALS();
        reading.tsl_ch0 = tsl.all_data;
        reading.tsl_ch1 = tsl.ir_data;

        if (as7265x.Get_DataStatus() && (as7331.Get_Status() & 0x0008)) {
            as7331.Get_All(&temp_ignore, &reading.raw_uva, &reading.raw_uvb, &reading.raw_uvc);
            as7265x.Get_Channel_Raw(reading.raw_spectral);

            char rowBuffer[512];
            snprintf(rowBuffer, sizeof(rowBuffer), "%d,%d,%d,%d,%d,%d,%.2f,%.2f,%u,%u,%u,%u,%u,",
                S_gainValue, S_integrationTime, U_gainValue, U_integrationTime, I_gainValue, I_integrationTime,
                reading.temperature, reading.humidity, reading.tsl_ch0, reading.tsl_ch1,
                reading.raw_uvc, reading.raw_uvb, reading.raw_uva);
            String rowString = String(rowBuffer);
            for (int j = 0; j < 18; ++j) {
                rowString += String(reading.raw_spectral[j]);
                rowString += (j < 17) ? "," : "\n";
            }
            collected_csv_rows.push_back(rowString);
        }
    }

    char dataFileName[80];
    snprintf(dataFileName, sizeof(dataFileName), "sweep_%s.csv", baseFileName);
    uploadSweepCsv(collected_csv_rows, dataFileName);

    char imgName[80];
    snprintf(imgName, sizeof(imgName), "image_%s.jpeg", baseFileName);
    photo_send(imgName, ftpLandingZone, ftp);

    Serial.println("--- Measurement Sweep Complete ---");
}

void setup() {
    Serial.begin(115200);
    Serial.printf("\n\n--- Starting Parallel Sweep Logger for %s ---\n", deviceName.c_str());

    if (!psramInit()) { Serial.println("FATAL ERROR: PSRAM initialization failed!"); while(true); }

    preferences.begin("sweep-settings", false);
    S_wait_time = preferences.getFloat("s_wait_time", 10.0);
    preferences.end();

    Serial.println("Connecting to WiFi...");
    unsigned long connection_start_time = millis();
    while (wifi_toggle && WiFi.status() != WL_CONNECTED) {
        if (Serial.available()) { processSerialCommand(Serial.readStringUntil('\n')); }
        if (millis() - connection_start_time > 10000) {
            Serial.print("\nAttempting connection...");
            WiFi.begin(WIFI_SSID, WIFI_PASS);
            connection_start_time = millis();
        }
        Serial.print("."); delay(500);
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi connected!");
        Serial.print("IP address: "); Serial.println(WiFi.localIP());
        setupMqtt(client, deviceName, callback);
        configTime(3600, 3600, "pool.ntp.org");
    }

    setupTSL2591(); setupAS7331(); setupAS7265X(); setupSHT4X(); setupOV5640_jpeg();
    ledLight(false);

    updateGain('S', S_gainValue); updateGain('U', U_gainValue); updateGain('I', I_gainValue);
    updateIntegrationTime('I', I_integrationTime);

    Serial.println("\nSetup complete. Ready for sweep.");
}

void loop() {
    if (wifi_toggle) { handleMqtt(client, deviceName); }
    if (Serial.available()) { processSerialCommand(Serial.readStringUntil('\n')); }

    struct tm timeinfo;
    if (!getLocalTime(&timeinfo)) { delay(100); return; }

    long seconds_of_the_day = (timeinfo.tm_hour * 3600L) + (timeinfo.tm_min * 60L) + timeinfo.tm_sec;
    int sensor_interval_sec = (int)(S_wait_time * 60.0);
    bool isSensorScheduled = (sensor_interval_sec >= 10) && (seconds_of_the_day % sensor_interval_sec == 0) && (seconds_of_the_day != lastSensorTriggerSecond);

    if (isSensorScheduled || triggerSensorMeasurement) {
        if (isSensorScheduled) lastSensorTriggerSecond = seconds_of_the_day;
        triggerSensorMeasurement = false;
        performMeasurementSweep();
    }
}
