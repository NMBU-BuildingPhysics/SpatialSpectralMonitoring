/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
* 
* Description:
* This file contains the main setup and loop functions for scanning I2C registers
*/

 
#include <Wire.h>

#define SDA_PIN 8  // Define the SDA pin (GPIO8 by default)
#define SCL_PIN 9  // Define the SCL pin (GPIO9 by default)

void setup() {
  // Initialize the I2C bus on the specific pins
  Wire.begin(SDA_PIN, SCL_PIN);
  Serial.begin(115200);
  
  while (!Serial);
  Serial.println("I2C Scanner");
}

void loop() {
  byte error, address;
  int devicesFound = 0;
  
  for (address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();
    
    if (error == 0) {
      Serial.print("I2C device found at address 0x");
      if (address < 16) {
        Serial.print("0");
      }
      Serial.println(address, HEX);
      devicesFound++;
    }
  }
  
  if (devicesFound == 0) {
    Serial.println("No devices found");
  }
  delay(5000);
}
