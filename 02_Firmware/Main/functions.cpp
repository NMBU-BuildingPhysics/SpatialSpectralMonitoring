/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* This directory contains the source code for the ESP32-S3 microcontroller
* This file contains general utility functions used across the project
*/

#include "functions.h"
#include "secrets.h"
#include "datastructures.h"
#include "globals.h"
#include "sensors.h"
#include "calibration.h"
#include <cmath>

char mqtt_server[]= MQTT_SERVER;

float get_as7265x_effective_time_sec(int register_val) {
    float base_time_sec = (float)(register_val * 2.8) / 1000.0;
    return base_time_sec * 2.0;
}

float get_as7331_time_sec(int time_ms) {
    return (float)time_ms / 1000.0;
}

String sensorReadingToCsv(
    const FullSensorReading &reading,
    int S_gain, int S_time,
    int U_gain, int U_time,
    int I_gain, int I_time,
    const CalibrationProfile &profile
) {
    String csv = "";

    csv += String(S_gain) + "," + String(S_time) + ",";
    csv += String(U_gain) + "," + String(U_time) + ",";
    csv += String(I_gain) + "," + String(I_time) + ",";

    csv += String(reading.temperature, 2) + ",";
    csv += String(reading.humidity, 2) + ",";
    csv += String(reading.cal_lux, 2) + ",";

    csv += String(reading.raw_uvc) + ",";
    csv += String(reading.raw_uvb) + ",";
    csv += String(reading.raw_uva) + ",";

    for (int i = 0; i < 18; i++) {
        csv += String(reading.raw_spectral[i]);
        csv += ",";
    }

    csv += String(reading.cal_uvc, 2) + ",";
    csv += String(reading.cal_uvb, 2) + ",";
    csv += String(reading.cal_uva, 2) + ",";
    
    for (int i = 0; i < 18; i++) {
        csv += String(reading.cal_spectral[i], 2);
        if (i != 17) csv += ",";
    }

    return csv;
}

FullSensorReading performSmartMeasurement() {
    FullSensorReading reading;
    float temp_ignore;
    
    Serial.println("--- Starting Smart Measurement ---");

    if (!sht.Measure(&reading.temperature, &reading.humidity, SHT4X_REG_MEASURE_HIGH)) {
        Serial.println("ERROR: Failed to read SHT4X, aborting.");
        reading.isValid = false;
        return reading;
    }
    reading.temperature /= 1000.0;
    reading.humidity /= 1000.0;

    tsl.Get_ALS();
    reading.raw_lux = tsl.lux_data;

    const TempCoeffSet& lux_temp_model = getLuxTempCoefficients();
    float lux_temp_correction = (lux_temp_model.a * reading.temperature * reading.temperature) + (lux_temp_model.b * reading.temperature) + lux_temp_model.c;
    float temp_corrected_lux = reading.raw_lux / (lux_temp_correction != 0 ? lux_temp_correction : 1.0);
    float calibrated_lux = temp_corrected_lux * active_profile.lux_factor;
    
    Serial.printf("Scout reading: %.1f raw lux -> %.1f calibrated lux\n", reading.raw_lux, calibrated_lux);
    Serial.printf("raw_lux=%.2f, lux_factor=%.2f, calibrated=%.2f\n", reading.raw_lux, active_profile.lux_factor, reading.raw_lux * active_profile.lux_factor);

    int optimal_s_time_reg = 150;
    const AutoIntModel& model = getAutoIntegrationModel();

    if (!isfinite(reading.raw_lux) || !isfinite(calibrated_lux) || calibrated_lux <= 0.0f) {
      optimal_s_time_reg = S_INT_TIME_MAX;
      Serial.println("Invalid/low lux reading detected -> using max integration time.");
    } else {
      float optimal_time_sec = model.coeff_a * pow(calibrated_lux, model.coeff_b);
      optimal_s_time_reg = round((optimal_time_sec * 1000.0) / 5.6);

      if (optimal_s_time_reg < S_INT_TIME_MIN) optimal_s_time_reg = S_INT_TIME_MIN;
      if (optimal_s_time_reg > S_INT_TIME_MAX) optimal_s_time_reg = S_INT_TIME_MAX;
        
      Serial.printf("Model predicted %.3f sec -> Setting register to: %d\n", optimal_time_sec, optimal_s_time_reg);
    }
    
    updateIntegrationTime('S', optimal_s_time_reg);
    unsigned long wait_ms = (unsigned long)(S_integrationTime * 2.8 * 2.0) + 20;
    delay(wait_ms);

    if (as7265x.Get_DataStatus() && (as7331.Get_Status() & 0x0008)) {
        as7331.Get_All(&temp_ignore, &reading.raw_uva, &reading.raw_uvb, &reading.raw_uvc);
        as7265x.Get_Channel_Raw(reading.raw_spectral);
        
        reading.isValid = true;
        Serial.println("Main measurement successful.");
    } else {
        Serial.println("ERROR: Failed to get data from AS7265x/AS7331 after integration.");
        reading.isValid = false;
    }

    return reading;
}

