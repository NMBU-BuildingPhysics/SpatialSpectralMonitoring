/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* This directory contains the source code for the ESP32-S3 microcontroller
* This file contains main setup and loop functions
*/


#include "config.h"
#include <Preferences.h> 
#include <WiFi.h>        
#include "globals.h"     
#include "sensors.h"
#include "functions.h"
#include "Wire.h"
#include "time.h"
#include <vector>

String deviceName = DEVICE_NAME;
bool cam_toggle = true;
bool hdr_toggle = true;
bool wifi_toggle = true;
CalibrationProfile active_profile;

long lastSensorTriggerSecond = -1;
long lastCameraTriggerSecond = -1;
volatile bool triggerSensorMeasurement = false;
volatile bool triggerCameraCapture = false;
float S_wait_time = 10;
float C_wait_time = 10;
std::vector<int> exposure_values = {1, 2, 8, 16, 32, 64, 128, 256, 512, 1200};

int S_gainValue = 16;
int U_gainValue = 128;
int I_gainValue = 0;
int S_integrationTime = 100; 
int U_integrationTime = 512;
int I_integrationTime = 300;

char ftp_user[]   = FTP_USER;
char ftp_pass[]   = FTP_PASS;
WiFiClient espClient;
PubSubClient client(espClient);
ESP32_FTPClient ftp (FTP_SERVER, ftp_user, ftp_pass, 5000, 0);
Preferences preferences;

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  Serial.println("Sensor name: " + deviceName);
  Serial.printf("Loading calibration profile for '%s'...\n", deviceName.c_str());
  active_profile = getCalibrationProfile(deviceName.c_str());
  if (active_profile.C_p[0] == 1.0f) {
      Serial.println("WARNING: Using default (uncorrected) profile. Check deviceName.");
  } else {
      Serial.println("Calibration profile loaded successfully.");
  }
  preferences.begin("sensor-settings", false); 
  S_wait_time = preferences.getFloat("s_wait_time", S_wait_time); 
  C_wait_time = preferences.getFloat("c_wait_time", C_wait_time);
  preferences.end(); 

  setupTSL2591();
  setupAS7331();
  setupAS7265X();
  setupSHT4X();
  //setupOV5640_565();
  setupOV5640_jpeg(); 
  Serial.println("All Sensors and Camera initialized.");
  if (psramInit()) {
      Serial.println("PSRAM initialized successfully");
  } else {
      Serial.println("PSRAM initialization failed");
  }
  size_t freeMem = heap_caps_get_free_size(MALLOC_CAP_8BIT);
  size_t freePSRAM = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
  Serial.printf("Free RAM: %d bytes, Free PSRAM: %d bytes\n", freeMem, freePSRAM);

  Serial.println("Connecting to WiFi... (You can type 'WIFI OFF' to cancel)");
  unsigned long connection_start_time = millis();

  while (wifi_toggle && WiFi.status() != WL_CONNECTED) {
    if (Serial.available()) {
      processSerialCommand(Serial.readStringUntil('\n'));
    }
    if ((millis() - connection_start_time) % 10000 < 500) {
        Serial.print("\nAttempting connection...");
        WiFi.begin(WIFI_SSID, WIFI_PASS);
    }
    Serial.print(".");
    delay(500);
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    setupMqtt(client, deviceName, callback);
    configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  } 
  else {
    Serial.println("\nProceeding in OFFLINE mode.");
  }

  if (wifi_toggle) {
    setupMqtt(client, deviceName, callback);
    configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
    struct tm timeinfo;
    if (!getLocalTime(&timeinfo)) {
      Serial.println("Failed to obtain time");
    } else {
      Serial.println("Time obtained successfully!");
      Serial.printf("Current time: %d:%d:%d\n", timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
    }
    Wire.begin();
    unsigned status;
  }

  
  
  ledLight(false); // Turn off led light after setup is complete
}

