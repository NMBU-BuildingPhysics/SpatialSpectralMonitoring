
#include "measurement.h"
#include "sensor_init.h"
#include "globals.h"
#include "calibration.h"
#include "comms.h"
#include <cmath>

static constexpr float AS7265X_REG_TO_SEC =
    (AS7265X_BASE_PERIOD_MS * AS7265X_MODE2_MULTIPLIER) / 1000.0f;

static float get_as7265x_effective_time_sec(int register_val) {
    return static_cast<float>(register_val) * AS7265X_REG_TO_SEC;
}
static float get_as7331_time_sec(int time_ms) {
    return static_cast<float>(time_ms) / 1000.0f;
}

static int snapToPowerOfTwo(int target, int max_val) {
    if (target <= 1)       return 1;
    if (target >= max_val) return max_val;
    int lo = 1;
    while (lo * 2 <= target) lo <<= 1;
    int hi = lo << 1;
    if (hi > max_val) return lo;
    return ((target - lo) <= (hi - target)) ? lo : hi;
}
void printCsvHeader() {
    char buf[640];
    int off = 0;
    off += snprintf(buf + off, sizeof(buf) - off,
        "date,time,device,"
        "rssi,uptime_min,"
        "S_gain,S_time,U_gain,U_time,I_gain,I_time,num_accum,"
        "temperature,humidity,"
        "tsl_ch0,tsl_ch1,raw_lux,cal_lux,S_sat_pct,U_sat_pct,I_sat_pct,");
    for (int i = 0; i < 3; i++) {
        off += snprintf(buf + off, sizeof(buf) - off, "%s,", masterChannelList[i].csv_col_name);
    }
    const char* rawByNative[18] = {};
    for (size_t i = 3; i < masterChannelList.size(); i++) {
        rawByNative[masterChannelList[i].native_index] = masterChannelList[i].csv_col_name;
    }
    for (int i = 0; i < 18; i++) {
        off += snprintf(buf + off, sizeof(buf) - off, "%s,",
                        rawByNative[i] ? rawByNative[i] : "raw_unknown");
    }
    for (int i = 0; i < 3; i++) {
        char tmp[12];
        snprintf(tmp, sizeof(tmp), "cal_%s", masterChannelList[i].name);
        for (char* p = tmp + 4; *p; p++) *p = tolower((unsigned char)*p);
        off += snprintf(buf + off, sizeof(buf) - off, "%s,", tmp);
    }

    for (size_t i = 3; i < masterChannelList.size(); i++) {
        const char* sep = (i < masterChannelList.size() - 1) ? "," : "";
        off += snprintf(buf + off, sizeof(buf) - off, "cal_%dnm%s",
                        masterChannelList[i].wavelength, sep);
    }
    Serial.println(buf);
    Serial.flush();
}

String readingToCsv(
    const FullSensorReading& reading,
    int S_gain, int S_time,
    int U_gain, int U_time,
    int I_gain, int I_time,
    const CalibrationProfile& profile,
    const struct tm* timeinfo,
    int rssi,
    unsigned long uptime_ms
) {
    char buf[2400];
    int off = 0;
    if (timeinfo) {
        off += snprintf(buf + off, sizeof(buf) - off,
            "%04d%02d%02d,%02d%02d%02d,%s,",
            timeinfo->tm_year + 1900, timeinfo->tm_mon + 1, timeinfo->tm_mday,
            timeinfo->tm_hour, timeinfo->tm_min, timeinfo->tm_sec,
            deviceName.c_str());
    } else {
        off += snprintf(buf + off, sizeof(buf) - off, ",,%s,", deviceName.c_str());
    }
    off += snprintf(buf + off, sizeof(buf) - off, "%d,%lu,", rssi, uptime_ms / 60000);
    off += snprintf(buf + off, sizeof(buf) - off,
        "%d,%d,%d,%d,%d,%d,%u,",
        S_gain, S_time, U_gain, U_time, I_gain, I_time,
        reading.num_accumulations);

    off += snprintf(buf + off, sizeof(buf) - off, "%.2f,%.2f,",
        reading.temperature, reading.humidity);
    {
        uint16_t u_peak = max(reading.raw_uva, max(reading.raw_uvb, reading.raw_uvc));
        uint16_t i_peak = max(reading.tsl_ch0, reading.tsl_ch1);
        off += snprintf(buf + off, sizeof(buf) - off, "%u,%u,%.2f,%.2f,%.2f,%.2f,%.2f,",
            reading.tsl_ch0, reading.tsl_ch1, reading.raw_lux, reading.cal_lux,
            reading.spectral_peak * 100.0f / 65535.0f,
            u_peak * 100.0f / 65535.0f,
            i_peak * 100.0f / 65535.0f);
    }
    off += snprintf(buf + off, sizeof(buf) - off, "%u,%u,%u,",
        reading.raw_uvc, reading.raw_uvb, reading.raw_uva);
    for (int i = 0; i < 18; i++) {
        off += snprintf(buf + off, sizeof(buf) - off, "%u,", reading.raw_spectral[i]);
    }

    off += snprintf(buf + off, sizeof(buf) - off, "%.2f,%.2f,%.2f,",
        reading.cal_uvc, reading.cal_uvb, reading.cal_uva);
    for (int i = 0; i < 18; i++) {
        off += snprintf(buf + off, sizeof(buf) - off, "%.2f%s",
            reading.cal_spectral[i], (i < 17) ? "," : "");
    }
    return String(buf);
}