FullSensorReading applyCalibration(const FullSensorReading& reading, const CalibrationProfile& profile, int s_gain, int u_gain, int s_time_reg_val, int u_time_ms) {
    FullSensorReading result = reading;
    float current_temp = reading.temperature;
    
    const TempCoeffSet& lux_temp_model = getLuxTempCoefficients();
    float lux_temp_correction = (lux_temp_model.a * current_temp * current_temp) + (lux_temp_model.b * current_temp) + lux_temp_model.c;
    if (lux_temp_correction != 0) {
        float temp_corrected_lux = reading.raw_lux / lux_temp_correction;
        result.cal_lux = temp_corrected_lux * profile.lux_factor;
    } else {
        result.cal_lux = reading.raw_lux * profile.lux_factor;
    }
    
    const uint16_t raw_uv_counts[] = {reading.raw_uva, reading.raw_uvb, reading.raw_uvc};
    const uint16_t* raw_spectral_counts = reading.raw_spectral;
    
    float u_time_sec = (float)u_time_ms / 1000.0;
    float s_time_sec = (float)(s_time_reg_val * 2.8 * 2.0) / 1000.0;

    for (size_t i = 0; i < masterChannelList.size(); ++i) {
        const ChannelInfo& channel = masterChannelList[i];
        
        uint16_t S_p_light = 0;
        float S_p_dark = 0.0f;
        float t_int = 0;
        int G = 1;

        if (strncmp(channel.name, "UV", 2) == 0) {
            S_p_light = raw_uv_counts[channel.native_index];
            t_int = u_time_sec;
            G = u_gain;
        } else {
            S_p_light = raw_spectral_counts[channel.native_index];
            t_int = s_time_sec;
            G = s_gain;
        }

        S_p_dark = profile.S_p_dark[i];

        float C_p = profile.C_p[i];
        const TempCoeffSet& temp_model = getTempCoefficients(channel.name);
        float f_Tp = (temp_model.a * current_temp * current_temp) + (temp_model.b * current_temp) + temp_model.c;
        
        float Sp_prime_light = 0.0f;
        float Sp_prime_dark = 0.0f;
        float Sp_prime_net = 0.0f;
        
        if (t_int > 0 && G > 0 && f_Tp != 0) {
            Sp_prime_light = (float)S_p_light / (f_Tp * t_int * G);
            Sp_prime_dark = S_p_dark / (f_Tp * t_int * G);
            Sp_prime_net = Sp_prime_light - Sp_prime_dark;
        }
        
        float final_irradiance = 0.0f;
        if (C_p > 0 && Sp_prime_net > 0) {
            final_irradiance = C_p * Sp_prime_net;
        }
        
        if (strncmp(channel.name, "UV", 2) == 0) {
            if (strcmp(channel.name, "UVA") == 0) result.cal_uva = (final_irradiance < 0) ? 0 : final_irradiance;
            if (strcmp(channel.name, "UVB") == 0) result.cal_uvb = (final_irradiance < 0) ? 0 : final_irradiance;
            if (strcmp(channel.name, "UVC") == 0) result.cal_uvc = (final_irradiance < 0) ? 0 : final_irradiance;
        } else {
            result.cal_spectral[i - 3] = (final_irradiance < 0) ? 0 : final_irradiance;
        }
    }

    return result;
}
void capture_LDR_image(const char* baseDir, int exposure, ESP32_FTPClient &ftp, struct tm timeinfo) {
  setCameraExposure(exposure);

  char filename[64];
  strftime(filename, sizeof(filename), "%Y%m%d_%H%M%S", &timeinfo);
  snprintf(
      filename + strlen(filename),
      sizeof(filename) - strlen(filename),
      "_%s_exp%d.jpeg",
      deviceName.c_str(),
      exposure);
  photo_send(filename, baseDir, ftp);
}

