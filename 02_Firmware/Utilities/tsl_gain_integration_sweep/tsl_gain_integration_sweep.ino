/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* TSL2591 gain x integration time sweep (4 gains x 6 times per cycle).
* Logs raw channels, lux and saturation flags as CSV.
*/

#include <Wire.h>
#include "src/sensors/TSL2591.h"
#include "src/sensors/SHT4X.h"

const char* deviceName = "tsl_sweep";

const float SWEEP_INTERVAL_MINUTES = 10.0f;

struct GainEntry { int code; uint8_t reg; const char* name; float nominal; };
static constexpr GainEntry GAINS[] = {
    { 0, TSL2591_GAIN_LOW,  "LOW",  1.0f     },
    { 1, TSL2591_GAIN_MED,  "MED",  25.0f    },
    { 2, TSL2591_GAIN_HIGH, "HIGH", 428.0f   },
    { 3, TSL2591_GAIN_MAX,  "MAX",  9876.0f  },
};
static constexpr int N_GAINS = sizeof(GAINS) / sizeof(GAINS[0]);

struct TimeEntry { int ms; uint8_t reg; };
static constexpr TimeEntry TIMES[] = {
    { 100, TSL2591_TIME_100MS },
    { 200, TSL2591_TIME_200MS },
    { 300, TSL2591_TIME_300MS },
    { 400, TSL2591_TIME_400MS },
    { 500, TSL2591_TIME_500MS },
    { 600, TSL2591_TIME_600MS },
};
static constexpr int N_TIMES = sizeof(TIMES) / sizeof(TIMES[0]);

static constexpr uint16_t TSL_SATURATED = 65535;

TSL2591    tsl;
SHT4X      sht;

float      sweepIntervalMin = SWEEP_INTERVAL_MINUTES;
unsigned long lastSweepMs   = 0;
volatile bool triggerSweep  = false;

static char csvBuffer[4096];

static bool readOneBracket(
    const GainEntry& g, const TimeEntry& t,
    uint16_t& ch0, uint16_t& ch1, uint16_t& vis, float& lux,
    bool& sat_ch0, bool& sat_ch1)
{
    tsl.Set_GAIN(g.reg);
    tsl.Set_Integration_Time(t.reg);
    tsl.Disable();
    delay(10);
    tsl.Enable();

    delay(t.ms + 50);
    tsl.Get_ALS();

    ch0 = tsl.all_data;
    ch1 = tsl.ir_data;
    vis = tsl.visible_data;

    sat_ch0 = (ch0 >= TSL_SATURATED);
    sat_ch1 = (ch1 >= TSL_SATURATED);

    if (sat_ch0 || ch0 == 0) {
        lux = -1.0f;
    } else {
        lux = tsl.lux_data;
    }

    return true;
}

void performSweep() {
    unsigned long t0_ms = millis();
    char timestamp[20];
    snprintf(timestamp, sizeof(timestamp), "%lums", t0_ms);

    Serial.printf("\n=== TSL2591 sweep start (t=%lums) ===\n", t0_ms);

    float temperature = 0.0f, humidity = 0.0f;
    if (sht.Measure(&temperature, &humidity, SHT4X_REG_MEASURE_HIGH)) {
        temperature /= 1000.0f;
        humidity    /= 1000.0f;
    } else {
        Serial.println("WARNING: SHT4X read failed — using 0.0 for T/RH.");
    }
    Serial.printf("  T=%.2f °C  RH=%.1f %%\n", temperature, humidity);

    int off = 0;
    off += snprintf(csvBuffer + off, sizeof(csvBuffer) - off,
        "sweep_id,timestamp,temperature_C,humidity_pct,"
        "gain_code,gain_name,gain_nominal_x,int_time_ms,"
        "ch0_all,ch1_ir,ch0_visible,lux,sat_ch0,sat_ch1\n");

    for (int gi = 0; gi < N_GAINS; gi++) {
        const GainEntry& g = GAINS[gi];
        for (int ti = 0; ti < N_TIMES; ti++) {
            const TimeEntry& t = TIMES[ti];

            uint16_t ch0 = 0, ch1 = 0, vis = 0;
            float    lux = 0.0f;
            bool     sat0 = false, sat1 = false;

            readOneBracket(g, t, ch0, ch1, vis, lux, sat0, sat1);

            Serial.printf("  gain=%-4s (%4.0fx)  t=%3d ms  "
                          "ch0=%5u  ch1=%5u  vis=%5u  lux=%8.2f%s%s\n",
                          g.name, g.nominal, t.ms,
                          ch0, ch1, vis, lux,
                          sat0 ? "  SAT_CH0" : "",
                          sat1 ? "  SAT_CH1" : "");

            off += snprintf(csvBuffer + off, sizeof(csvBuffer) - off,
                "%s,%s,%.2f,%.1f,"
                "%d,%s,%.0f,%d,"
                "%u,%u,%u,%.4f,%d,%d\n",
                timestamp, timestamp,
                temperature, humidity,
                g.code, g.name, g.nominal, t.ms,
                ch0, ch1, vis,
                (sat0 || (ch0 == 0)) ? -1.0f : lux,
                (int)sat0, (int)sat1);

            if (off > (int)sizeof(csvBuffer) - 200) {
                Serial.println("WARNING: CSV buffer near full — truncating.");
                break;
            }
        }
    }

    Serial.println("=== Sweep complete ===");

    Serial.println(csvBuffer);
}

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.printf("\n\n=== TSL2591 Gain/Integration Sweep ===\n");
    Serial.printf("Sweep interval: %.2f min\n", sweepIntervalMin);
    Wire.begin();

    if (!tsl.begin()) {
        Serial.println("FATAL: TSL2591 not found on I2C bus. Check wiring.");
        while (true) { delay(1000); }
    }
    tsl.Enable();
    Serial.println("TSL2591 initialised.");

    if (!sht.begin()) {
        Serial.println("WARNING: SHT4X not found. Temperature/humidity will be 0.");
    } else {
        Serial.println("SHT4X initialised.");
    }

    Serial.printf("\nReady. Sweeping all %d gain × %d time = %d combinations.\n",
                  N_GAINS, N_TIMES, N_GAINS * N_TIMES);
    Serial.println("Type 'SENS' or 'SWEEP' followed by newline to trigger a run.");
}

void loop() {
    static String serialLine;
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (serialLine.length() > 0) {
                String cmd = serialLine;
                cmd.trim();
                cmd.toUpperCase();
                if (cmd.startsWith("SENS") || cmd.startsWith("SWEEP")) {
                    triggerSweep = true;
                    Serial.println("[CMD] Sweep triggered.");
                } else {
                    Serial.printf("[CMD] Unknown: '%s'\n", cmd.c_str());
                }
                serialLine = "";
            }
        } else {
            serialLine += c;
        }
    }

    unsigned long now = millis();
    unsigned long interval_ms = (unsigned long)(sweepIntervalMin * 60.0f * 1000.0f);
    bool isScheduled = (now - lastSweepMs >= interval_ms);

    if (isScheduled || triggerSweep) {
        lastSweepMs = now;
        if (triggerSweep) {
            Serial.println("--- On-demand sweep ---");
        } else {
            Serial.printf("--- Scheduled sweep (t=%lums) ---\n", now);
        }
        triggerSweep = false;
        performSweep();
    }

    delay(50);
}
