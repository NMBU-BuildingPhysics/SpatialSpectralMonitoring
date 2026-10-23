/*
* Project: Spatial-Spectral Sensing System
* Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
* Author:  Tobias Kristiansen / NMBU Building Physics
* License: GNU General Public License v3.0
*
* Description:
* Hardware initialization for all I2C sensors (TSL2591, AS7265x, AS7331,
* SHT4X) and OV5640 camera configurations (YUV422 VGA for HDR, JPEG WQXGA for context images).
*/

#include "sensor_init.h"
#include "measurement.h"
#include "globals.h"

#define CAMERA_MODEL_XIAO_ESP32S3
#include "src/sensors/camera_pins.h"

TSL2591  tsl;
SHT4X    sht;
AS7265X  as7265x;
AS7331   as7331;

static bool initWithRetry(const char* name, bool (*initFn)(), int maxRetries = 5) {
    for (int attempt = 1; attempt <= maxRetries; attempt++) {
        if (initFn()) return true;
        Serial.printf("%s init failed (attempt %d/%d)\n", name, attempt, maxRetries);
        delay(200);
    }
    Serial.printf("ERROR: %s not responding after %d attempts.\n", name, maxRetries);
    return false;
}

static void fillCameraPins(camera_config_t& cfg) {
    cfg.ledc_channel = LEDC_CHANNEL_0;
    cfg.ledc_timer   = LEDC_TIMER_0;
    cfg.pin_d0       = Y2_GPIO_NUM;
    cfg.pin_d1       = Y3_GPIO_NUM;
    cfg.pin_d2       = Y4_GPIO_NUM;
    cfg.pin_d3       = Y5_GPIO_NUM;
    cfg.pin_d4       = Y6_GPIO_NUM;
    cfg.pin_d5       = Y7_GPIO_NUM;
    cfg.pin_d6       = Y8_GPIO_NUM;
    cfg.pin_d7       = Y9_GPIO_NUM;
    cfg.pin_xclk     = XCLK_GPIO_NUM;
    cfg.pin_pclk     = PCLK_GPIO_NUM;
    cfg.pin_vsync    = VSYNC_GPIO_NUM;
    cfg.pin_href     = HREF_GPIO_NUM;
    cfg.pin_sscb_sda = SIOD_GPIO_NUM;
    cfg.pin_sscb_scl = SIOC_GPIO_NUM;
    cfg.pin_pwdn     = PWDN_GPIO_NUM;
    cfg.pin_reset    = RESET_GPIO_NUM;
    cfg.xclk_freq_hz = 24000000;
    cfg.grab_mode    = CAMERA_GRAB_LATEST;
    cfg.fb_location  = CAMERA_FB_IN_PSRAM;
    cfg.jpeg_quality = 12;
}

static void applyBaseSensorSettings(sensor_t* s) {
    Serial.println("CAM: applying base sensor settings...");
    s->set_brightness(s, 0);
    s->set_contrast(s, 0);
    s->set_saturation(s, 0);
    s->set_special_effect(s, 0);
    s->set_whitebal(s, 0);
    s->set_awb_gain(s, 0);
    s->set_wb_mode(s, 0);
    s->set_reg(s, 0x3400, 0xff, 0x01);  // unity R/G/B gains (0x3400-0x3405)
    s->set_reg(s, 0x3401, 0xff, 0x00);
    s->set_reg(s, 0x3402, 0xff, 0x01);
    s->set_reg(s, 0x3403, 0xff, 0x00);
    s->set_reg(s, 0x3404, 0xff, 0x01);
    s->set_reg(s, 0x3405, 0xff, 0x00);
    Serial.println("CAM: AWB/WB/gain done");
    s->set_exposure_ctrl(s, 0);
    s->set_aec2(s, 0);
    s->set_ae_level(s, 0);
    s->set_aec_value(s, 0);
    s->set_gain_ctrl(s, 0);
    s->set_agc_gain(s, 0);
    s->set_gainceiling(s, static_cast<gainceiling_t>(0));
    Serial.println("CAM: AEC/AGC API calls done");

    s->set_reg(s, 0x3503, 0xff, 0x07);  // manual AEC/AGC, bit 2 is needed for VTS extension
    s->set_reg(s, 0x350a, 0xff, 0x00);
    s->set_reg(s, 0x350b, 0xff, 0x10);  // analog gain 1x
    Serial.println("CAM: direct register writes done (0x3503/0x350A/0x350B)");

    s->set_bpc(s, 1);
    s->set_wpc(s, 1);
    s->set_raw_gma(s, 0);        // gamma off, linear response
    s->set_lenc(s, 0);           // lens correction off
    s->set_hmirror(s, 0);
    s->set_vflip(s, 0);
    s->set_dcw(s, 1);
    s->set_colorbar(s, 0);
}

