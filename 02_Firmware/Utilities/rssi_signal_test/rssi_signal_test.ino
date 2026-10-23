/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
* 
* Description:
* This sketch tests the RSSI signal strength
*/

#include <WiFi.h>
#include <SPI.h>
#include "secrets.h"
#include <AS7265X.h>

AS7265X as7265x;

void setupAS7265X() {
    if (!as7265x.begin()) {
        Serial.println("AS7265X initialize error.");
        while (1);
    }
    as7265x.Set_Interrupt(true);

    as7265x.Set_Gain(AS7265X_GAIN_3_7X);
    as7265x.Set_Measurement(AS7265X_MEASUREMENT_MODE2);
    as7265x.Set_Integration(15);
}

void ledLight(bool toggle) {
  if (toggle) {
    as7265x.Set_LED(AS7265X_SELECT_AS72651, AS7265X_LED_IND_ENABLE | AS7265X_LED_DRV_ENABLE | AS7265X_LED_DRV_100MA);
    as7265x.Set_LED(AS7265X_SELECT_AS72652, AS7265X_LED_IND_ENABLE | AS7265X_LED_DRV_ENABLE);
    as7265x.Set_LED(AS7265X_SELECT_AS72653, AS7265X_LED_IND_ENABLE | AS7265X_LED_DRV_ENABLE);
  }
  else {
    as7265x.Set_LED(AS7265X_SELECT_AS72651, AS7265X_LED_IND_DISABLE | AS7265X_LED_DRV_DISABLE | AS7265X_LED_DRV_DISABLE);
    as7265x.Set_LED(AS7265X_SELECT_AS72652, AS7265X_LED_IND_DISABLE | AS7265X_LED_DRV_DISABLE);
    as7265x.Set_LED(AS7265X_SELECT_AS72653, AS7265X_LED_IND_DISABLE | AS7265X_LED_DRV_DISABLE);
  }
}

void blinkLedBasedOnRSSI() {
    int rssi = WiFi.RSSI();
    Serial.print("Wi-Fi RSSI: ");
    Serial.println(rssi);

    if (rssi > -15) {
        ledLight(true);
        delay(10);
        ledLight(false);
        delay(10);
    }
    else if (rssi > -20) {
        ledLight(true);
        delay(25);
        ledLight(false);
        delay(25);
    }
    else if (rssi > -30) {
        ledLight(true);
        delay(100);
        ledLight(false);
        delay(100);
    }
    else if (rssi > -40) {
        ledLight(true);
        delay(200);
        ledLight(false);
        delay(200);
    }
    else if (rssi > -50) {
        ledLight(true);
        delay(500);
        ledLight(false);
        delay(500);
    }
    else if (rssi > -100) {
        ledLight(true);
        delay(1000);
        ledLight(false);
        delay(1000);
    }
    else {
        ledLight(true);
    }
}

void setup() {
    Serial.begin(115200);

    setupAS7265X();
    Serial.print("CPU Frequency: ");
    Serial.print(getCpuFrequencyMhz());
    Serial.println(" MHz");
    esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);

    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.println("Connecting Wifi...");

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println("\nWiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());

    WiFi.setSleep(false);
    Serial.println("Wi-Fi sleep mode disabled.");
    WiFi.setTxPower(WIFI_POWER_20_5dBm);
}

int lastRSSI = 0;
unsigned long lastReconnectAttempt = 0;

void loop() {
    if (WiFi.status() == WL_CONNECTED) {
            int currentRSSI = WiFi.RSSI();
        if (abs(currentRSSI - lastRSSI) > 2) {
            lastRSSI = currentRSSI;
            blinkLedBasedOnRSSI();
      }
    } else {
        Serial.println("WiFi disconnected! Trying to reconnect...");
        if (millis() - lastReconnectAttempt > 5000) {
            lastReconnectAttempt = millis();
            WiFi.disconnect();
            WiFi.reconnect();
        }
    }
    delay(500);
}