void photo_send(const char * fileName, const char* uploadDir, ESP32_FTPClient &ftp) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Failed to get camera frame buffer");
    return;
  }
  ftp.OpenConnection();
  ftp.ChangeWorkDir(uploadDir);
  ftp.InitFile("Type I");
  ftp.NewFile(fileName);
  ftp.WriteData(fb->buf, fb->len);
  ftp.CloseFile();
  ftp.CloseConnection();
  esp_camera_fb_return(fb);
  Serial.printf("Uploaded to landing zone: %s\r\n", fileName);
}

void callback(char* topic, byte* payload, unsigned int length) {
  char message[length + 1];
  memcpy(message, payload, length);
  message[length] = '\0';
  
  if (length == 0) {
  return;
  }

  Serial.print("Message on topic: "); Serial.print(topic);
  Serial.print(". Payload: "); Serial.println(message);
  String topicStr = String(topic);
  if (topicStr.startsWith("control/trigger/")) {
    String command = String(message);
    command.toUpperCase();
    if (command == "BOTH" || command == "ALL") {
        triggerSensorMeasurement = true;
        triggerCameraCapture = true;
        Serial.println("Triggering BOTH sensors and camera.");
    } else if (command == "SENSORS" || command == "S") {
        triggerSensorMeasurement = true;
        Serial.println("Triggering SENSORS only.");
    } else if (command == "CAMERA" || command == "C") {
        triggerCameraCapture = true;
        Serial.println("Triggering CAMERA only.");
    } else {
      Serial.println("Invalid trigger command. Use S, C, or BOTH/ALL.");
    }
    return;
  }

    if (strcmp(topic, "control/wait_time") == 0) {
    float new_wait_time = atof(message);
    if (new_wait_time >= 0.167) {
      S_wait_time = new_wait_time;
      C_wait_time = new_wait_time;
      Serial.printf("ALL sync intervals updated to: %.2f minutes\n", new_wait_time);
      preferences.begin("sensor-settings", false);
      preferences.putFloat("s_wait_time", S_wait_time);
      preferences.putFloat("c_wait_time", C_wait_time);
      preferences.end();
      Serial.println("Saved both s_wait_time and c_wait_time to flash.");

    } else {
      Serial.println("Invalid wait time. Must be >= 0.167 minutes (10 seconds).");
    }
  }
  if (strcmp(topic, "control/S_wait_time") == 0) {
    float new_wait_time = atof(message);
    if (new_wait_time >= 0.167) {
      S_wait_time = new_wait_time;
      Serial.printf("Sensor sync interval updated to: %.2f minutes\n", S_wait_time);

      preferences.begin("sensor-settings", false);
      preferences.putFloat("s_wait_time", S_wait_time);
      preferences.end();
      Serial.println("Saved s_wait_time to flash.");

    } else {
      Serial.println("Invalid wait time. Must be >= 0.167 minutes (10 seconds).");
    }
  } 
  else if (strcmp(topic, "control/C_wait_time") == 0) {
    float new_wait_time = atof(message);
    if (new_wait_time >= 0.167) {
      C_wait_time = new_wait_time;
      Serial.printf("Master sync interval updated to: %.2f minutes\n", C_wait_time);
      preferences.begin("sensor-settings", false);
      preferences.putFloat("c_wait_time", C_wait_time);
      preferences.end();
      Serial.println("Saved c_wait_time to flash.");

    } else {
      Serial.println("Invalid wait time. Must be >= 0.167 minutes (10 seconds).");
    }
  }
  else if (strcmp(topic, "control/exposure_values") == 0) {
    Serial.println("Received new exposure values.");
    std::vector<int> new_values;

    String payloadStr(message);
    int lastIndex = 0;
    int commaIndex = 0;

    while ((commaIndex = payloadStr.indexOf(',', lastIndex)) != -1) {
        String valueStr = payloadStr.substring(lastIndex, commaIndex);
        new_values.push_back(valueStr.toInt());
        lastIndex = commaIndex + 1;
    }
    
    String lastValueStr = payloadStr.substring(lastIndex);
    lastValueStr.trim();
    if (lastValueStr.length() > 0) {
        new_values.push_back(lastValueStr.toInt());
    }

    if (!new_values.empty()) {
      exposure_values.swap(new_values);
      
      Serial.print("Exposure values updated successfully. New list: ");
      for (int val : exposure_values) {
        Serial.printf("%d ", val);
      }
      Serial.println();

    } else {
      Serial.println("Failed to parse any exposure values from the payload. It might be empty or invalid.");
    }
    return;
  }
  
  else if (strcmp(topic, "control/hdr_toggle") == 0) {
    String payloadStr(message);
    payloadStr.toUpperCase();
    if (payloadStr == "ON" || payloadStr == "TRUE" || payloadStr == "1") {
      hdr_toggle = true;
      Serial.println("HDR mode enabled.");
    } else if (payloadStr == "OFF" || payloadStr == "FALSE" || payloadStr == "0") {
      hdr_toggle = false;
      Serial.println("HDR mode disabled.");
    }
    return;
  }
}
static void reconnectMqtt(PubSubClient& client, const String& deviceName) {
  Serial.print("Attempting MQTT connection...");

  char status_topic[50];
  snprintf(status_topic, sizeof(status_topic), "sensors/%s/status", deviceName.c_str());

  if (client.connect(deviceName.c_str(), MQTT_USER, MQTT_PASS, status_topic, 1, true, "offline")) {
    Serial.println("connected");

    client.publish(status_topic, "online", true); 
    client.subscribe("control/S_wait_time");
    client.subscribe("control/C_wait_time");
    client.subscribe("control/wait_time");
    client.subscribe("control/exposure_values");
    client.subscribe("control/hdr_toggle");
    client.subscribe(("control/trigger/" + deviceName).c_str());
    client.subscribe("control/trigger/all");
    
  } else {
    Serial.print("failed, rc=");
    Serial.print(client.state());
    Serial.println(" - will try again in 5 seconds");
  }
}
void setupMqtt(PubSubClient& client, const String& deviceName, MqttCallback callback) {
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}
void handleMqtt(PubSubClient& client, const String& deviceName) {
  static unsigned long lastReconnectAttempt = 0;

  if (!client.connected() && wifi_toggle) {
    unsigned long now = millis();
    if (now - lastReconnectAttempt > 5000) {
      lastReconnectAttempt = now;
      reconnectMqtt(client, deviceName);
    }
  } else if (client.connected()) {
    client.loop();
  }
}