void setupOV5640_YUV422_VGA() {
    camera_config_t config = {};
    fillCameraPins(config);
    config.frame_size   = FRAMESIZE_VGA;
    config.pixel_format = PIXFORMAT_YUV422;
    config.fb_count     = 1;  // fb_count = 2 overflows the cam_task stack

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Camera HDR init failed: 0x%x\n", err);
        return;
    }

    delay(500);  // let cam_task start before SCCB writes

    sensor_t* s = esp_camera_sensor_get();
    applyBaseSensorSettings(s);
    s->set_agc_gain(s, 0);
}

void setupOV5640_JPEG_WQXGA() {
    camera_config_t config = {};
    fillCameraPins(config);
    config.frame_size   = FRAMESIZE_WQXGA;
    config.pixel_format = PIXFORMAT_JPEG;
    config.jpeg_quality = 3;
    config.fb_count     = 1;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Camera WQXGA init failed: 0x%x\n", err);
        return;
    }

    delay(500);

    sensor_t* s = esp_camera_sensor_get();
    s->set_brightness(s, 0);
    s->set_contrast(s, 0);
    s->set_saturation(s, 0);
    s->set_special_effect(s, 0);
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_wb_mode(s, 0);
    s->set_exposure_ctrl(s, 1);
    s->set_aec2(s, 1);
    s->set_ae_level(s, 0);
    s->set_gain_ctrl(s, 1);
    s->set_agc_gain(s, 0);
    s->set_gainceiling(s, static_cast<gainceiling_t>(6));
    s->set_bpc(s, 1);
    s->set_wpc(s, 1);
    s->set_raw_gma(s, 1);
    s->set_lenc(s, 1);
    s->set_hmirror(s, 0);
    s->set_vflip(s, 0);
    s->set_dcw(s, 1);
    s->set_colorbar(s, 0);
    s->set_reg(s, 0x3503, 0xff, 0x00);  // auto AEC/AGC
}

void tslApplyAndFlush(int time_ms) {
    tsl.Disable();
    delay(10);
    tsl.Enable();
    delay(time_ms + 50);
    tsl.Get_ALS();
}

void setupTSL2591() {
    if (!initWithRetry("TSL2591", []() { return tsl.begin(); })) return;
    tsl.Enable();
    setGain('I', I_gainValue);
    setIntegrationTime('I', I_integrationTime);
}

void setupAS7331() {
    if (!initWithRetry("AS7331", []() { return as7331.begin(); })) return;
    as7331.Set_Device_State(AS7331_STATE_CONFIGURATION);
    as7331.Set_Mode(AS7331_MMODE_CONT);
    as7331.Set_CCLK(AS7331_CCLK_1024);
    setGain('U', U_gainValue);
    setIntegrationTime('U', U_integrationTime);
    as7331.Set_BREAK(25);
    as7331.Set_Device_State(AS7331_STATE_MEASUREMENT);
    as7331.Set_Measurement(AS7331_MEASUREMENT_START);
}

void setupAS7265X() {
    if (!initWithRetry("AS7265X", []() { return as7265x.begin(); })) return;
    as7265x.Set_Interrupt(true);
    as7265x.Set_Measurement(AS7265X_MEASUREMENT_MODE2);
    setGain('S', S_gainValue);
    setIntegrationTime('S', S_integrationTime);
}

void setupSHT4X() {
    if (!initWithRetry("SHT4X", []() { return sht.begin(); })) return;
}
