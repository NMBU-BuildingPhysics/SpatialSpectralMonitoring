# Sensor Firmware

This directory contains the source code for the ESP32-S3 microcontroller. It is divided into diagnostic tools for hardware verification and the main production firmware for deployment.

## Prerequisites

1.  **IDE:** Arduino IDE (v2.3.4)
2.  **Board Manager:** Install `esp32` by Espressif Systems.
3.  **Selected Board:** `XIAO_ESP32S3`.
4.  **PSRAM:** Must be **Enabled** (OPI) in Tools settings (Required for camera buffers).

## Dependencies
Ensure the following libraries are installed or included in the `src` folder:
*   `PubSubClient` (MQTT)
*   `ESP32_FTPClient` (FTP)
*   `esp_camera` (Built-in to ESP32 core)
*   `AS7265x`, `AS7331`, `TSL2591` and `SHT4x` libraries. 
    * Check `src/sensors` folder

## Directory Structure

### `Main/`
The primary firmware for data logging.
*   **Functionality:** Orchestrates the camera and spectral sensors logging, handles MQTT communication, performs auto-exposure logic, and manages FTP uploads.
*   **Setup:**
    1.  Change `secrets.example.h` to `secrets.h` and set:
        *   `WIFI_SSID`, `WIFI_PASS`
        *   `MQTT_SERVER`, `FTP_SERVER`
        *   `FTP_USER`, `FTP_PASS`, `FTP_PATH`
    2.  Define your specific `DEVICE_NAME` in `config.h`.
    3.  Upload calibration factors into `calibration.cpp`.
        * Calibration pipeline found in `03_Python_Suite`

### `Utilities/`
Standalone sketches to verify hardware subsystems before deploying the main firmware.

*   **`Camera_Web_Server`**: Streams video to a browser. Use this for camera calibration and characterization pipeline.
*   **`Find_Register`**: Scans the I2C bus. Run this to confirm the ESP32 can talk to the AS7265x, AS7331, TSL2591, and SHT4x sensors.
*   **`Int_Time_Characterization`**: A specialized utility used to generate the "Auto-Integration Time" model. It sweeps through integration times while recording raw spectral counts, temperature and lux values.
*   **`RSSI_Signal_Test`**: Simple tool to test WiFi antenna performance inside the enclosure.