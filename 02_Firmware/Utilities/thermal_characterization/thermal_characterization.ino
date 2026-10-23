/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* Fixed gain and integration time serial logger for thermal characterisation.
* CSV output matches the Main firmware format.
*/

#include "../../Main/config.h"
#include "../../Main/datastructures.h"
#include "../../Main/globals.h"
#include "../../Main/calibration.h"
#include "../../Main/sensor_init.h"
#include "../../Main/measurement.h"
#include "../../Main/comms.h"
#include "../../Main/camera.h"
#include <Wire.h>
#include <climits>
#include <cmath>

#include "../../Main/src/sensors/SHT4X.cpp"
#include "../../Main/src/sensors/TSL2591.cpp"
#include "../../Main/src/sensors/AS7265X.cpp"
#include "../../Main/src/sensors/AS7331.cpp"

#include "../../Main/calibration.cpp"
#include "../../Main/sensor_init.cpp"
#include "../../Main/measurement.cpp"
#include "../../Main/comms.cpp"
#include "../../Main/camera.cpp"

#define TC_DEVICE_NAME  "sensor06"

#define TC_S_GAIN  4
#define TC_S_TIME  165

#define TC_U_GAIN  64
#define TC_U_TIME  128

#define TC_I_GAIN  0
#define TC_I_TIME  200

#define TC_INTERVAL_SEC  1

String deviceName = TC_DEVICE_NAME;

bool cam_toggle  = false;
bool hdr_toggle  = false;
bool jpeg_toggle = false;
bool wifi_toggle = false;

CalibrationProfile     active_profile;
volatile bool          triggerSensorMeasurement = false;
volatile bool          triggerCameraCapture     = false;
float                  S_wait_time              = 1.0f;
float                  C_wait_time              = 1.0f;
int                    upload_stagger_ms        = 0;
time_t                 nextSensorTrigger        = LONG_MAX;
time_t                 nextCameraTrigger        = LONG_MAX;

std::vector<int> exposure_values     = {};
int              hdr_avg_frames      = 1;
bool             hdr_sat_fill        = false;
bool             hdr_early_term      = false;
float            hdr_et_pct          = 0.0f;
int              hdr_et_min_exp      = 0;
float            hdr_et_radius_pct   = 0.0f;

bool cam_cal_enable              = false;
bool cam_vign_enable             = false;
bool cam_crop_enable             = false;
const CameraCalibration* cam_cal_colour = nullptr;
float cam_cal_scale_override     = 1.0f;
bool  cam_cal_scale_overridden   = false;

int S_gainValue       = TC_S_GAIN;
int U_gainValue       = TC_U_GAIN;
int I_gainValue       = TC_I_GAIN;
int S_integrationTime = TC_S_TIME;
int U_integrationTime = TC_U_TIME;
int I_integrationTime = TC_I_TIME;

char            ftp_user[] = FTP_USER;
char            ftp_pass[] = FTP_PASS;
WiFiClient      espClient;
PubSubClient    client(espClient);
ESP32_FTPClient ftp(FTP_SERVER, ftp_user, ftp_pass, 5000, 0);
Preferences     preferences;

QueueHandle_t     uploadQueue       = NULL;
SemaphoreHandle_t i2cMutex          = NULL;
SemaphoreHandle_t hdrBufferSem      = NULL;
TaskHandle_t      captureTaskHandle = NULL;
TaskHandle_t      networkTaskHandle = NULL;

static int g_interval_sec = TC_INTERVAL_SEC;