//CSV HEADER: S_gain,S_time,U_gain,U_time,I_gain,I_time,temperature,humidity,cal_lux,
//raw_uvc,raw_uvb,raw_uva,raw_ch1,raw_ch2,raw_ch3,raw_ch4,raw_ch5,raw_ch6,raw_ch13,raw_ch14,raw_ch7,raw_ch15,raw_ch8,raw_ch16,raw_ch9,raw_ch10,raw_ch11,raw_ch12,raw_ch17,raw_ch18,
//cal_260nm,cal_300nm,cal_360nm,cal_410nm,cal_435nm,cal_460nm,cal_485nm,cal_510nm,cal_535nm,cal_560nm,cal_585nm,cal_610nm,cal_645nm,cal_680nm,cal_705nm,cal_730nm,cal_760nm,cal_810nm,cal_860nm,cal_900nm,cal_940nm
void uploadCsvData(ESP32_FTPClient &ftp, const char* uploadDir, const char* fileName, const FullSensorReading& data, int s_gain, int u_gain, int i_gain, int s_time, int u_time, int i_time) {
    
    if (!data.isValid) {
        Serial.println("Cannot upload CSV, sensor data is invalid.");
        return;
    }

    const bool INCLUDE_CSV_HEADER = false;

    char csvBuffer[2400];
    int offset = 0;

    if (INCLUDE_CSV_HEADER) {
        offset += snprintf(csvBuffer + offset, sizeof(csvBuffer) - offset,
            "S_gain,S_time,U_gain,U_time,I_gain,I_time,"
            "temperature,humidity,cal_lux,");
            
        for (const auto& channel : masterChannelList) {
            offset += snprintf(csvBuffer + offset, sizeof(csvBuffer) - offset, "%s,", channel.csv_col_name);
        }
        for (size_t i = 0; i < masterChannelList.size(); ++i) {
            const auto& channel = masterChannelList[i];
            offset += snprintf(csvBuffer + offset, sizeof(csvBuffer) - offset, "cal_%dnm%s", 
                channel.wavelength, (i < masterChannelList.size() - 1) ? "," : "\n");
        }
    }

    offset += snprintf(csvBuffer + offset, sizeof(csvBuffer) - offset,
        "%d,%d,%d,%d,%d,%d,%.2f,%.2f,%.2f,",
        s_gain, s_time, u_gain, u_time, i_gain, i_time,
        data.temperature, data.humidity, data.cal_lux);

    const uint16_t raw_uv_counts[] = {data.raw_uva, data.raw_uvb, data.raw_uvc};
    const float cal_uv_values[] = {data.cal_uva, data.cal_uvb, data.cal_uvc};

    for (const auto& channel : masterChannelList) {
        if (strncmp(channel.name, "UV", 2) == 0) {
            offset += snprintf(csvBuffer + offset, sizeof(csvBuffer) - offset, "%u,", raw_uv_counts[channel.native_index]);
        } else {
            offset += snprintf(csvBuffer + offset, sizeof(csvBuffer) - offset, "%u,", data.raw_spectral[channel.native_index]);
        }
    }

    for (size_t i = 0; i < masterChannelList.size(); ++i) {
        const auto& channel = masterChannelList[i];
        float value_to_write = 0.0f;
        if (strncmp(channel.name, "UV", 2) == 0) {
            value_to_write = cal_uv_values[channel.native_index];
        } else {
            int sorted_cal_index = (int)(&channel - &masterChannelList[0]) - 3;
            if (sorted_cal_index >= 0 && sorted_cal_index < 18) {
                value_to_write = data.cal_spectral[sorted_cal_index];
            }
        }
        offset += snprintf(csvBuffer + offset, sizeof(csvBuffer) - offset, "%.4f%s", 
            value_to_write, (i < masterChannelList.size() - 1) ? "," : "\n");
    }

    ftp.OpenConnection();
    ftp.ChangeWorkDir(uploadDir);
    ftp.InitFile("Type A");
    ftp.NewFile(fileName);
    ftp.Write(csvBuffer);
    ftp.CloseFile();
    ftp.CloseConnection();

    Serial.printf("Uploaded to landing zone: %s\r\n", fileName);
}