void loop() {

  unsigned long lastOfflineMeasure = 0;
  while (!wifi_toggle) {
      if (Serial.available()) {
          processSerialCommand(Serial.readStringUntil('\n'));
      }

      unsigned long now = millis();
      unsigned long offlineInterval = (unsigned long)(S_wait_time * 60.0 * 1000.0);

      if (now - lastOfflineMeasure >= offlineInterval) {
          lastOfflineMeasure = now;

          Serial.println("--- OFFLINE measurement ---");

          FullSensorReading raw_reading = performSmartMeasurement();

          if (raw_reading.isValid) {
              FullSensorReading final_reading = applyCalibration(
                  raw_reading,
                  active_profile,
                  S_gainValue,
                  U_gainValue,
                  S_integrationTime,
                  U_integrationTime
              );
              String csvLine = sensorReadingToCsv(
                  final_reading,
                  S_gainValue, S_integrationTime,
                  U_gainValue, U_integrationTime,
                  I_gainValue, I_integrationTime,
                  active_profile
              );

              Serial.println(csvLine);
          } else {
              Serial.println("Offline: invalid reading.");
          }
      }

      delay(20);
  }

  if (wifi_toggle) {
    static bool networkInitialized = false;
    static unsigned long lastWifiAttempt = 0;

    if (WiFi.status() != WL_CONNECTED) {
      networkInitialized = false;
      unsigned long nowMs = millis();
      if (nowMs - lastWifiAttempt > 10000) {
        Serial.print("Reconnecting WiFi...");
        WiFi.begin(WIFI_SSID, WIFI_PASS);
        lastWifiAttempt = nowMs;
      }
      delay(200);
      return;
    }

    if (!networkInitialized) {
      setupMqtt(client, deviceName, callback);
      configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
      struct tm ti;
      if (!getLocalTime(&ti)) {
        Serial.println("Waiting for NTP time...");
        delay(500);
        return;
      }
      networkInitialized = true;
      Serial.printf("Current time: %02d:%02d:%02d\n", ti.tm_hour, ti.tm_min, ti.tm_sec);
    }

    struct tm timeinfo;
    if (!getLocalTime(&timeinfo)) {
      delay(1000);
      return;
    }

    handleMqtt(client, deviceName);

    if (Serial.available()) {
      processSerialCommand(Serial.readStringUntil('\n'));  
    }

    long seconds_of_the_day = (timeinfo.tm_hour * 3600L) + (timeinfo.tm_min * 60L) + timeinfo.tm_sec;

    int sensor_interval_sec = (int)(S_wait_time * 60.0);
    if (sensor_interval_sec < 1) sensor_interval_sec = 1;
    bool isSensorScheduled = (sensor_interval_sec >= 1) && ((seconds_of_the_day % sensor_interval_sec) < 2) && (seconds_of_the_day != lastSensorTriggerSecond);

    if (triggerSensorMeasurement || isSensorScheduled) {
      if (isSensorScheduled) {
          lastSensorTriggerSecond = seconds_of_the_day;
          Serial.printf("--- SENSOR action due to Wall-Clock Sync at %02d:%02d:%02d ---\n", timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
      } else {
          Serial.println("--- SENSOR action due to on-demand trigger ---");
      }
      publishHealthStatus(client, deviceName);
      FullSensorReading raw_reading = performSmartMeasurement();
      if (raw_reading.isValid) {
        FullSensorReading final_reading = applyCalibration(raw_reading, active_profile, S_gainValue, U_gainValue, S_integrationTime, U_integrationTime);
        publishMetric(client, deviceName, "temperature", final_reading.temperature, 1, true);
        publishMetric(client, deviceName, "humidity", final_reading.humidity, 0, true);
        publishMetric(client, deviceName, "illuminance", final_reading.cal_lux, 0, true);
        publishMetric(client, deviceName, "Raw_Lux", final_reading.raw_lux, 0, true); 

        char filename[64];
        strftime(filename, sizeof(filename), "%Y%m%d_%H%M%S", &timeinfo);
        snprintf(filename + strlen(filename), sizeof(filename) - strlen(filename), "_%s.csv", deviceName.c_str());

        uploadCsvData(ftp, ftpLandingZone, filename, final_reading, S_gainValue, U_gainValue, I_gainValue, S_integrationTime, U_integrationTime, I_integrationTime);
        
        char topic[100];
        snprintf(topic, sizeof(topic), "sensors/%s/new_csv", deviceName.c_str());
        client.publish(topic, filename);
      }
      triggerSensorMeasurement = false;
    }

    delay(100);

    int camera_interval_sec = (int)(C_wait_time * 60.0);
    if (camera_interval_sec < 1) camera_interval_sec = 1;
    bool isCameraScheduled = (camera_interval_sec >= 1) && ((seconds_of_the_day % camera_interval_sec) < 2) && (seconds_of_the_day != lastCameraTriggerSecond);

    if (triggerCameraCapture || isCameraScheduled) {
      if (isCameraScheduled) {
          lastCameraTriggerSecond = seconds_of_the_day;
          Serial.printf("--- CAMERA action due to Wall-Clock Sync at %02d:%02d:%02d ---\n", timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
      } else {
          Serial.println("--- CAMERA action due to on-demand trigger ---");
      }
      if (cam_toggle) {
          if (hdr_toggle) {
            for (int i = 0; i < exposure_values.size(); i++) {
              capture_LDR_image(ftpLandingZone, exposure_values[i], ftp, timeinfo);
              
              char topic[100];
              snprintf(topic, sizeof(topic), "sensors/%s/hdr_image", deviceName.c_str());
              client.publish(topic, "captured");
            }
          } else {
            char filename[64];
            strftime(filename, sizeof(filename), "%Y%m%d_%H%M%S", &timeinfo);
            snprintf(filename + strlen(filename), sizeof(filename) - strlen(filename), "_%s.jpeg", deviceName.c_str());

            photo_send(filename, ftpLandingZone, ftp);

            char topic[100];
            snprintf(topic, sizeof(topic), "sensors/%s/new_image", deviceName.c_str());
            client.publish(topic, filename);
          }
      }
      triggerCameraCapture = false;
    }
  }
}
