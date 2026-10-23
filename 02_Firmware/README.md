# Sensor Firmware

This directory contains the source code for the ESP32-S3 microcontroller. It is divided into the main firmware for deployment and utilities for hardware verification and characterisation.

## Prerequisites

1.  **IDE:** Arduino IDE (v2.3.4)
2.  **Board Manager:** Install `esp32` by Espressif Systems.
3.  **Selected Board:** `XIAO_ESP32S3`.
4.  **PSRAM:** Must be **Enabled** (OPI) in Tools settings (required for the HDR buffers).

## Dependencies
Ensure the following libraries are installed or included in the `src` folder:
*   `PubSubClient 2.8` (MQTT)
*   `ESP32_FTPClient 0.1.4` (FTP)
*   `esp_camera 3.1.0w` (Built-in to ESP32 core)
*   `AS7265x`, `AS7331`, `TSL2591` and `SHT4x` libraries. 
    * Check `src/sensors` folder

## Directory Structure

### `Main/`
The firmware used in the sensors.
*   **Functionality:** Goal-seeking auto-exposure of the spectral sensors, on-device HDR merge and Radiance `.hdr` encoding, MQTT control, NTP time and FTP upload. Capture and network run as separate tasks on the two cores.
*   **Files:**
    *   `Main.ino` – setup, capture task and network task
    *   `measurement.cpp` – auto-exposure, calibration and CSV output
    *   `camera.cpp` – HDR capture, merge, encoding and upload
    *   `comms.cpp` – MQTT, serial commands and crash reports
    *   `sensor_init.cpp` – sensor and camera initialisation
    *   `selftest.cpp` – pre-deployment self-test (`TEST`)
    *   `config.h` – device name, intervals and default settings
*   **Setup:**
    1.  Copy `secrets.example.h` to `Main/secrets.h` and set:
        *   `WIFI_SSID`, `WIFI_PASS`
        *   `MQTT_SERVER`, `MQTT_USER`, `MQTT_PASS`
        *   `FTP_SERVER`, `FTP_USER`, `FTP_PASS`, `FTP_LANDING_ZONE`
    2.  Copy `calibration.example.cpp` to `Main/calibration.cpp` and add the calibration factors.
        * Calibration pipeline found in `03_Python_Suite`
    3.  Set `DEVICE_NAME` in `Main/config.h` (sensor01 … sensor12).
    4.  Optional: run `generate_version.ps1` to stamp the git version into `Main/version.h`.
*   **Commands:** see the [Command Cheat Sheet](../04_Documentation/command-cheatsheet.md).

### `Utilities/`
Standalone sketches to verify and characterise the hardware.

*   **`camera_web_server`**: Streams video to a browser. Used for the camera calibration and characterisation pipeline.
*   **`find_register`**: Scans the I2C bus to confirm that the AS7265x, AS7331, TSL2591 and SHT4x respond.
*   **`int_time_characterization`**: Integration time sweep used for the auto-integration model in v1.0.0.
*   **`rssi_signal_test`**: Tests WiFi signal strength inside the enclosure.
*   **`spectral_gain_time_sweep`**: AS7265x gain × integration time sweep, using the Main firmware sources.
*   **`thermal_characterization`**: Fixed-settings logger for thermal characterisation.
*   **`tsl_gain_integration_sweep`**: TSL2591 gain × integration time sweep. Needs the TSL2591 and SHT4x drivers in its own `src/sensors` folder (not included, same as Main).