void publishHealthStatus(PubSubClient& client, const String& deviceName) {
  char rssiPayload[10];
  snprintf(rssiPayload, sizeof(rssiPayload), "%ld", WiFi.RSSI());
  char topicBuffer[100];
  snprintf(topicBuffer, sizeof(topicBuffer), "sensors/%s/rssi", deviceName.c_str());
  client.publish(topicBuffer, rssiPayload, true);
  float uptime_hours = (float)millis() / 3600000.0;
  publishMetric(client, deviceName, "uptime_hours", uptime_hours, 2, true);
}

void publishMetric(PubSubClient& client, const String& deviceName, const char* metric, float value, int decimals, bool retain)  {

  char topicBuffer[100];
  char payloadBuffer[20];
  char formatBuffer[8];

  snprintf(topicBuffer, sizeof(topicBuffer), "sensors/%s/%s", deviceName.c_str(), metric);
  snprintf(formatBuffer, sizeof(formatBuffer), "%%.%df", decimals);
  snprintf(payloadBuffer, sizeof(payloadBuffer), formatBuffer, value);

  client.publish(topicBuffer, payloadBuffer, retain);
}

void publishMetric(PubSubClient& client, const String& deviceName, const char* metric, unsigned int value, bool retain)  {
  char topicBuffer[100];
  char payloadBuffer[20];
  snprintf(topicBuffer, sizeof(topicBuffer), "sensors/%s/%s", deviceName.c_str(), metric);
  snprintf(payloadBuffer, sizeof(payloadBuffer), "%u", value);
  client.publish(topicBuffer, payloadBuffer, retain);
}