static void handleTcCommand(const String& raw) {
    String cmd = raw;
    cmd.trim();
    String upper = cmd;
    upper.toUpperCase();

    if (upper == "HELP") {
        Serial.println("--- Thermal Characterization Commands ---");
        Serial.println("  S GAIN <1|4|16|64>              AS7265X gain");
        Serial.println("  S TIME <1-255>                  AS7265X integration-time register");
        Serial.println("  U GAIN <1..2048, pow2>          AS7331 gain");
        Serial.println("  U TIME <1..16384, pow2 ms>      AS7331 integration time");
        Serial.println("  I GAIN <0..3>                   TSL2591 gain index");
        Serial.println("  I TIME <100..600, step 100 ms>  TSL2591 integration time");
        Serial.println("  INTERVAL <seconds>              Delay between measurements");
        Serial.println("  HEADER                          Reprint CSV header");
        Serial.println("  NOW                             Trigger immediate measurement");
        Serial.println("  STATUS                          Print current settings");
        Serial.println("  HELP                            Print this list");
    } else if (upper == "HEADER") {
        printCsvHeader();
    } else if (upper == "NOW") {
        triggerSensorMeasurement = true;
    } else if (upper == "STATUS") {
        Serial.printf("S: gain=%d  time_reg=%d (%.0f ms)\n",
                      S_gainValue, S_integrationTime,
                      S_integrationTime * AS7265X_BASE_PERIOD_MS * AS7265X_MODE2_MULTIPLIER);
        Serial.printf("U: gain=%d  time=%d ms\n", U_gainValue, U_integrationTime);
        Serial.printf("I: gain=%d  time=%d ms\n", I_gainValue, I_integrationTime);
        Serial.printf("Interval: %d s\n", g_interval_sec);
    } else if (upper.startsWith("INTERVAL ")) {
        int val = upper.substring(9).toInt();
        if (val >= 1) {
            g_interval_sec = val;
            Serial.printf("Interval set to %d s\n", g_interval_sec);
        } else {
            Serial.println("ERROR: INTERVAL must be >= 1");
        }
    } else if (upper.startsWith("S GAIN ")) {
        int val = upper.substring(7).toInt();
        setGain('S', val);
        Serial.printf("S gain set to %d\n", S_gainValue);
    } else if (upper.startsWith("S TIME ")) {
        int val = upper.substring(7).toInt();
        setIntegrationTime('S', val);
        Serial.printf("S time_reg set to %d (%.0f ms)\n",
                      S_integrationTime,
                      S_integrationTime * AS7265X_BASE_PERIOD_MS * AS7265X_MODE2_MULTIPLIER);
    } else if (upper.startsWith("U GAIN ")) {
        int val = upper.substring(7).toInt();
        setGain('U', val);
        Serial.printf("U gain set to %d\n", U_gainValue);
    } else if (upper.startsWith("U TIME ")) {
        int val = upper.substring(7).toInt();
        setIntegrationTime('U', val);
        Serial.printf("U time set to %d ms\n", U_integrationTime);
    } else if (upper.startsWith("I GAIN ")) {
        int val = upper.substring(7).toInt();
        setGain('I', val);
        Serial.printf("I gain set to %d\n", I_gainValue);
    } else if (upper.startsWith("I TIME ")) {
        int val = upper.substring(7).toInt();
        setIntegrationTime('I', val);
        Serial.printf("I time set to %d ms\n", I_integrationTime);
    } else if (upper.length() > 0) {
        Serial.printf("Unknown command: '%s'  (type HELP)\n", cmd.c_str());
    }
}

static void refreshTSL() {
    tsl.Disable();
    delay(10);
    tsl.Enable();
    delay(I_integrationTime + 50);
    tsl.Get_ALS();
}