FullSensorReading measureSpectralFixed() {
    FullSensorReading reading;
    float temp_ignore;
    Serial.println("--- Starting Fixed-Settings Measurement ---");
    Serial.printf("S: gain=%d time_reg=%d | U: gain=%d time=%dms | I: gain=%d time=%dms\n",
                  S_gainValue, S_integrationTime,
                  U_gainValue, U_integrationTime,
                  I_gainValue, I_integrationTime);
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
        Serial.printf("AS7265x data-ready: %s\n", as7265x_ready ? "YES" : "TIMEOUT");
    }
    bool as7331_ready = false;
    {
        unsigned long as7331_deadline = millis()
            + static_cast<unsigned long>(U_integrationTime) * 2 + 100;
        do {
            as7331_ready = (as7331.Get_Status() & 0x0008) != 0;
            if (as7331_ready) break;
            if (millis() >= as7331_deadline) break;
            delay(50);
        } while (true);
        Serial.printf("AS7331 data-ready: %s\n", as7331_ready ? "YES" : "TIMEOUT");
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
        Serial.printf("Fixed measurement complete: peak=%u\n", reading.spectral_peak);
    } else {
        Serial.println("ERROR: Sensor data not ready after fixed integration timeout.");
        reading.isValid = false;
    }
    return reading;
}

