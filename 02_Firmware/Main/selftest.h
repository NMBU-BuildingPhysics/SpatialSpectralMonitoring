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

#pragma once

#include <Arduino.h>
#include <PubSubClient.h>

void runSelfTest(PubSubClient& client, const String& deviceName, const char* group = "ALL");
