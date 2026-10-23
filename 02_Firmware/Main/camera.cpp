/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* OV5640 camera management, bracketed HDR capture with on-device
* pixel-level merge, Radiance .hdr encoding, and FTP upload.
*/

#include "camera.h"
#include "globals.h"
#include "sensor_init.h"
#include "comms.h"
#include "version.h"
#include <cmath>
#include <esp_camera.h>
#include <esp_task_wdt.h>
#include <WiFi.h>

static float*    s_accum     = nullptr;
static float*    s_best_conf = nullptr;
static uint16_t* s_avg_buf   = nullptr;  // also used as the .hdr encode buffer
static size_t    s_buf_pixels = 0;

void freeHDRBuffers() {
    if (s_accum)     { free(s_accum);     s_accum     = nullptr; }
    if (s_best_conf) { free(s_best_conf); s_best_conf = nullptr; }
    if (s_avg_buf)   { free(s_avg_buf);   s_avg_buf   = nullptr; }
    s_buf_pixels = 0;
}

void freeHDRAccumBuffers() {
    if (s_accum)     { free(s_accum);     s_accum     = nullptr; }
    if (s_best_conf) { free(s_best_conf); s_best_conf = nullptr; }
}

static uint16_t ovReadVTS(sensor_t* s) {
    int hi = s->get_reg(s, 0x380e, 0xff);
    int lo = s->get_reg(s, 0x380f, 0xff);
    if (hi < 0 || lo < 0) return 984;
    return static_cast<uint16_t>((hi << 8) | lo);
}

static uint16_t ovReadHTS(sensor_t* s) {
    int hi = s->get_reg(s, 0x380c, 0xff);
    int lo = s->get_reg(s, 0x380d, 0xff);
    if (hi < 0 || lo < 0) return 1896;
    return static_cast<uint16_t>((hi << 8) | lo);
}

static int calculateLinePeriod(sensor_t* s) {
    constexpr float PCLK_MHZ_VGA = 56.0f;
    uint16_t hts = ovReadHTS(s);
    float line_us = (static_cast<float>(hts) / PCLK_MHZ_VGA) * 1.15f;
    return static_cast<int>(line_us);
}

static constexpr int MAX_AEC_VALUE = 1048496;

// AEC is in 1/16 line units. Exposures longer than VTS - 4 lines need a longer frame (VTS).
static int ovSetExtendedExposure(sensor_t* s, int aec_val, uint16_t default_vts,
                                 int* actual_aec = nullptr) {
    const int line_period_us = calculateLinePeriod(s);
    if (aec_val > MAX_AEC_VALUE) {
        Serial.printf("HDR WARNING: aec_val %d exceeds AEC max (%d). Clamping.\n",
                      aec_val, MAX_AEC_VALUE);
        aec_val = MAX_AEC_VALUE;
    }

    int exposure_lines = (aec_val + 15) >> 4;

    uint16_t new_vts = default_vts;
    if (exposure_lines >= static_cast<int>(default_vts - 4)) {
        int extended = exposure_lines + 100;
        new_vts = static_cast<uint16_t>(min(extended, static_cast<int>(MAX_SAFE_VTS)));
    }

    if (new_vts == MAX_SAFE_VTS) {
        int max_aec_for_vts = (static_cast<int>(new_vts) - 100) * 16;
        if (aec_val > max_aec_for_vts && max_aec_for_vts > 0) {
            Serial.printf("HDR: VTS capped at %u — clamping AEC from %d to %d\n",
                          new_vts, aec_val, max_aec_for_vts);
            aec_val = max_aec_for_vts;
        }
    }

    if (actual_aec) *actual_aec = aec_val;

    s->set_reg(s, 0x380e, 0xff, (new_vts >> 8) & 0xFF);
    s->set_reg(s, 0x380f, 0xff,  new_vts       & 0xFF);

    unsigned int aec = static_cast<unsigned int>(aec_val);
    s->set_reg(s, 0x3500, 0x0f, (aec >> 16) & 0x0F);
    s->set_reg(s, 0x3501, 0xff, (aec >> 8)  & 0xFF);
    s->set_reg(s, 0x3502, 0xff,  aec        & 0xFF);

    int rb0 = s->get_reg(s, 0x3500, 0x0f);
    int rb1 = s->get_reg(s, 0x3501, 0xff);
    int rb2 = s->get_reg(s, 0x3502, 0xff);
    if (rb0 >= 0 && rb1 >= 0 && rb2 >= 0) {
        unsigned int rb_aec = (static_cast<unsigned int>(rb0) << 16)
                            | (static_cast<unsigned int>(rb1) << 8)
                            |  static_cast<unsigned int>(rb2);
        if (rb_aec != aec) {
            Serial.printf("HDR WARNING: AEC readback mismatch! wrote %u, read %u\n",
                          aec, rb_aec);
        }
    } else {
        Serial.println("HDR WARNING: AEC register readback failed (SCCB error)");
    }

    return static_cast<int>(static_cast<uint32_t>(new_vts) * line_period_us / 1000) + 10;
}

void reinitCamera(bool hdrMode) {
    sensor_t* s = esp_camera_sensor_get();
    if (s) {
        s->set_reg(s, 0x3008, 0xff, 0x42);  // standby before deinit
        delay(50);
    }

    esp_camera_deinit();
    delay(100);
    if (hdrMode) {
        setupOV5640_YUV422_VGA();
    } else {
        setupOV5640_JPEG_WQXGA();
    }
}

void powerDownCamera() {
    sensor_t* s = esp_camera_sensor_get();
    if (s) {
        s->set_reg(s, 0x3008, 0xff, 0x42);
    }
}

