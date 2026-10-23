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

#pragma once

#include "datastructures.h"
#include "calibration.h"
#include <PubSubClient.h>

class ESP32_FTPClient;

using MqttCallback = void (*)(char*, uint8_t*, unsigned int);

void onMqttMessage(char* topic, byte* payload, unsigned int length);
void setupMqtt(PubSubClient& client, const String& deviceName, MqttCallback cb);
void handleMqtt(PubSubClient& client, const String& deviceName);
void maintainMqtt();
bool isUploadDeadlineImminent();

void publishHealthStatus(PubSubClient& client, const String& deviceName);
void publishMetric(PubSubClient& client, const String& deviceName,
                   const char* metric, float value, int decimals, bool retain = false);
void publishMetric(PubSubClient& client, const String& deviceName,
                   const char* metric, unsigned int value, bool retain = false);

void handleSerialCommand(String command);

void saveCrashReason(const char* reason);
void publishCrashReport(PubSubClient& client, const String& deviceName);

int parseBool(const char* str);