void ledLight(bool toggle) {
  if (toggle) {    //Turn off light
    as7265x.Set_LED(AS7265X_SELECT_AS72651, AS7265X_LED_IND_ENABLE | AS7265X_LED_DRV_ENABLE | AS7265X_LED_DRV_100MA);
    as7265x.Set_LED(AS7265X_SELECT_AS72652, AS7265X_LED_IND_ENABLE | AS7265X_LED_DRV_ENABLE);
    as7265x.Set_LED(AS7265X_SELECT_AS72653, AS7265X_LED_IND_ENABLE | AS7265X_LED_DRV_ENABLE);
  }
  else {        //Turn off light
    as7265x.Set_LED(AS7265X_SELECT_AS72651, AS7265X_LED_IND_DISABLE | AS7265X_LED_DRV_DISABLE | AS7265X_LED_DRV_DISABLE);
    as7265x.Set_LED(AS7265X_SELECT_AS72652, AS7265X_LED_IND_DISABLE | AS7265X_LED_DRV_DISABLE);
    as7265x.Set_LED(AS7265X_SELECT_AS72653, AS7265X_LED_IND_DISABLE | AS7265X_LED_DRV_DISABLE);
  }
}

void setCameraExposure(int exposure_value) {
  sensor_t *s = esp_camera_sensor_get();
  s->set_aec_value(s, exposure_value);

  for (int i = 0; i < 2; ++i) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) {
      esp_camera_fb_return(fb);
    } else {
      break;
    }
    delay(100);
  }
  delay(150);
}