// Goal-seeking auto-exposure: up to 3 iterations towards ~50,000 counts (45,000-55,000),
// AS7265x and AS7331 adjusted independently. The best unsaturated reading of each is kept.
FullSensorReading performGoalSeekingMeasurement() {
    static constexpr int S_GAINS[]     = {1, 16, 64};
    static constexpr int U_GAINS[]     = {64, 256, 1024};
    static constexpr int S_GAINS_N     = 3;
    static constexpr int U_GAINS_N     = 3;
    static constexpr int U_TIME_MAX_GS = 8192;
    constexpr int GS_TARGET = 50000;
    constexpr int GS_LOW    = 45000;
    constexpr int GS_HIGH   = 55000;
    int old_s_gain = S_gainValue;
    int old_u_gain = U_gainValue;
    tsl.Set_GAIN(TSL2591_GAIN_LOW);
    tsl.Set_Integration_Time(TSL2591_TIME_100MS);
    tslApplyAndFlush(100);
    I_gainValue       = 0;
    I_integrationTime = 100;
    uint16_t scout_ch0 = tsl.all_data;
    Serial.printf("--- GoalSeek scout: TSL ch0=%u ---\n", scout_ch0);
    int init_s_gain;
    if      (scout_ch0 > TSL_SCOUT_BRIGHT_THRESH)   init_s_gain = 1;
    else if (scout_ch0 > TSL_SCOUT_DAYLIGHT_THRESH) init_s_gain = 16;
    else                                             init_s_gain = 64;

    int init_u_gain;
    if      (scout_ch0 > TSL_SCOUT_BRIGHT_THRESH)   init_u_gain = 64;
    else if (scout_ch0 > TSL_SCOUT_DAYLIGHT_THRESH) init_u_gain = 256;
    else                                             init_u_gain = 1024;
    int s_gain_idx = S_GAINS_N - 1;
    for (int i = 0; i < S_GAINS_N; i++)
        if (S_GAINS[i] == init_s_gain) { s_gain_idx = i; break; }
    int u_gain_idx = U_GAINS_N - 1;
    for (int i = 0; i < U_GAINS_N; i++)
        if (U_GAINS[i] == init_u_gain) { u_gain_idx = i; break; }

    if (S_gainValue != init_s_gain) setGain('S', init_s_gain);
    if (U_gainValue != init_u_gain) setGain('U', init_u_gain);

    int start_s_time = S_integrationTime;
    if (init_s_gain < old_s_gain && old_s_gain > 0) {
        start_s_time = max(S_INT_TIME_MIN,
            static_cast<int>(S_integrationTime
                / (static_cast<float>(old_s_gain) / static_cast<float>(init_s_gain))));
    }
    start_s_time = constrain(start_s_time, S_INT_TIME_MIN, S_INT_TIME_MAX);
    int start_u_time = U_integrationTime;
    if (init_u_gain < old_u_gain && old_u_gain > 0) {
        start_u_time = max(1,
            static_cast<int>(U_integrationTime
                / (static_cast<float>(old_u_gain) / static_cast<float>(init_u_gain))));
    }
    start_u_time = snapToPowerOfTwo(constrain(start_u_time, 1, U_TIME_MAX_GS), U_TIME_MAX_GS);
    setIntegrationTime('S', start_s_time);
    setIntegrationTime('U', start_u_time);
    Serial.printf("--- GoalSeek start: S gain=%d time_reg=%d | U gain=%d time=%dms ---\n",
                  S_gainValue, S_integrationTime, U_gainValue, U_integrationTime);
    FullSensorReading reading;
    reading.num_accumulations = 1;
    reading.isValid           = false;

    // Best unsaturated reading per sensor across all iterations
    struct { uint16_t ch[18]; uint16_t peak; int gain, time_reg; bool valid; } bestS = {};
    struct { uint16_t uva, uvb, uvc, peak; int gain, time_ms; bool valid; } bestU = {};
    for (int iter = 0; iter < 3; iter++) {
        Serial.printf("GoalSeek [%d/3]: S gain=%d time_reg=%d (%.0fms) | U gain=%d time=%dms\n",
                      iter + 1,
                      S_gainValue, S_integrationTime,
                      S_integrationTime * AS7265X_BASE_PERIOD_MS * AS7265X_MODE2_MULTIPLIER,
                      U_gainValue, U_integrationTime);

        unsigned long s_period_ms = static_cast<unsigned long>(
            S_integrationTime * AS7265X_BASE_PERIOD_MS * AS7265X_MODE2_MULTIPLIER);
        bool s_ready = false;
        delay(s_period_ms);
        maintainMqtt();
        unsigned long s_deadline = millis() + s_period_ms + 100;
        do {
            s_ready = as7265x.Get_DataStatus();
            if (s_ready) break;
            if (millis() >= s_deadline) break;
            delay(20);
        } while (true);
        bool u_ready = false;
        unsigned long u_deadline = millis()
            + static_cast<unsigned long>(U_integrationTime) * 2 + 100;
        do {
            maintainMqtt();
            u_ready = (as7331.Get_Status() & 0x0008) != 0;
            if (u_ready) break;
            if (millis() >= u_deadline) break;
            delay(10);
        } while (true);
        Serial.printf("  AS7265x: %s | AS7331: %s\n",
                      s_ready ? "READY" : "TIMEOUT",
                      u_ready ? "READY" : "TIMEOUT");
        if (!s_ready && !u_ready) {
            Serial.println("  GoalSeek: both sensors timed out — aborting.");
            return reading;
        }

        uint16_t raw_spectral[18] = {0};
        uint16_t raw_uva = 0, raw_uvb = 0, raw_uvc = 0;
        float    tmp_uv;
        if (s_ready) as7265x.Get_Channel_Raw(raw_spectral);
        if (u_ready) as7331.Get_All(&tmp_uv, &raw_uva, &raw_uvb, &raw_uvc);
        uint16_t max_S = 0;
        for (int i = 0; i < 18; i++)
            if (raw_spectral[i] > max_S) max_S = raw_spectral[i];
        uint16_t max_U = max(raw_uva, max(raw_uvb, raw_uvc));
        bool s_saturated = (max_S >= 65535);
        bool u_saturated = (max_U >= 65535);
        Serial.printf("  max_S=%u%s  max_U=%u%s  target=[%d, %d]\n",
                      max_S, s_saturated ? " SAT" : "",
                      max_U, u_saturated ? " SAT" : "",
                      GS_LOW, GS_HIGH);
        Serial.printf("  [iter%d raw] S_gain=%d S_time=%d | U_gain=%d U_time=%d"
                      " | raw_uvc=%u raw_uvb=%u raw_uva=%u"
                      " | spec_peak=%u (ch0=%u ch1=%u ... ch17=%u)\n",
                      iter + 1,
                      S_gainValue, S_integrationTime,
                      U_gainValue, U_integrationTime,
                      raw_uvc, raw_uvb, raw_uva,
                      max_S, raw_spectral[0], raw_spectral[1], raw_spectral[17]);
        for (int i = 0; i < 18; i++) reading.raw_spectral[i] = raw_spectral[i];
        reading.raw_uva       = raw_uva;
        reading.raw_uvb       = raw_uvb;
        reading.raw_uvc       = raw_uvc;
        reading.spectral_peak = max_S;
        reading.isValid       = s_ready || u_ready;

        if (!s_saturated && s_ready && max_S > bestS.peak) {
            for (int i = 0; i < 18; i++) bestS.ch[i] = raw_spectral[i];
            bestS.peak     = max_S;
            bestS.gain     = S_gainValue;
            bestS.time_reg = S_integrationTime;
            bestS.valid    = true;
            Serial.printf("  Best-S updated: peak=%u @ gain=%d time_reg=%d\n",
                          bestS.peak, bestS.gain, bestS.time_reg);
        }
        if (!u_saturated && u_ready && max_U > bestU.peak) {
            bestU.uva     = raw_uva;
            bestU.uvb     = raw_uvb;
            bestU.uvc     = raw_uvc;
            bestU.peak    = max_U;
            bestU.gain    = U_gainValue;
            bestU.time_ms = U_integrationTime;
            bestU.valid   = true;
            Serial.printf("  Best-U updated: peak=%u @ gain=%d time=%dms\n",
                          bestU.peak, bestU.gain, bestU.time_ms);
        }
        bool s_at_ceiling = (s_gain_idx == S_GAINS_N - 1 && S_integrationTime == S_INT_TIME_MAX);
        bool u_at_ceiling = (u_gain_idx == U_GAINS_N - 1 && U_integrationTime == U_TIME_MAX_GS);
        bool s_at_floor   = (s_gain_idx == 0 && S_integrationTime == S_INT_TIME_MIN);
        bool u_at_floor   = (u_gain_idx == 0 && U_integrationTime == 1);

        bool u_quant_limit = !u_saturated && max_U > 0
            && max_U < static_cast<uint16_t>(GS_LOW)
            && static_cast<uint32_t>(max_U) * 2 > 62000;

        bool s_optimal = !s_saturated
                      && ((max_S >= GS_LOW && max_S <= GS_HIGH)
                       || (max_S  < GS_LOW  && s_at_ceiling)
                       || (max_S  > GS_HIGH && s_at_floor));
        bool u_optimal = !u_saturated
                      && ((max_U >= GS_LOW && max_U <= GS_HIGH)
                       || (max_U  < GS_LOW  && (u_at_ceiling || u_quant_limit))
                       || (max_U  > GS_HIGH && u_at_floor));

        if (u_quant_limit)
            Serial.printf("  UV quant-limit: peak=%u, 2× would project %lu > 62000\n",
                          max_U, static_cast<unsigned long>(max_U) * 2);
        if (s_optimal && u_optimal) {
            Serial.printf("  GoalSeek converged on iteration %d.\n", iter + 1);
            break;
        }

        if (iter == 2) {
            if (!s_saturated && !u_saturated) {
                Serial.println("  GoalSeek: max iterations reached — using last reading.");
                break;
            }
            Serial.println("  GoalSeek: saturated on final iter — applying emergency step-down.");
        }
        if (!s_optimal && s_ready) {
            float ideal_S = s_saturated
                ? static_cast<float>(S_integrationTime) / 4.0f
                : (max_S > 0
                    ? static_cast<float>(S_integrationTime) * (GS_TARGET / static_cast<float>(max_S))
                    : static_cast<float>(S_INT_TIME_MAX));
            int new_s_idx = s_gain_idx;
            if (ideal_S > static_cast<float>(S_INT_TIME_MAX) && new_s_idx < S_GAINS_N - 1) {
                float ratio = static_cast<float>(S_GAINS[new_s_idx + 1])
                            / static_cast<float>(S_GAINS[new_s_idx]);
                ideal_S /= ratio;
                new_s_idx++;
            } else if (ideal_S < 1.0f && new_s_idx > 0) {
                float ratio = static_cast<float>(S_GAINS[new_s_idx])
                            / static_cast<float>(S_GAINS[new_s_idx - 1]);
                ideal_S *= ratio;
                new_s_idx--;
            }
            int new_s_time = constrain(static_cast<int>(roundf(ideal_S)),
                                       S_INT_TIME_MIN, S_INT_TIME_MAX);
            Serial.printf("  S adjust: gain %d→%d, time_reg %d→%d\n",
                          S_GAINS[s_gain_idx], S_GAINS[new_s_idx],
                          S_integrationTime, new_s_time);
            if (new_s_idx != s_gain_idx) {
                setGain('S', S_GAINS[new_s_idx]);
                s_gain_idx = new_s_idx;
            }
            setIntegrationTime('S', new_s_time);
        }

        if (!u_optimal && u_ready) {
            float ideal_U = (max_U > 0)
                ? (u_saturated
                    ? static_cast<float>(U_integrationTime) / 4.0f
                    : static_cast<float>(U_integrationTime) * (GS_TARGET / static_cast<float>(max_U)))
                : static_cast<float>(U_TIME_MAX_GS);

            int new_u_idx = u_gain_idx;
            if (ideal_U > static_cast<float>(U_TIME_MAX_GS) && new_u_idx < U_GAINS_N - 1) {
                float ratio = static_cast<float>(U_GAINS[new_u_idx + 1])
                            / static_cast<float>(U_GAINS[new_u_idx]);
                ideal_U /= ratio;
                new_u_idx++;
            } else if (ideal_U < 1.0f && new_u_idx > 0) {
                float ratio = static_cast<float>(U_GAINS[new_u_idx])
                            / static_cast<float>(U_GAINS[new_u_idx - 1]);
                ideal_U *= ratio;
                new_u_idx--;
            }
            int new_u_time = snapToPowerOfTwo(
                constrain(static_cast<int>(roundf(ideal_U)), 1, U_TIME_MAX_GS),
                U_TIME_MAX_GS);
            if (new_u_time == U_integrationTime) {
                if (max_U < static_cast<uint16_t>(GS_LOW) && new_u_time < U_TIME_MAX_GS
                    && static_cast<uint32_t>(max_U) * 2 <= 62000)
                    new_u_time = min(U_integrationTime * 2, U_TIME_MAX_GS);
                else if (max_U > static_cast<uint16_t>(GS_HIGH) && new_u_time > 1)
                    new_u_time = max(U_integrationTime / 2, 1);
            }
            Serial.printf("  U adjust: gain %d→%d, time %d→%dms\n",
                          U_GAINS[u_gain_idx], U_GAINS[new_u_idx],
                          U_integrationTime, new_u_time);
            if (new_u_idx != u_gain_idx) {
                setGain('U', U_GAINS[new_u_idx]);
                u_gain_idx = new_u_idx;
            }
            setIntegrationTime('U', new_u_time);
        }
    }

    // Still saturated after the loop: halve integration times up to 4 times
    {
        auto isAnySaturated = [&]() -> bool {
            if (reading.raw_uva == 65535 || reading.raw_uvb == 65535 ||
                reading.raw_uvc == 65535) return true;
            for (int i = 0; i < 18; i++)
                if (reading.raw_spectral[i] == 65535) return true;
            return false;
        };
        for (int safety = 0; isAnySaturated() && safety < 4; safety++) {
            Serial.printf("  SafetyNet [%d/4]: halving times \xe2\x80\x94 S_time %d\xe2\x86\x92%d, U_time %d\xe2\x86\x92%dms\n",
                          safety + 1,
                          S_integrationTime, max(S_integrationTime / 2, S_INT_TIME_MIN),
                          U_integrationTime, snapToPowerOfTwo(max(U_integrationTime / 2, 1), U_TIME_MAX_GS));
            bool s_still_sat = false;
            for (int i = 0; i < 18; i++)
                if (reading.raw_spectral[i] == 65535) { s_still_sat = true; break; }
            bool u_still_sat = (reading.raw_uva == 65535 || reading.raw_uvb == 65535 ||
                                reading.raw_uvc == 65535);
            if (s_still_sat) {
                int new_t = max(S_integrationTime / 2, S_INT_TIME_MIN);
                setIntegrationTime('S', new_t);
            }
            if (u_still_sat) {
                int new_t = snapToPowerOfTwo(max(U_integrationTime / 2, 1), U_TIME_MAX_GS);
                setIntegrationTime('U', new_t);
            }

            bool s_rdy = false, u_rdy = false;
            unsigned long s_ms = static_cast<unsigned long>(
                S_integrationTime * AS7265X_BASE_PERIOD_MS * AS7265X_MODE2_MULTIPLIER);
            delay(s_ms);
            maintainMqtt();
            unsigned long s_dl = millis() + s_ms + 100;
            do {
                s_rdy = as7265x.Get_DataStatus();
                if (s_rdy) break;
                if (millis() >= s_dl) break;
                delay(20);
            } while (true);
            unsigned long u_dl = millis() +
                static_cast<unsigned long>(U_integrationTime) * 2 + 100;
            do {
                maintainMqtt();
                u_rdy = (as7331.Get_Status() & 0x0008) != 0;
                if (u_rdy) break;
                if (millis() >= u_dl) break;
                delay(10);
            } while (true);
            if (!s_rdy && !u_rdy) {
                Serial.println("  SafetyNet: both sensors timed out \xe2\x80\x94 stopping.");
                break;
            }
            float tmp_uv2;
            uint16_t new_spectral[18] = {0};
            uint16_t new_uva = 0, new_uvb = 0, new_uvc = 0;
            if (s_rdy) as7265x.Get_Channel_Raw(new_spectral);
            if (u_rdy) as7331.Get_All(&tmp_uv2, &new_uva, &new_uvb, &new_uvc);
            for (int i = 0; i < 18; i++) reading.raw_spectral[i] = new_spectral[i];
            reading.raw_uva = new_uva;
            reading.raw_uvb = new_uvb;
            reading.raw_uvc = new_uvc;
            reading.isValid = s_rdy || u_rdy;
            reading.spectral_peak = 0;
            for (int i = 0; i < 18; i++)
                if (new_spectral[i] > reading.spectral_peak)
                    reading.spectral_peak = new_spectral[i];
            uint16_t sn_max_U = max(new_uva, max(new_uvb, new_uvc));
            Serial.printf("  SafetyNet result: S_peak=%u  max_U=%u%s%s\n",
                          reading.spectral_peak, sn_max_U,
                          reading.spectral_peak == 65535 ? " S_SAT" : "",
                          sn_max_U == 65535 ? " U_SAT" : "");
            bool sn_s_sat = (reading.spectral_peak == 65535);
            bool sn_u_sat = (sn_max_U == 65535);
            if (!sn_s_sat && s_rdy && reading.spectral_peak > bestS.peak) {
                for (int i = 0; i < 18; i++) bestS.ch[i] = new_spectral[i];
                bestS.peak     = reading.spectral_peak;
                bestS.gain     = S_gainValue;
                bestS.time_reg = S_integrationTime;
                bestS.valid    = true;
            }
            if (!sn_u_sat && u_rdy && sn_max_U > bestU.peak) {
                bestU.uva     = new_uva;
                bestU.uvb     = new_uvb;
                bestU.uvc     = new_uvc;
                bestU.peak    = sn_max_U;
                bestU.gain    = U_gainValue;
                bestU.time_ms = U_integrationTime;
                bestU.valid   = true;
            }
        }
    }
    Serial.println("  Merge:");
    if (bestS.valid) {
        for (int i = 0; i < 18; i++) reading.raw_spectral[i] = bestS.ch[i];
        S_gainValue       = bestS.gain;
        S_integrationTime = bestS.time_reg;
        Serial.printf("    S: best-fit peak=%u @ gain=%d time_reg=%d\n",
                      bestS.peak, bestS.gain, bestS.time_reg);
    } else {
        Serial.println("    S: no clean reading — last used (may be saturated)");
    }
    if (bestU.valid) {
        reading.raw_uva   = bestU.uva;
        reading.raw_uvb   = bestU.uvb;
        reading.raw_uvc   = bestU.uvc;
        U_gainValue       = bestU.gain;
        U_integrationTime = bestU.time_ms;
        Serial.printf("    U: best-fit peak=%u @ gain=%d time=%dms\n",
                      bestU.peak, bestU.gain, bestU.time_ms);
    } else {
        Serial.println("    U: no clean reading — last used (may be saturated)");
    }
    reading.spectral_peak = 0;
    for (int i = 0; i < 18; i++)
        if (reading.raw_spectral[i] > reading.spectral_peak)
            reading.spectral_peak = reading.raw_spectral[i];
    // Low light: sum frames at max integration time until the next frame would clip
    reading.num_accumulations = 1;
    if (S_integrationTime == S_INT_TIME_MAX
        && reading.spectral_peak < static_cast<uint16_t>(GS_LOW))
    {
        Serial.printf("  Accumulation: peak=%u below target, collecting up to %d frames\n",
                      reading.spectral_peak, S_MAX_ACCUMULATIONS);
        for (int n = 1; n < S_MAX_ACCUMULATIONS; n++) {
            unsigned long period_ms = static_cast<unsigned long>(
                S_integrationTime * AS7265X_BASE_PERIOD_MS * AS7265X_MODE2_MULTIPLIER);
            delay(period_ms);
            unsigned long deadline = millis() + period_ms + 100;
            bool rdy = false;
            do {
                rdy = as7265x.Get_DataStatus();
                if (rdy) break;
                if (millis() >= deadline) break;
                delay(20);
            } while (true);
            if (!rdy) {
                Serial.printf("  Accumulation frame %d: timeout — stopping.\n", n + 1);
                break;
            }
            uint16_t frame[18] = {0};
            as7265x.Get_Channel_Raw(frame);
            uint16_t frame_peak = 0;
            for (int i = 0; i < 18; i++)
                if (frame[i] > frame_peak) frame_peak = frame[i];

            uint32_t predicted_peak = 0;
            for (int i = 0; i < 18; i++) {
                uint32_t predicted_sum = static_cast<uint32_t>(reading.raw_spectral[i]) + frame[i];
                if (predicted_sum > predicted_peak) predicted_peak = predicted_sum;
            }
            if (predicted_peak >= 65535u) {
                Serial.printf("  Accumulation: predicted_peak=%lu would clip — rejecting frame %d, stopping.\n",
                              static_cast<unsigned long>(predicted_peak), n + 1);
                break;
            }
            for (int i = 0; i < 18; i++) {
                reading.raw_spectral[i] = static_cast<uint16_t>(
                    static_cast<uint32_t>(reading.raw_spectral[i]) + frame[i]);
            }
            reading.num_accumulations = static_cast<uint8_t>(n + 1);
            reading.spectral_peak = 0;
            for (int i = 0; i < 18; i++)
                if (reading.raw_spectral[i] > reading.spectral_peak)
                    reading.spectral_peak = reading.raw_spectral[i];
            Serial.printf("  Accumulation frame %d: frame_peak=%u  accum_peak=%u\n",
                          n + 1, frame_peak, reading.spectral_peak);
        }
        Serial.printf("  Accumulation complete: %d frames, final peak=%u\n",
                      reading.num_accumulations, reading.spectral_peak);
    }
    if (!sht.Measure(&reading.temperature, &reading.humidity, SHT4X_REG_MEASURE_HIGH)) {
        Serial.println("WARNING: SHT4X read failed in GoalSeek — using defaults.");
        reading.temperature = 25000.0f;
        reading.humidity    = 50000.0f;
    }
    reading.temperature /= 1000.0f;
    reading.humidity    /= 1000.0f;

    {
        static constexpr float GAIN_MULTS[] = {1.0f, 25.0f, 428.0f, 9876.0f};
        static constexpr int   GAIN_VALS[]  = {0, 1, 2, 3};
        int gi = 3;
        if      (scout_ch0 > TSL_SCOUT_BRIGHT_THRESH)   gi = 0;
        else if (scout_ch0 > TSL_SCOUT_DAYLIGHT_THRESH) gi = 1;
        else if (scout_ch0 > TSL_SCOUT_DIM_THRESH)      gi = 2;
        int final_time_ms = 600;
        if (scout_ch0 > 0) {
            float est = static_cast<float>(scout_ch0) * GAIN_MULTS[gi];
            float t_ms = 100.0f * (TSL_TARGET_COUNTS / est);
            final_time_ms = static_cast<int>(roundf(t_ms / 100.0f)) * 100;
            final_time_ms = constrain(final_time_ms, 100, 600);
        }
        setGain('I', GAIN_VALS[gi]);
        setIntegrationTime('I', final_time_ms);
        while ((tsl.all_data >= 65535 || tsl.ir_data >= 65535) && I_gainValue > 0) {
            setGain('I', I_gainValue - 1);
            tsl.Get_ALS();
            Serial.printf("  TSL sat step-down: gain→%d ch0=%u\n", I_gainValue, tsl.all_data);
        }
        reading.tsl_ch0 = tsl.all_data;
        reading.tsl_ch1 = tsl.ir_data;
        reading.raw_lux = tsl.lux_data;
        Serial.printf("  TSL post-seek: gi=%d gain=%d time=%dms ch0=%u ch1=%u\n",
                      gi, GAIN_VALS[gi], final_time_ms, reading.tsl_ch0, reading.tsl_ch1);
    }
    reading.spectral_peak = 0;
    for (int i = 0; i < 18; i++)
        if (reading.raw_spectral[i] > reading.spectral_peak)
            reading.spectral_peak = reading.raw_spectral[i];
    Serial.printf("--- GoalSeek complete: peak=%u (%.1f%% FS), "
                  "S gain=%d time_reg=%d | U gain=%d time=%dms ---\n",
                  reading.spectral_peak,
                  100.0f * reading.spectral_peak / 65535.0f,
                  S_gainValue, S_integrationTime,
                  U_gainValue, U_integrationTime);
    return reading;
}