static constexpr uint8_t HDR_LO = 16;
static constexpr uint8_t HDR_HI = 235;

// Triangular weight between HDR_LO and HDR_HI
static inline uint8_t pixelConf(uint8_t v) {
    if (v <= HDR_LO || v >= HDR_HI) return 0;
    constexpr int mid = ((int)HDR_LO + (int)HDR_HI) / 2;
    if (v <= mid) return static_cast<uint8_t>((int)(v - HDR_LO) * 254 / (mid - HDR_LO));
    else          return static_cast<uint8_t>((int)(HDR_HI - v) * 254 / (HDR_HI - mid));
}

HdrBuffer captureHDRMerged() {
    HdrBuffer result;

    reinitCamera(true);

    delay(500);

    for (int i = 0; i < 5; i++) {
        camera_fb_t* flush = esp_camera_fb_get();
        if (flush) esp_camera_fb_return(flush);
        delay(50);
    }

    camera_fb_t* probe = esp_camera_fb_get();
    if (!probe) {
        Serial.println("HDR: failed to probe frame dimensions");
        reinitCamera(false);
        return result;
    }
    const uint16_t W = probe->width;
    const uint16_t H = probe->height;
    esp_camera_fb_return(probe);

    const size_t num_pixels = static_cast<size_t>(W) * H;
    const size_t accum_bytes = num_pixels * 3 * sizeof(float);

    if (!s_accum || s_buf_pixels != num_pixels) {
        if (s_accum)     { free(s_accum);     s_accum     = nullptr; }
        if (s_best_conf) { free(s_best_conf); s_best_conf = nullptr; }
        if (s_avg_buf)   { free(s_avg_buf);   s_avg_buf   = nullptr; }

        s_accum = static_cast<float*>(
            heap_caps_malloc(accum_bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
        if (!s_accum) {
            Serial.printf("HDR: PSRAM alloc failed for accum (%u bytes needed)\n",
                          static_cast<unsigned>(accum_bytes));
            reinitCamera(false);
            return result;
        }

        s_best_conf = static_cast<float*>(
            heap_caps_malloc(num_pixels * sizeof(float), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
        if (!s_best_conf) {
            Serial.println("HDR: PSRAM alloc failed for confidence-map");
            reinitCamera(false);
            return result;
        }

        s_avg_buf = static_cast<uint16_t*>(
            heap_caps_malloc(num_pixels * 3 * sizeof(uint16_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
        if (!s_avg_buf) {
            Serial.println("HDR: avg_buf alloc failed — multi-frame brackets will be skipped");
        }

        s_buf_pixels = num_pixels;
        Serial.printf("HDR: persistent PSRAM buffers allocated for %ux%u (%u px)\n",
                      W, H, static_cast<unsigned>(num_pixels));
    }
    memset(s_accum, 0, accum_bytes);
    memset(s_best_conf, 0, num_pixels * sizeof(float));

    float*    accum     = s_accum;
    float*    best_conf = s_best_conf;
    uint16_t* avg_buf   = s_avg_buf;

    const float et_radius = (hdr_et_radius_pct / 100.0f)
                            * static_cast<float>(min(W / 2, H / 2));
    const float et_r2 = et_radius * et_radius;
    const float et_cx = static_cast<float>(W) * 0.5f;
    const float et_cy = static_cast<float>(H) * 0.5f;
    uint8_t* in_center = static_cast<uint8_t*>(
        heap_caps_malloc(num_pixels, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    size_t center_total = 0;
    if (in_center) {
        for (size_t i = 0; i < num_pixels; i++) {
            const float dx = static_cast<float>(i % W) - et_cx;
            const float dy = static_cast<float>(i / W) - et_cy;
            in_center[i] = (dx * dx + dy * dy <= et_r2) ? 1 : 0;
            if (in_center[i]) center_total++;
        }
    } else {
        for (size_t i = 0; i < num_pixels; i++) {
            const float dx = static_cast<float>(i % W) - et_cx;
            const float dy = static_cast<float>(i / W) - et_cy;
            if (dx * dx + dy * dy <= et_r2) center_total++;
        }
    }
    Serial.printf("HDR: center circle: %.0f%% radius = %.1f px, %u/%u pixels\n",
                  hdr_et_radius_pct, et_radius,
                  static_cast<unsigned>(center_total),
                  static_cast<unsigned>(num_pixels));

    sensor_t* cam_s = esp_camera_sensor_get();
    if (!cam_s) {
        Serial.println("HDR: camera sensor unavailable");
        if (in_center) free(in_center);
        reinitCamera(false);
        return result;
    }

    const uint16_t default_vts = ovReadVTS(cam_s);
    const int line_period_us = calculateLinePeriod(cam_s);
    Serial.printf("HDR: VGA default VTS = %u (frame ≈ %d ms, line period %d µs)\n",
                  default_vts,
                  static_cast<int>(static_cast<uint32_t>(default_vts) * line_period_us / 1000) + 10,
                  line_period_us);

    {
        // 1x analog gain and no extra VTS (0x350C/D is not cleared in manual AEC mode)
        cam_s->set_reg(cam_s, 0x350a, 0xff, 0x00);
        cam_s->set_reg(cam_s, 0x350b, 0xff, 0x10);
        cam_s->set_reg(cam_s, 0x350c, 0xff, 0x00);
        cam_s->set_reg(cam_s, 0x350d, 0xff, 0x00);

        int rb_3503 = cam_s->get_reg(cam_s, 0x3503, 0xff);
        int rb_350a = cam_s->get_reg(cam_s, 0x350a, 0xff);
        int rb_350b = cam_s->get_reg(cam_s, 0x350b, 0xff);
        if (rb_3503 >= 0 && (rb_3503 & 0x07) != 0x07)
            Serial.printf("HDR WARNING: 0x3503=0x%02X (expected 0x07 for AEC/AGC/VTS manual)\n", rb_3503);
        if ((rb_350a >= 0 && rb_350a != 0x00) || (rb_350b >= 0 && rb_350b != 0x10))
            Serial.printf("HDR WARNING: analog gain 0x350A/B=0x%02X%02X (expected 0x0010 = 1x)\n",
                          rb_350a, rb_350b);
    }

    const int num_brackets = static_cast<int>(exposure_values.size());
    int brackets_done = 0;
    for (int b = 0; b < num_brackets; b++) {
        const int exp_val = exposure_values[b];

        int actual_aec = exp_val;
        int frame_ms = ovSetExtendedExposure(cam_s, exp_val, default_vts, &actual_aec);

        // With fb_count = 1 the buffered frame still has the old exposure, so discard it
        delay(frame_ms);
        {
            camera_fb_t* stale = esp_camera_fb_get();
            if (stale) esp_camera_fb_return(stale);
        }
        delay(frame_ms);

        const int frames_to_avg = (actual_aec <= HDR_AVG_CUTOFF) ? hdr_avg_frames : 1;

        auto clamp8 = [](int x) -> uint8_t {
            return static_cast<uint8_t>(x < 0 ? 0 : (x > 255 ? 255 : x));
        };

        int frames_captured = 0;

        if (frames_to_avg == 1) {
            camera_fb_t* fb = esp_camera_fb_get();
            if (!fb) {
                Serial.printf("HDR: frame grab failed at bracket %d\n", b);
            } else {
                frames_captured = 1;
                const float norm = 1.0f / static_cast<float>(actual_aec);
                const uint8_t* px = fb->buf;
                for (size_t i = 0; i < num_pixels; i += 2) {
                    size_t byteOff = i * 2;
                    int y0 = px[byteOff + 0];
                    int u  = px[byteOff + 1] - 128;
                    int y1 = px[byteOff + 2];
                    int v  = px[byteOff + 3] - 128;

                    int r0 = y0 + (359 * v >> 8);  // YUYV to RGB (BT.601)
                    int g0 = y0 - ((88 * u + 183 * v) >> 8);
                    int b0 = y0 + (454 * u >> 8);

                    uint8_t r8 = clamp8(r0);
                    uint8_t g8 = clamp8(g0);
                    uint8_t b8 = clamp8(b0);
                    uint8_t maxch = max(r8, max(g8, b8));
                    if (maxch < HDR_HI) {
                        uint8_t c0 = pixelConf(maxch);
                        if (c0 > 0) {
                            float current_weight = c0 * (float)actual_aec;  // confidence x exposure
                            float nr = r8 * norm, ng = g8 * norm, nb = b8 * norm;
                            if (best_conf[i] <= 0.0f) {
                                accum[i * 3 + 0] = nr;
                                accum[i * 3 + 1] = ng;
                                accum[i * 3 + 2] = nb;
                                best_conf[i] = current_weight;
                            } else {
                                float w = best_conf[i], wc = w + current_weight;
                                accum[i * 3 + 0] = (w * accum[i * 3 + 0] + current_weight * nr) / wc;
                                accum[i * 3 + 1] = (w * accum[i * 3 + 1] + current_weight * ng) / wc;
                                accum[i * 3 + 2] = (w * accum[i * 3 + 2] + current_weight * nb) / wc;
                                best_conf[i] = wc;
                            }
                        } else if (best_conf[i] == 0.0f) {
                            accum[i * 3 + 0] = r8 * norm;
                            accum[i * 3 + 1] = g8 * norm;
                            accum[i * 3 + 2] = b8 * norm;
                        }
                    } else if (best_conf[i] == 0.0f) {
                        accum[i * 3 + 0] = r8 * norm;
                        accum[i * 3 + 1] = g8 * norm;
                        accum[i * 3 + 2] = b8 * norm;
                        best_conf[i] = -1.0f;
                    }

                    if (i + 1 < num_pixels) {
                        int r1 = y1 + (359 * v >> 8);
                        int g1 = y1 - ((88 * u + 183 * v) >> 8);
                        int b1 = y1 + (454 * u >> 8);

                        r8 = clamp8(r1);
                        g8 = clamp8(g1);
                        b8 = clamp8(b1);
                        maxch = max(r8, max(g8, b8));
                        if (maxch < HDR_HI) {
                            uint8_t c1 = pixelConf(maxch);
                            if (c1 > 0) {
                                float current_weight1 = c1 * (float)actual_aec;
                                float nr = r8 * norm, ng = g8 * norm, nb = b8 * norm;
                                if (best_conf[i + 1] <= 0.0f) {
                                    accum[(i + 1) * 3 + 0] = nr;
                                    accum[(i + 1) * 3 + 1] = ng;
                                    accum[(i + 1) * 3 + 2] = nb;
                                    best_conf[i + 1] = current_weight1;
                                } else {
                                    float w = best_conf[i + 1], wc = w + current_weight1;
                                    accum[(i + 1) * 3 + 0] = (w * accum[(i + 1) * 3 + 0] + current_weight1 * nr) / wc;
                                    accum[(i + 1) * 3 + 1] = (w * accum[(i + 1) * 3 + 1] + current_weight1 * ng) / wc;
                                    accum[(i + 1) * 3 + 2] = (w * accum[(i + 1) * 3 + 2] + current_weight1 * nb) / wc;
                                    best_conf[i + 1] = wc;
                                }
                            } else if (best_conf[i + 1] == 0.0f) {
                                accum[(i + 1) * 3 + 0] = r8 * norm;
                                accum[(i + 1) * 3 + 1] = g8 * norm;
                                accum[(i + 1) * 3 + 2] = b8 * norm;
                            }
                        } else if (best_conf[i + 1] == 0.0f) {
                            accum[(i + 1) * 3 + 0] = r8 * norm;
                            accum[(i + 1) * 3 + 1] = g8 * norm;
                            accum[(i + 1) * 3 + 2] = b8 * norm;
                            best_conf[i + 1] = -1.0f;
                        }
                    }
                }
                esp_camera_fb_return(fb);
            }
        } else {
            if (!avg_buf) {
                Serial.printf("HDR: avg_buf unavailable, skipping bracket %d\n", b);
                continue;
            }
            memset(avg_buf, 0, num_pixels * 3 * sizeof(uint16_t));

            for (int n = 0; n < frames_to_avg; n++) {
                camera_fb_t* fb = esp_camera_fb_get();
                if (!fb) {
                    Serial.printf("HDR: frame grab failed at bracket %d / avg %d\n", b, n);
                    break;
                }
                const uint8_t* px = fb->buf;
                for (size_t i = 0; i < num_pixels; i += 2) {
                    size_t byteOff = i * 2;
                    int y0 = px[byteOff + 0];
                    int u  = px[byteOff + 1] - 128;
                    int y1 = px[byteOff + 2];
                    int v  = px[byteOff + 3] - 128;

                    int r0 = y0 + (359 * v >> 8);
                    int g0 = y0 - ((88 * u + 183 * v) >> 8);
                    int b0 = y0 + (454 * u >> 8);
                    int r1 = y1 + (359 * v >> 8);
                    int g1 = y1 - ((88 * u + 183 * v) >> 8);
                    int b1 = y1 + (454 * u >> 8);

                    avg_buf[i * 3 + 0] += clamp8(r0);
                    avg_buf[i * 3 + 1] += clamp8(g0);
                    avg_buf[i * 3 + 2] += clamp8(b0);
                    if (i + 1 < num_pixels) {
                        avg_buf[(i + 1) * 3 + 0] += clamp8(r1);
                        avg_buf[(i + 1) * 3 + 1] += clamp8(g1);
                        avg_buf[(i + 1) * 3 + 2] += clamp8(b1);
                    }
                }
                frames_captured++;
                esp_camera_fb_return(fb);
                if (n < hdr_avg_frames - 1) { delay(frame_ms); }
            }

            if (frames_captured > 0) {
                if (frames_captured > 1) {
                    for (size_t i = 0; i < num_pixels * 3; i++) {
                        avg_buf[i] = static_cast<uint16_t>(avg_buf[i] / frames_captured);
                    }
                }

                const float norm = 1.0f / static_cast<float>(actual_aec);
                for (size_t i = 0; i < num_pixels; i++) {
                    uint8_t r8 = static_cast<uint8_t>(avg_buf[i * 3 + 0]);
                    uint8_t g8 = static_cast<uint8_t>(avg_buf[i * 3 + 1]);
                    uint8_t b8 = static_cast<uint8_t>(avg_buf[i * 3 + 2]);
                    uint8_t maxch = max(r8, max(g8, b8));
                    if (maxch < HDR_HI) {
                        uint8_t c = pixelConf(maxch);
                        if (c > 0) {
                            float current_weight = c * (float)actual_aec;
                            float nr = r8 * norm, ng = g8 * norm, nb = b8 * norm;
                            if (best_conf[i] <= 0.0f) {
                                accum[i * 3 + 0] = nr;
                                accum[i * 3 + 1] = ng;
                                accum[i * 3 + 2] = nb;
                                best_conf[i] = current_weight;
                            } else {
                                float w = best_conf[i], wc = w + current_weight;
                                accum[i * 3 + 0] = (w * accum[i * 3 + 0] + current_weight * nr) / wc;
                                accum[i * 3 + 1] = (w * accum[i * 3 + 1] + current_weight * ng) / wc;
                                accum[i * 3 + 2] = (w * accum[i * 3 + 2] + current_weight * nb) / wc;
                                best_conf[i] = wc;
                            }
                        } else if (best_conf[i] == 0.0f) {
                            accum[i * 3 + 0] = r8 * norm;
                            accum[i * 3 + 1] = g8 * norm;
                            accum[i * 3 + 2] = b8 * norm;
                        }
                    } else if (best_conf[i] == 0.0f) {
                        accum[i * 3 + 0] = r8 * norm;
                        accum[i * 3 + 1] = g8 * norm;
                        accum[i * 3 + 2] = b8 * norm;
                        best_conf[i] = -1.0f;
                    }
                }
            }
        }

        brackets_done = b + 1;
        esp_task_wdt_reset();

        float fill_pct = -1.0f;
        size_t center_filled = 0;
        if (center_total > 0 && exp_val >= hdr_et_min_exp && in_center) {
            for (size_t i = 0; i < num_pixels; i++) {
                if (in_center[i] && best_conf[i] > 0) center_filled++;
            }
            fill_pct = center_filled * 100.0f / static_cast<float>(center_total);
        }

        if (fill_pct >= 0.0f) {
            Serial.printf("HDR: bracket %d/%d (exp=%d, avg=%d) merged (%d frames)"
                          " | Center fill: %.1f%% (%u/%u)\n",
                          b + 1, num_brackets, exp_val, frames_to_avg, frames_captured,
                          fill_pct,
                          static_cast<unsigned>(center_filled),
                          static_cast<unsigned>(center_total));
        } else {
            Serial.printf("HDR: bracket %d/%d (exp=%d, avg=%d) merged (%d frames)\n",
                          b + 1, num_brackets, exp_val, frames_to_avg, frames_captured);
        }

        if (hdr_early_term && fill_pct >= 0.0f && b < num_brackets - 1) {
            if (fill_pct >= hdr_et_pct) {
                Serial.printf("HDR: early-term at bracket %d/%d"
                              " (fill=%.1f%% >= %.1f%%) — %d bracket(s) skipped\n",
                              b + 1, num_brackets, fill_pct, hdr_et_pct,
                              num_brackets - b - 1);
                break;
            }
        }
    }

    // Pixels that are still zero get the image maximum
    if (hdr_sat_fill) {
        float max_val[3] = {0.0f, 0.0f, 0.0f};
        for (size_t i = 0; i < num_pixels; i++) {
            float r = accum[i * 3 + 0];
            float g = accum[i * 3 + 1];
            float b = accum[i * 3 + 2];
            if (r > max_val[0]) max_val[0] = r;
            if (g > max_val[1]) max_val[1] = g;
            if (b > max_val[2]) max_val[2] = b;
        }

        int sat_count = 0;
        for (size_t i = 0; i < num_pixels; i++) {
            if (accum[i*3+0] < 1e-6f && accum[i*3+1] < 1e-6f && accum[i*3+2] < 1e-6f) {
                accum[i * 3 + 0] = max_val[0];
                accum[i * 3 + 1] = max_val[1];
                accum[i * 3 + 2] = max_val[2];
                sat_count++;
            }
        }
        Serial.printf("HDR: sat_fill assigned (R=%.4f G=%.4f B=%.4f) to %d pixels\n",
                      max_val[0], max_val[1], max_val[2], sat_count);
    }

    result.data           = accum;
    result.width          = W;
    result.height         = H;
    result.isValid        = true;
    result.brackets_used  = brackets_done;
    result.brackets_total = num_brackets;

    Serial.printf("HDR merge complete: %dx%d, %.1f KB in PSRAM — %d/%d brackets used\n",
                  W, H, static_cast<float>(accum_bytes) / 1024.0f,
                  brackets_done, num_brackets);
    if (in_center) free(in_center);
    return result;
}

static void float_to_rgbe(uint8_t rgbe[4], float r, float g, float b) {
    float maxc = fmaxf(r, fmaxf(g, b));
    if (maxc < 1e-32f) {
        rgbe[0] = rgbe[1] = rgbe[2] = rgbe[3] = 0;
        return;
    }
    int exp;
    float scale = frexpf(maxc, &exp) * 256.0f / maxc;
    rgbe[0] = static_cast<uint8_t>(r * scale);
    rgbe[1] = static_cast<uint8_t>(g * scale);
    rgbe[2] = static_cast<uint8_t>(b * scale);
    rgbe[3] = static_cast<uint8_t>(exp + 128);
}

size_t encodeRadianceHdr(const HdrBuffer& hdr, uint8_t* outBuf, struct tm timeinfo) {
    size_t offset = 0;

    const bool do_crop = cam_crop_enable && cam_cal_colour && (hdr.channels == 3);
    uint16_t out_w = hdr.width;
    uint16_t out_h = hdr.height;
    uint16_t crop_x = 0, crop_y = 0;
    if (do_crop) {
        crop_x = cam_cal_colour->crop_x;
        crop_y = cam_cal_colour->crop_y;
        if (crop_x >= hdr.width)  crop_x = 0;
        if (crop_y >= hdr.height) crop_y = 0;
        out_w = min(cam_cal_colour->crop_w, static_cast<uint16_t>(hdr.width  - crop_x));
        out_h = min(cam_cal_colour->crop_h, static_cast<uint16_t>(hdr.height - crop_y));
    }

    float ell_cx = 0, ell_cy = 0, ell_rx2_inv = 0, ell_ry2_inv = 0;
    if (do_crop) {
        ell_cx = cam_cal_colour->vign_cx - crop_x;
        ell_cy = cam_cal_colour->vign_cy - crop_y;
        float rx = out_w / 2.0f;
        float ry = out_h / 2.0f;
        ell_rx2_inv = 1.0f / (rx * rx);
        ell_ry2_inv = 1.0f / (ry * ry);
    }

    char capdate[32], gmtdate[32];
    strftime(capdate, sizeof(capdate), "%Y:%m:%d %H:%M:%S", &timeinfo);
    time_t t = mktime(&timeinfo);
    strftime(gmtdate, sizeof(gmtdate), "%Y:%m:%d %H:%M:%S", gmtime(&t));

    char hdr_header[768];
    int hlen = snprintf(hdr_header, sizeof(hdr_header),
        "#?RADIANCE\n"
        "SOFTWARE=SpatialSpectral-Firmware/" FIRMWARE_VERSION "\n"
        "DEVICE=%s\n"
        "SENSOR=OV5640\n"
        "CAPDATE= %s\n"
        "GMT= %s\n"
        "FORMAT=32-bit_rle_rgbe\n"
        "EXPOSURE=1.0000e+00\n"
        "PRIMARIES=0.6400 0.3300 0.2900 0.6000 0.1500 0.0600 0.3333 0.3333\n"
        "HDR_BRACKETS=%d/%d\n",
        deviceName.c_str(),
        capdate, gmtdate,
        hdr.brackets_used, hdr.brackets_total);

    if (cam_cal_colour) {
        hlen += snprintf(hdr_header + hlen, sizeof(hdr_header) - hlen,
            "CAL_VIGN_BCD=%.5f %.5f %.5f\n"
            "CAL_VIGN_CENTER=%.1f %.1f\n"
            "CAL_VIGN_MAXDIST=%.3f\n"
            "CAL_SCALE=%.4f\n"
            "CAL_CROP=%u %u %u %u\n"
            "CAL_FLAGS=%s%s%s\n",
            cam_cal_colour->vign_b, cam_cal_colour->vign_c, cam_cal_colour->vign_d,
            cam_cal_colour->vign_cx, cam_cal_colour->vign_cy,
            cam_cal_colour->vign_max_dist,
            cam_cal_colour->cal_scale,
            cam_cal_colour->crop_x, cam_cal_colour->crop_y,
            cam_cal_colour->crop_w, cam_cal_colour->crop_h,
            cam_vign_enable ? "VIGN " : "",
            cam_cal_enable  ? "SCALE " : "",
            cam_crop_enable ? "CROP" : "");
    }

    hlen += snprintf(hdr_header + hlen, sizeof(hdr_header) - hlen,
        "\n-Y %u +X %u\n",
        static_cast<unsigned>(out_h), static_cast<unsigned>(out_w));

    memcpy(outBuf, hdr_header, static_cast<size_t>(hlen));
    offset = static_cast<size_t>(hlen);

    float* col_dx2 = nullptr;
    float inv_max_dist2 = 0.0f;
    if (cam_vign_enable && cam_cal_colour) {
        col_dx2 = static_cast<float*>(malloc(out_w * sizeof(float)));

        if (!col_dx2) {
            Serial.println(F("WARN: col_dx2 alloc failed, vignetting disabled"));
        }
        if (col_dx2) {
            for (uint16_t x = 0; x < out_w; x++) {
                float dx = static_cast<float>(x + crop_x) - cam_cal_colour->vign_cx;
                col_dx2[x] = dx * dx;
            }
        }
        float md = cam_cal_colour->vign_max_dist;
        inv_max_dist2 = (md > 0.0f) ? 1.0f / (md * md) : 0.0f;
    }

    uint8_t rgbe[4];
    const size_t out_pixels = static_cast<size_t>(out_w) * out_h;
    for (size_t i = 0; i < out_pixels; i++) {
        uint16_t ox = static_cast<uint16_t>(i % out_w);
        uint16_t oy = static_cast<uint16_t>(i / out_w);
        uint16_t src_x = ox + crop_x;
        uint16_t src_y = oy + crop_y;
        size_t src_idx = static_cast<size_t>(src_y) * hdr.width + src_x;

        float cr = hdr.data[src_idx * 3 + 0];
        float cg = hdr.data[src_idx * 3 + 1];
        float cb = hdr.data[src_idx * 3 + 2];

        if (do_crop) {
            float dx = static_cast<float>(ox) - ell_cx;
            float dy = static_cast<float>(oy) - ell_cy;
            if (dx * dx * ell_rx2_inv + dy * dy * ell_ry2_inv > 1.0f) {
                cr = cg = cb = 0.0f;
            }
        }

        {
            float factor = 1.0f;
            if (cam_vign_enable && cam_cal_colour && col_dx2) {
                float dy = static_cast<float>(src_y) - cam_cal_colour->vign_cy;
                float dist2 = col_dx2[ox] + dy * dy;
                float rn2 = dist2 * inv_max_dist2;
                float rn4 = rn2 * rn2;
                float rn6 = rn4 * rn2;
                // V(r) = 1 + b r^2 + c r^4 + d r^6, r normalised to vign_max_dist
                float vign = 1.0f + cam_cal_colour->vign_b * rn2
                           + cam_cal_colour->vign_c * rn4
                           + cam_cal_colour->vign_d * rn6;
                if (vign < 0.1f) vign = 0.1f;
                factor = 1.0f / vign;
                if (factor > 10.0f) factor = 10.0f;
            }
            if (cam_cal_enable && cam_cal_colour) {
                factor *= cam_cal_scale_overridden ? cam_cal_scale_override
                                                   : cam_cal_colour->cal_scale;
            }
            cr *= factor;
            cg *= factor;
            cb *= factor;
        }
        float_to_rgbe(rgbe, cr, cg, cb);
        outBuf[offset++] = rgbe[0];
        outBuf[offset++] = rgbe[1];
        outBuf[offset++] = rgbe[2];
        outBuf[offset++] = rgbe[3];
    }

    if (col_dx2) free(col_dx2);

    if (do_crop) {
        Serial.printf("HDR encode: cropped %ux%u → %ux%u, elliptical mask applied\n",
                      hdr.width, hdr.height, out_w, out_h);
    }

    return offset;
}

EncodedHDR captureAndEncodeHDR(struct tm timeinfo) {
    EncodedHDR result;
    Serial.println("--- Starting HDR capture + encode ---");

    HdrBuffer hdr = captureHDRMerged();
    if (!hdr.isValid || !hdr.data) {
        Serial.println("HDR: capture/merge failed.");
        return result;
    }

    const size_t num_pixels = static_cast<size_t>(hdr.width) * hdr.height;

    strftime(result.filename, sizeof(result.filename), "%Y%m%d_%H%M%S", &timeinfo);
    snprintf(result.filename + strlen(result.filename),
             sizeof(result.filename) - strlen(result.filename),
             "_%s.hdr", deviceName.c_str());

    constexpr size_t HEADER_MAX = 768;
    size_t enc_pixels = num_pixels;
    if (cam_crop_enable && cam_cal_colour) {
        uint16_t cx = (cam_cal_colour->crop_x < hdr.width)  ? cam_cal_colour->crop_x : 0;
        uint16_t cy = (cam_cal_colour->crop_y < hdr.height) ? cam_cal_colour->crop_y : 0;
        uint16_t cw = min(cam_cal_colour->crop_w,
                          static_cast<uint16_t>(hdr.width  - cx));
        uint16_t ch = min(cam_cal_colour->crop_h,
                          static_cast<uint16_t>(hdr.height - cy));
        enc_pixels = static_cast<size_t>(cw) * ch;
    }
    const size_t out_size = HEADER_MAX + enc_pixels * 4;

    if (!s_avg_buf || out_size > s_buf_pixels * 3 * sizeof(uint16_t)) {
        Serial.printf("HDR: encode buffer too small (%u > %u)\n",
                      static_cast<unsigned>(out_size),
                      static_cast<unsigned>(s_buf_pixels * 3 * sizeof(uint16_t)));
        return result;
    }
    uint8_t* encoded = reinterpret_cast<uint8_t*>(s_avg_buf);
    size_t encoded_len = encodeRadianceHdr(hdr, encoded, timeinfo);
    hdr.data = nullptr;

    freeHDRAccumBuffers();

    result.data = encoded;
    result.len = encoded_len;
    result.brackets_used = hdr.brackets_used;
    result.brackets_total = hdr.brackets_total;
    result.valid = true;

    Serial.printf("HDR: encoded %s (%u bytes) — %d/%d brackets\n",
                  result.filename, static_cast<unsigned>(encoded_len),
                  hdr.brackets_used, hdr.brackets_total);
    return result;
}

bool uploadEncodedHDR(ESP32_FTPClient& ftp, const char* baseDir, const EncodedHDR& hdr) {
    if (!hdr.valid || !hdr.data || hdr.len == 0) {
        Serial.println("HDR upload: no valid data to upload.");
        return false;
    }

    Serial.printf("HDR: uploading %s (%u bytes)...\n",
                  hdr.filename, static_cast<unsigned>(hdr.len));

    bool wdt_added = (esp_task_wdt_add(NULL) == ESP_OK);

    char tmpName[76];
    // Upload as .tmp and rename when complete
    snprintf(tmpName, sizeof(tmpName), "%s.tmp", hdr.filename);

    bool uploaded = false;
    for (int attempt = 1; attempt <= 6 && !uploaded; attempt++) {
        esp_task_wdt_reset();

        if (isUploadDeadlineImminent()) {
            Serial.println("HDR upload aborted: next measurement cycle is imminent.");
            return false;
        }

        if (WiFi.status() != WL_CONNECTED) {
            Serial.printf("HDR: WiFi down, attempt %d/6 — waiting 5s...\n", attempt);
            for (int i = 0; i < 10; i++) { delay(500); esp_task_wdt_reset(); }
            continue;
        }

        esp_task_wdt_reset();
        ftp.OpenConnection();
        esp_task_wdt_reset();
        ftp.ChangeWorkDir(baseDir);
        esp_task_wdt_reset();
        ftp.InitFile("Type I");
        esp_task_wdt_reset();
        ftp.NewFile(tmpName);

        size_t offset = 0;
        while (offset < hdr.len) {
            if (isUploadDeadlineImminent()) {
                Serial.println("CRITICAL: HDR upload aborted mid-transfer — FTP data socket compromised, rebooting.");
                ftp.CloseFile();
                ftp.CloseConnection();
                saveCrashReason("HDR upload deadline exceeded mid-transfer");
                delay(1000);
                ESP.restart();
            }
            if (WiFi.status() != WL_CONNECTED) {
                Serial.println("CRITICAL: HDR WiFi lost mid-transfer — FTP data socket compromised, rebooting.");
                ftp.CloseFile();
                ftp.CloseConnection();
                saveCrashReason("HDR upload WiFi lost mid-transfer");
                delay(1000);
                ESP.restart();
            }
            size_t toWrite = min(FTP_CHUNK_SIZE, hdr.len - offset);
            ftp.WriteData(hdr.data + offset, toWrite);
            offset += toWrite;
            esp_task_wdt_reset();
        }

        esp_task_wdt_reset();
        ftp.CloseFile();

        char fromBuf[76], toBuf[76];
        strncpy(fromBuf, tmpName, sizeof(fromBuf));       fromBuf[sizeof(fromBuf)-1] = '\0';
        strncpy(toBuf, hdr.filename, sizeof(toBuf));      toBuf[sizeof(toBuf)-1] = '\0';
        esp_task_wdt_reset();
        ftp.RenameFile(fromBuf, toBuf);
        esp_task_wdt_reset();
        if (ftp.isConnected()) {
            ftp.CloseConnection();
            uploaded = true;
        } else {
            ftp.CloseConnection();
            Serial.printf("HDR: FTP data error on attempt %d/6 — retrying\n", attempt);
        }
    }

    if (!uploaded) {
        Serial.printf("CRITICAL: HDR upload failed after 6 attempts: %s — rebooting.\n", hdr.filename);
        saveCrashReason("HDR upload failed after 6 attempts");
        delay(1000);
        ESP.restart();
    }

    Serial.printf("HDR: uploaded %s\n", hdr.filename);

    char topic[100];
    snprintf(topic, sizeof(topic), "sensors/%s/new_hdr", deviceName.c_str());
    client.publish(topic, hdr.filename);

    char brackets_topic[100];
    snprintf(brackets_topic, sizeof(brackets_topic), "sensors/%s/hdr_brackets",
             deviceName.c_str());
    char brackets_payload[12];
    snprintf(brackets_payload, sizeof(brackets_payload), "%d/%d",
             hdr.brackets_used, hdr.brackets_total);
    client.publish(brackets_topic, brackets_payload, false);

    if (wdt_added) esp_task_wdt_delete(NULL);

    return true;
}

CapturedJPEG captureContextJPEG(struct tm timeinfo) {
    CapturedJPEG result;
    Serial.println("JPEG: Capturing WQXGA auto-exposure context image...");

    freeHDRBuffers();

    delay(150);

    reinitCamera(false);
    sensor_t* s = esp_camera_sensor_get();
    if (!s) {
        Serial.println("JPEG: sensor unavailable");
        return result;
    }

    for (int i = 0; i < 10; i++) {
        camera_fb_t* flush = esp_camera_fb_get();
        if (flush) esp_camera_fb_return(flush);
        delay(150);
    }

    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("JPEG: frame grab failed");
        return result;
    }

    strftime(result.filename, sizeof(result.filename), "%Y%m%d_%H%M%S", &timeinfo);
    snprintf(result.filename + strlen(result.filename),
             sizeof(result.filename) - strlen(result.filename),
             "_%s_context.jpg", deviceName.c_str());

    result.data = fb->buf;
    result.len = fb->len;
    result._fb = fb;
    result.valid = true;

    Serial.printf("JPEG: captured %s (%u bytes)\n",
                  result.filename, static_cast<unsigned>(fb->len));
    return result;
}

bool uploadContextJPEG(ESP32_FTPClient& ftp, const char* baseDir, CapturedJPEG& jpeg) {
    if (!jpeg.valid || !jpeg.data || jpeg.len == 0) {
        Serial.println("JPEG upload: no valid data to upload.");
        releaseJPEG(jpeg);
        return false;
    }

    Serial.printf("JPEG: uploading %s (%u bytes)...\n",
                  jpeg.filename, static_cast<unsigned>(jpeg.len));

    bool wdt_added = (esp_task_wdt_add(NULL) == ESP_OK);

    char tmpName[76];
    snprintf(tmpName, sizeof(tmpName), "%s.tmp", jpeg.filename);

    bool uploaded = false;
    for (int attempt = 1; attempt <= 6 && !uploaded; attempt++) {
        esp_task_wdt_reset();

        if (isUploadDeadlineImminent()) {
            Serial.println("JPEG upload aborted: next measurement cycle is imminent.");
            releaseJPEG(jpeg);
            return false;
        }

        if (WiFi.status() != WL_CONNECTED) {
            Serial.printf("JPEG: WiFi down, attempt %d/6 — waiting 5s...\n", attempt);
            for (int i = 0; i < 10; i++) { delay(500); esp_task_wdt_reset(); }
            continue;
        }

        esp_task_wdt_reset();
        ftp.OpenConnection();
        esp_task_wdt_reset();
        ftp.ChangeWorkDir(baseDir);
        esp_task_wdt_reset();
        ftp.InitFile("Type I");
        esp_task_wdt_reset();
        ftp.NewFile(tmpName);

        size_t offset = 0;
        while (offset < jpeg.len) {
            if (isUploadDeadlineImminent()) {
                Serial.println("CRITICAL: JPEG upload aborted mid-transfer — FTP data socket compromised, rebooting.");
                ftp.CloseFile();
                ftp.CloseConnection();
                releaseJPEG(jpeg);
                saveCrashReason("JPEG upload deadline exceeded mid-transfer");
                delay(1000);
                ESP.restart();
            }
            if (WiFi.status() != WL_CONNECTED) {
                Serial.println("CRITICAL: JPEG WiFi lost mid-transfer — FTP data socket compromised, rebooting.");
                ftp.CloseFile();
                ftp.CloseConnection();
                releaseJPEG(jpeg);
                saveCrashReason("JPEG upload WiFi lost mid-transfer");
                delay(1000);
                ESP.restart();
            }
            size_t toWrite = min(FTP_CHUNK_SIZE, jpeg.len - offset);
            ftp.WriteData(jpeg.data + offset, toWrite);
            offset += toWrite;
            esp_task_wdt_reset();
        }

        esp_task_wdt_reset();
        ftp.CloseFile();

        char fromBuf[76], toBuf[76];
        strncpy(fromBuf, tmpName, sizeof(fromBuf));        fromBuf[sizeof(fromBuf)-1] = '\0';
        strncpy(toBuf, jpeg.filename, sizeof(toBuf));      toBuf[sizeof(toBuf)-1] = '\0';
        esp_task_wdt_reset();
        ftp.RenameFile(fromBuf, toBuf);
        esp_task_wdt_reset();
        if (ftp.isConnected()) {
            ftp.CloseConnection();
            uploaded = true;
        } else {
            ftp.CloseConnection();
            Serial.printf("JPEG: FTP data error on attempt %d/6 — retrying\n", attempt);
        }
    }

    if (!uploaded) {
        Serial.printf("CRITICAL: JPEG upload failed after 6 attempts: %s — rebooting.\n", jpeg.filename);
        releaseJPEG(jpeg);
        saveCrashReason("JPEG upload failed after 6 attempts");
        delay(1000);
        ESP.restart();
    } else {
        Serial.printf("JPEG: uploaded %s\n", jpeg.filename);

        char topic[100];
        snprintf(topic, sizeof(topic), "sensors/%s/new_context_jpeg", deviceName.c_str());
        client.publish(topic, jpeg.filename);
    }

    if (wdt_added) esp_task_wdt_delete(NULL);
    releaseJPEG(jpeg);
    return uploaded;
}

void releaseJPEG(CapturedJPEG& jpeg) {
    if (jpeg._fb) {
        esp_camera_fb_return(static_cast<camera_fb_t*>(jpeg._fb));
        jpeg._fb = nullptr;
    }
    jpeg.data = nullptr;
    jpeg.valid = false;
}