void updateGain(char sensorType, int gainValue) {
    switch (sensorType) {
        case 'S':
            switch (gainValue) {
                case 1: as7265x.Set_Gain(AS7265X_GAIN_1X); break;
                case 4: as7265x.Set_Gain(AS7265X_GAIN_3_7X); break;
                case 16: as7265x.Set_Gain(AS7265X_GAIN_16X); break;
                case 64: as7265x.Set_Gain(AS7265X_GAIN_64X); break;
                default:
                    Serial.println("Invalid spectral gain. Valid: 1, 4, 16, 64.");
                    return;
            }
            S_gainValue = gainValue;
            Serial.print("Spectral gain set to: "); Serial.println(S_gainValue);
            return;

        case 'U':
            as7331.Set_Device_State(AS7331_STATE_CONFIGURATION);
            switch (gainValue) {
                case 1: as7331.Set_GAIN(AS7331_GAIN_1X); break;
                case 2: as7331.Set_GAIN(AS7331_GAIN_2X); break;
                case 4: as7331.Set_GAIN(AS7331_GAIN_4X); break;
                case 8: as7331.Set_GAIN(AS7331_GAIN_8X); break;
                case 16: as7331.Set_GAIN(AS7331_GAIN_16X); break;
                case 32: as7331.Set_GAIN(AS7331_GAIN_32X); break;
                case 64: as7331.Set_GAIN(AS7331_GAIN_64X); break;
                case 128: as7331.Set_GAIN(AS7331_GAIN_128X); break;
                case 256: as7331.Set_GAIN(AS7331_GAIN_256X); break;
                case 512: as7331.Set_GAIN(AS7331_GAIN_512X); break;
                case 1024: as7331.Set_GAIN(AS7331_GAIN_1024X); break;
                case 2048: as7331.Set_GAIN(AS7331_GAIN_2048X); break;
                default:
                    Serial.println("Invalid UV gain. Valid: 1-2048 (powers of two).");
                    return;
            }
            U_gainValue = gainValue;
            Serial.print("UV gain set to: "); Serial.println(U_gainValue);
            as7331.Set_Device_State(AS7331_STATE_MEASUREMENT);
            as7331.Set_Measurement(AS7331_MEASUREMENT_START);
            return;

        case 'I':
            switch (gainValue) {
                case 0: tsl.Set_GAIN(TSL2591_GAIN_LOW); break;
                case 1: tsl.Set_GAIN(TSL2591_GAIN_MED); break;
                case 2: tsl.Set_GAIN(TSL2591_GAIN_HIGH); break;
                case 3: tsl.Set_GAIN(TSL2591_GAIN_MAX); break;
                default:
                    Serial.println("Invalid illuminance gain. Valid: 0 (LOW) to 3 (MAX).");
                    return;
            }
            I_gainValue = gainValue;
            tsl.Enable();
            Serial.print("Illuminance gain set to: "); Serial.println(I_gainValue);
            
            return;

        default:
            Serial.println("Unknown sensor type for GAIN.");
            return;
    }
}
void updateIntegrationTime(char sensorType, int integrationTime) {
  const int S_minTime = 1;
  const int S_maxTime = 255;
    switch (sensorType) {
        case 'S': { // Spectral (AS7265X)
            if (integrationTime < S_minTime || integrationTime > S_maxTime) {
                Serial.println("Invalid spectral integration time. Must be 1–255.");
                return;
            }
            as7265x.Set_Integration(integrationTime);
            S_integrationTime = integrationTime;
            Serial.print("Spectral integration time set to: ");
            Serial.println(S_integrationTime);
            return;
        }

          case 'U': { // UV (AS7331)
            as7331.Set_Device_State(AS7331_STATE_CONFIGURATION);
            switch (integrationTime) {
                case 1: as7331.Set_Integration_Time(AS7331_TIME_1MS); break;
                case 2: as7331.Set_Integration_Time(AS7331_TIME_2MS); break;
                case 4: as7331.Set_Integration_Time(AS7331_TIME_4MS); break;
                case 8: as7331.Set_Integration_Time(AS7331_TIME_8MS); break;
                case 16: as7331.Set_Integration_Time(AS7331_TIME_16MS); break;
                case 32: as7331.Set_Integration_Time(AS7331_TIME_32MS); break;
                case 64: as7331.Set_Integration_Time(AS7331_TIME_64MS); break;
                case 128: as7331.Set_Integration_Time(AS7331_TIME_128MS); break;
                case 256: as7331.Set_Integration_Time(AS7331_TIME_256MS); break;
                case 512: as7331.Set_Integration_Time(AS7331_TIME_512MS); break;
                case 1024: as7331.Set_Integration_Time(AS7331_TIME_1024MS); break;
                case 2048: as7331.Set_Integration_Time(AS7331_TIME_2048MS); break;
                case 4096: as7331.Set_Integration_Time(AS7331_TIME_4096MS); break;
                case 8192: as7331.Set_Integration_Time(AS7331_TIME_8192MS); break;
                case 16384: as7331.Set_Integration_Time(AS7331_TIME_16384MS); break;
                default: 
                    Serial.println("Invalid UV integration time. Valid: 1–16384 (powers of two).");
                    return;
            }
            U_integrationTime = integrationTime;
            Serial.print("UV integration time set to: "); Serial.println(U_integrationTime);
            as7331.Set_Device_State(AS7331_STATE_MEASUREMENT);
            as7331.Set_Measurement(AS7331_MEASUREMENT_START);
            return;
          }

        case 'I': { // Illuminance (TSL2591)
            switch (integrationTime) {
                case 100: tsl.Set_Integration_Time(TSL2591_TIME_100MS); break;
                case 200: tsl.Set_Integration_Time(TSL2591_TIME_200MS); break;
                case 300: tsl.Set_Integration_Time(TSL2591_TIME_300MS); break;
                case 400: tsl.Set_Integration_Time(TSL2591_TIME_400MS); break;
                case 500: tsl.Set_Integration_Time(TSL2591_TIME_500MS); break;
                case 600: tsl.Set_Integration_Time(TSL2591_TIME_600MS); break;
                default:
                    Serial.println("Invalid illuminance integration time. Valid: 100, 200, 300, 400, 500, 600.");
                    return;
            }
            I_integrationTime = integrationTime;
            tsl.Enable();
            Serial.print("Illuminance integration time set to: "); Serial.println(I_integrationTime);
            return;
          }        

        default:
            Serial.println("Unknown sensor type for TIME.");
            return;
    }
}