FullSensorReading performCalibrationCapture(
    bool isDark,
    int& out_s_gain, int& out_s_time,
    int& out_u_gain, int& out_u_time,
    int& out_i_gain, int& out_i_time)
{
    const int saved_s_gain = S_gainValue;
    const int saved_s_time = S_integrationTime;
    const int saved_u_gain = U_gainValue;
    const int saved_u_time = U_integrationTime;
    const int saved_i_gain = I_gainValue;
    const int saved_i_time = I_integrationTime;
    if (isDark) {
        setGain('I', 3);
        setIntegrationTime('I', 600);
        setGain('S', 64);
        setIntegrationTime('S', 255);
        setGain('U', 2048);
        setIntegrationTime('U', 16384);
    } else {
        setGain('I', DEFAULT_I_GAIN);
        setIntegrationTime('I', DEFAULT_I_INT_TIME);
        setGain('S', DEFAULT_S_GAIN);
        setIntegrationTime('S', DEFAULT_S_INT_TIME);
        setGain('U', DEFAULT_U_GAIN);
        setIntegrationTime('U', DEFAULT_U_INT_TIME);
    }
    out_s_gain = S_gainValue;
    out_s_time = S_integrationTime;
    out_u_gain = U_gainValue;
    out_u_time = U_integrationTime;
    out_i_gain = I_gainValue;
    out_i_time = I_integrationTime;
    FullSensorReading result = measureSpectralFixed();

    setGain('I', saved_i_gain);
    setIntegrationTime('I', saved_i_time);
    setGain('S', saved_s_gain);
    setIntegrationTime('S', saved_s_time);
    setGain('U', saved_u_gain);
    setIntegrationTime('U', saved_u_time);
    return result;
}
FullSensorReading calibrateReading(
    const FullSensorReading& reading,
    const CalibrationProfile& profile,
    int s_gain, int u_gain,
    int s_time_reg_val, int u_time_ms
) {
    FullSensorReading result = reading;
    const float T = reading.temperature;

    {
        static constexpr float GAIN_MULTS[] = {1.0f, 25.0f, 428.0f, 9876.0f};
        float gain_mult = (I_gainValue >= 0 && I_gainValue <= 3) ? GAIN_MULTS[I_gainValue] : 1.0f;
        float cpl = (static_cast<float>(I_integrationTime) * gain_mult) / 408.0f;  // TSL2591 lux formula
        float raw_lux = 0.0f;
        if (cpl > 0.0f && reading.tsl_ch0 > reading.tsl_ch1 && reading.tsl_ch0 > 0) {
            raw_lux = (static_cast<float>(reading.tsl_ch0 - reading.tsl_ch1)
                       * (1.0f - static_cast<float>(reading.tsl_ch1) / static_cast<float>(reading.tsl_ch0)))
                      / cpl;
        }
        const TempCoeffSet& lux_tc = getLuxTempCoefficients();
        float lux_temp_factor = (lux_tc.a * T * T) + (lux_tc.b * T) + lux_tc.c;
        if (fabsf(lux_temp_factor) < 1e-6f) lux_temp_factor = 1.0f;
        result.cal_lux = (raw_lux / lux_temp_factor) * profile.lux_factor;
    }
    const uint16_t raw_uv[] = {reading.raw_uva, reading.raw_uvb, reading.raw_uvc};
    const float u_time_sec = get_as7331_time_sec(u_time_ms);
    const float s_time_sec = get_as7265x_effective_time_sec(s_time_reg_val);
    for (size_t i = 0; i < masterChannelList.size(); ++i) {
        const ChannelInfo& ch = masterChannelList[i];

        const bool is_uv = (strncmp(ch.name, "UV", 2) == 0);
        const uint16_t S_light = is_uv ? raw_uv[ch.native_index]
                                       : reading.raw_spectral[ch.native_index];
        const float t_int = is_uv ? u_time_sec : s_time_sec;
        const int   G     = is_uv ? u_gain     : s_gain;
        const float S_dark = profile.S_p_dark[i];
        const float C_p    = profile.C_p[i];
        const TempCoeffSet& tc = getTempCoefficients(ch.name);
        float f_T = (tc.a * T * T) + (tc.b * T) + tc.c;
        if (fabsf(f_T) < 1e-6f) f_T = 1.0f;

        float net = 0.0f;
        if (t_int > 0.0f && G > 0) {
            float light_norm = static_cast<float>(S_light) / (f_T * t_int * static_cast<float>(G));
            float dark_norm  = S_dark / f_T;  // dark counts are stored normalised by gain x time
            net = light_norm - dark_norm;
        }
        float irradiance = (C_p > 0.0f && net > 0.0f) ? C_p * net : 0.0f;
        if (is_uv) {
            if      (strcmp(ch.name, "UVA") == 0) result.cal_uva = irradiance;
            else if (strcmp(ch.name, "UVB") == 0) result.cal_uvb = irradiance;
            else if (strcmp(ch.name, "UVC") == 0) result.cal_uvc = irradiance;
        } else {
            result.cal_spectral[i - 3] = irradiance;
        }
    }
    return result;
}
void setSpectralLeds(bool on) {
    if (on) {
        as7265x.Set_LED(AS7265X_SELECT_AS72651,
            AS7265X_LED_IND_ENABLE | AS7265X_LED_DRV_ENABLE | AS7265X_LED_DRV_100MA);
        as7265x.Set_LED(AS7265X_SELECT_AS72652,
            AS7265X_LED_IND_ENABLE | AS7265X_LED_DRV_ENABLE);
        as7265x.Set_LED(AS7265X_SELECT_AS72653,
            AS7265X_LED_IND_ENABLE | AS7265X_LED_DRV_ENABLE);
    } else {
        as7265x.Set_LED(AS7265X_SELECT_AS72651,
            AS7265X_LED_IND_DISABLE | AS7265X_LED_DRV_DISABLE);
        as7265x.Set_LED(AS7265X_SELECT_AS72652,
            AS7265X_LED_IND_DISABLE | AS7265X_LED_DRV_DISABLE);
        as7265x.Set_LED(AS7265X_SELECT_AS72653,
            AS7265X_LED_IND_DISABLE | AS7265X_LED_DRV_DISABLE);
    }
}
void setGain(char sensorType, int gainValue) {
    switch (sensorType) {
        case 'S': {
            struct { int val; uint8_t reg; } static constexpr s_gains[] = {
                {1, AS7265X_GAIN_1X}, {4, AS7265X_GAIN_3_7X},
                {16, AS7265X_GAIN_16X}, {64, AS7265X_GAIN_64X}
            };
            for (const auto& g : s_gains) {
                if (g.val == gainValue) {
                    as7265x.Set_Gain(g.reg);
                    S_gainValue = gainValue;
                    return;
                }
            }
            return;
        }
        case 'U': {
            if (gainValue < 1 || gainValue > 2048 || (gainValue & (gainValue - 1)) != 0) {
                return;
            }
            int log2g = 0;
            for (int v = gainValue; v > 1; v >>= 1) log2g++;
            uint8_t reg = 0xb0 - (log2g * 0x10);  // 2048x = 0x00 ... 1x = 0xb0
            as7331.Set_Device_State(AS7331_STATE_CONFIGURATION);
            as7331.Set_GAIN(reg);
            U_gainValue = gainValue;
            as7331.Set_Device_State(AS7331_STATE_MEASUREMENT);
            as7331.Set_Measurement(AS7331_MEASUREMENT_START);
            return;
        }
        case 'I': {
            struct { int val; uint8_t reg; } static constexpr i_gains[] = {
                {0, TSL2591_GAIN_LOW}, {1, TSL2591_GAIN_MED},
                {2, TSL2591_GAIN_HIGH}, {3, TSL2591_GAIN_MAX}
            };
            for (const auto& g : i_gains) {
                if (g.val == gainValue) {
                    tsl.Set_GAIN(g.reg);
                    I_gainValue = gainValue;
                    tsl.Disable();
                    delay(10);
                    tsl.Enable();
                    delay(I_integrationTime + 50);
                    tsl.Get_ALS();
                    return;
                }
            }
            return;
        }
        default:
            Serial.println("Unknown sensor type for GAIN.");
    }
}
void setIntegrationTime(char sensorType, int integrationTime) {
    switch (sensorType) {
        case 'S': {
            if (integrationTime < S_INT_TIME_MIN || integrationTime > S_INT_TIME_MAX) {
                return;
            }
            as7265x.Set_Integration(integrationTime);
            S_integrationTime = integrationTime;
            return;
        }
        case 'U': {
            if (integrationTime < 1 || integrationTime > 16384
                || (integrationTime & (integrationTime - 1)) != 0) {
                return;
            }
            int log2t = 0;
            for (int v = integrationTime; v > 1; v >>= 1) log2t++;
            as7331.Set_Device_State(AS7331_STATE_CONFIGURATION);
            as7331.Set_Integration_Time(static_cast<uint8_t>(log2t));
            U_integrationTime = integrationTime;
            as7331.Set_Device_State(AS7331_STATE_MEASUREMENT);
            as7331.Set_Measurement(AS7331_MEASUREMENT_START);
            return;
        }
        case 'I': {
            if (integrationTime < 100 || integrationTime > 600 || integrationTime % 100 != 0) {
                return;
            }
            tsl.Set_Integration_Time(static_cast<uint8_t>((integrationTime / 100) - 1));
            I_integrationTime = integrationTime;
            tsl.Disable();
            delay(10);
            tsl.Enable();
            delay(integrationTime + 50);
            tsl.Get_ALS();
            Serial.printf("Illuminance integration time: %d ms\n", integrationTime);
            return;
        }
        default:
            Serial.println("Unknown sensor type for TIME.");
    }
}