static FullSensorReading measureQuiet() {
    FullSensorReading reading;
    float temp_ignore;

    if (!sht.Measure(&reading.temperature, &reading.humidity, SHT4X_REG_MEASURE_HIGH)) {
        reading.temperature = 25000.0f;
        reading.humidity    = 50000.0f;
    }
    reading.temperature /= 1000.0f;
    reading.humidity    /= 1000.0f;

    reading.tsl_ch0 = tsl.all_data;
    reading.tsl_ch1 = tsl.ir_data;
    reading.raw_lux = tsl.lux_data;

    bool as7265x_ready = false;
    {
        unsigned long period_ms = static_cast<unsigned long>(
            S_integrationTime * AS7265X_BASE_PERIOD_MS * AS7265X_MODE2_MULTIPLIER);
        delay(period_ms);
        unsigned long deadline = millis() + period_ms + 100;
        do {
            as7265x_ready = as7265x.Get_DataStatus();
            if (as7265x_ready) break;
            if (millis() >= deadline) break;
            delay(20);
        } while (true);
    }

    bool as7331_ready = false;
    {
        unsigned long deadline = millis()
            + static_cast<unsigned long>(U_integrationTime) * 2 + 100;
        do {
            as7331_ready = (as7331.Get_Status() & 0x0008) != 0;
            if (as7331_ready) break;
            if (millis() >= deadline) break;
            delay(50);
        } while (true);
    }

    if (as7265x_ready && as7331_ready) {
        as7331.Get_All(&temp_ignore, &reading.raw_uva, &reading.raw_uvb, &reading.raw_uvc);
        as7265x.Get_Channel_Raw(reading.raw_spectral);
        reading.num_accumulations = 1;
        reading.spectral_peak = 0;
        for (int i = 0; i < 18; i++)
            if (reading.raw_spectral[i] > reading.spectral_peak)
                reading.spectral_peak = reading.raw_spectral[i];
        reading.isValid = true;
    } else {
        Serial.println("ERROR: sensor not ready — check I2C connections");
        reading.isValid = false;
    }

    return reading;
}

void setup() {
    Serial.begin(115200);
    delay(500);

    Serial.println();
    Serial.println("=== Thermal Characterization Utility ===");
    Serial.printf("Device: %s\n", TC_DEVICE_NAME);

    active_profile = getCalibrationProfile(TC_DEVICE_NAME);
    if (active_profile.C_p[0] == 1.0f) {
        Serial.println("WARNING: Using default (uncorrected) calibration profile.");
    } else {
        Serial.println("Calibration profile loaded.");
    }

    cam_cal_colour = &getCameraCalibration(TC_DEVICE_NAME);

    Wire.begin();
    setupTSL2591();
    setupAS7331();
    setupAS7265X();
    setupSHT4X();
    Serial.println("All sensors initialized.");

    setGain('I', TC_I_GAIN);
    setIntegrationTime('I', TC_I_TIME);
    setGain('S', TC_S_GAIN);
    setIntegrationTime('S', TC_S_TIME);
    setGain('U', TC_U_GAIN);
    setIntegrationTime('U', TC_U_TIME);

    setSpectralLeds(false);

    Serial.println();
    Serial.printf("S: gain=%-3d  time_reg=%-3d (%.0f ms)\n",
                  S_gainValue, S_integrationTime,
                  S_integrationTime * AS7265X_BASE_PERIOD_MS * AS7265X_MODE2_MULTIPLIER);
    Serial.printf("U: gain=%-4d time=%d ms\n",    U_gainValue, U_integrationTime);
    Serial.printf("I: gain=%-2d   time=%d ms\n",  I_gainValue, I_integrationTime);
    Serial.printf("Measurement interval: %d s\n",  g_interval_sec);
    Serial.println("Type HELP for runtime commands.");
    Serial.println();

    printCsvHeader();
}

void loop() {
    while (Serial.available()) {
        handleTcCommand(Serial.readStringUntil('\n'));
    }

    refreshTSL();

    FullSensorReading raw = measureQuiet();

    if (raw.isValid) {
        FullSensorReading cal = calibrateReading(
            raw, active_profile,
            S_gainValue, U_gainValue,
            S_integrationTime, U_integrationTime);

        Serial.println(readingToCsv(
            cal,
            S_gainValue, S_integrationTime,
            U_gainValue, U_integrationTime,
            I_gainValue, I_integrationTime,
            active_profile,
            nullptr,
            0,
            millis()));
    } else {
        Serial.println("ERROR: sensor read failed (check I2C connections)");
    }

    triggerSensorMeasurement = false;
    unsigned long wait_end = millis() + static_cast<unsigned long>(g_interval_sec) * 1000UL;
    while (millis() < wait_end && !triggerSensorMeasurement) {
        while (Serial.available()) {
            handleTcCommand(Serial.readStringUntil('\n'));
        }
        delay(100);
    }
    triggerSensorMeasurement = false;
}