void processSerialCommand(String command) {
  command.trim();
  command.toUpperCase();

  if (command == "HEALTH") {
    Serial.println("--- Sending health status ---");
    publishHealthStatus(client, deviceName);
    return;
  } 
  
  if (command == "SENS" || command == "SENSOR" || command == "SEN" ) {
    Serial.println("--- Queuing SENSOR action from SERIAL trigger ---");
    triggerSensorMeasurement = true;
    return;
  } 
  
  if (command == "CAM" || command == "CAMERA") {
    Serial.println("--- Queuing CAMERA action from SERIAL trigger ---");
    triggerCameraCapture = true;
    return;
  }

  if (command.startsWith("CAM ")) {
    String toggleValue = command.substring(4);
    toggleValue.trim();
    if (toggleValue == "ON" || toggleValue == "TRUE" || toggleValue == "1") {
        cam_toggle = true;
    } else if (toggleValue == "OFF" || toggleValue == "FALSE" || toggleValue == "0") {
        cam_toggle = false;
    }
    Serial.print("Camera toggle set to: ");
    Serial.println(cam_toggle ? "ON" : "OFF");
    return;
  }
  
  if (command.startsWith("HDR ")) {
    String toggleValue = command.substring(4);
    toggleValue.trim();
    if (toggleValue == "ON" || toggleValue == "TRUE" || toggleValue == "1") {
        hdr_toggle = true;
    } else if (toggleValue == "OFF" || toggleValue == "FALSE" || toggleValue == "0") {
        hdr_toggle = false;
    }
    Serial.print("HDR toggle set to: ");
    Serial.println(hdr_toggle ? "ON" : "OFF");
    return;
  }
  
  if (command.startsWith("WIFI ")) {
    String toggleValue = command.substring(5);
    toggleValue.trim();
    if (toggleValue == "ON" || toggleValue == "TRUE" || toggleValue == "1") {
        wifi_toggle = true;
        Serial.println("Wi-Fi enabled. Will attempt to connect/reconnect.");
        if (WiFi.status() != WL_CONNECTED) {
          WiFi.begin(WIFI_SSID, WIFI_PASS);
        }
    } else if (toggleValue == "OFF" || toggleValue == "FALSE" || toggleValue == "0") {
        wifi_toggle = false;
        Serial.println("Wi-Fi disabled. Disconnecting if connected.");
        WiFi.disconnect(true);
    }
    Serial.print("Wi-Fi toggle set to: ");
    Serial.println(wifi_toggle ? "ON" : "OFF");
    return;
  }

  if (command.length() > 6 && command.charAt(1) == ' ') { 
    char sensorType = command.charAt(0);
    String actionPart = command.substring(2);

    if (actionPart.startsWith("GAIN ")) {
      int value = actionPart.substring(5).toInt();
      updateGain(sensorType, value);
      return; 
    }
    
    if (actionPart.startsWith("TIME ")) {
      int value = actionPart.substring(5).toInt();
      updateIntegrationTime(sensorType, value);
      return;
    } 
    
    if (actionPart.startsWith("WAIT ")) {
      float value = actionPart.substring(5).toFloat();
      switch (sensorType) {
        case 'S':
          S_wait_time = value;
          Serial.print("Sensor wait time set to: "); Serial.println(S_wait_time);
          break;
        case 'C':
          C_wait_time = value;
          Serial.print("Camera wait time set to: "); Serial.println(C_wait_time);
          break;
        default:
          Serial.println("Invalid sensor type for WAIT.");
          break;
      }
      return;
    }
  }

  Serial.println("Invalid command. Use: HEALTH, SENSOR, CAM, WIFI ON/OFF, CAM ON/OFF, or <S|C|I> <GAIN|TIME|WAIT> <Value>");
}