# ESP32 Controller — Command Cheat Sheet

> **Boolean values** accepted everywhere: `ON | OFF | TRUE | FALSE | 1 | 0 | ENABLE | DISABLE`

---

## Serial Commands

Send commands via any serial terminal at **115200 baud** (newline-terminated). Commands are not case-sensitive.

### General

| Command | Effect |
|---------|--------|
| `HELP` \| `HELP <topic>` | Show commands (topics: `DEVICE`, `SENSOR`, `CAMERA`, `NETWORK`, `TEST`) |
| `WHO` \| `NAME` \| `ME` | Print device name, MAC and IP |
| `HEALTH` | Print WiFi, MQTT and uptime, and publish RSSI and uptime via MQTT |
| `SENSOR` \| `SENS` \| `SEN` | Trigger a spectral sensor measurement immediately |
| `CAM` \| `CAMERA` | Trigger a camera capture immediately |
| `BOTH` \| `RUN` \| `TRIGGER` | Trigger sensor measurement and camera capture |
| `HEAD` \| `HEADER` | Print the CSV column header |
| `TEST` \| `TEST <group>` | Run the self-test (groups: `ALL`, `CONFIG`, `MEMORY`, `SENSOR`, `CAMERA`, `NETWORK`) |

```
HELP
SENSOR
CAM
TEST CAMERA
```

---

### Network

| Command | Effect |
|---------|--------|
| `WIFI <bool>` | Enable / disable WiFi (disconnects or reconnects immediately) |
| `STAGGER <ms>` | Upload delay per device number before FTP |

```
WIFI OFF
WIFI ON
STAGGER 15000
```

---

### Calibration

| Command | Effect |
|---------|--------|
| `CAL` | One reading at the default gain and integration time, printed as CSV |
| `CAL DARK` | Dark count measurement at maximum gain and time (cover the sensors). Prints the values and asks whether to save them to NVS |

---

### Camera

| Command | Effect |
|---------|--------|
| `CAM <bool>` | Enable / disable camera altogether |
| `CAM CAL <bool>` | Enable / disable absolute luminance calibration |
| `CAM VIGN <bool>` | Enable / disable vignetting correction |
| `CAM CROP <bool>` | Enable / disable fisheye bounding-box crop |
| `CAM SCALE <float>` | Override the calibration scale (cd/m² per HDR unit) until reboot |
| `CAM SCALE RESET` | Use the compiled calibration scale again |
| `JPEG <bool>` | Enable / disable a WQXGA JPEG context image after the HDR |

```
CAM ON
CAM CAL OFF
CAM VIGN ON
CAM CROP OFF
```

---

### HDR

| Command | Effect |
|---------|--------|
| `HDR <bool>` | Enable / disable HDR mode |
| `HDR AVG <1–8>` | Number of frames averaged per short-exposure bracket |
| `HDR SATFILL <bool>` | Assign the image maximum to pixels that are still zero after the merge |
| `HDR EARLYTERM <bool>` | Enable / disable early termination of the exposure sequence |
| `HDR EARLYTERM PCT <0–100>` | Centre-fill % required to stop early (default 98) |
| `HDR EARLYTERM MIN <aec>` | Minimum exposure (AEC units, 1 = 1/16 line) before early termination is checked (default 64) |
| `HDR EARLYTERM RADIUS <10–100>` | Centre-ROI radius as % of min(W/2, H/2) (default 95) |

```
HDR ON
HDR AVG 3
HDR EARLYTERM ON
HDR EARLYTERM PCT 98
```

---

### Sensor Timing & Gain

`<sensor>` is one of: `S` (AS7265x spectral), `U` (AS7331 UV), `I` (TSL2591 illuminance), `C` (camera, `WAIT` only).

| Command | Effect |
|---------|--------|
| `S GAIN <1\|4\|16\|64>` | AS7265x gain |
| `S TIME <1–255>` | AS7265x integration time register (× 2.8 ms) |
| `U GAIN <1–2048>` | AS7331 gain (power of 2) |
| `U TIME <1–16384>` | AS7331 integration time in ms (power of 2) |
| `I GAIN <0–3>` | TSL2591 gain (0 = LOW, 1 = MED, 2 = HIGH, 3 = MAX) |
| `I TIME <100–600>` | TSL2591 integration time in ms (steps of 100) |
| `S WAIT <minutes>` | Spectral sensor measurement interval |
| `C WAIT <minutes>` | Camera capture interval |

Gain and time set here are the starting point; the goal-seeking auto-exposure adjusts them at every scheduled measurement.

```
S GAIN 16
U GAIN 128
I TIME 300
S WAIT 10
C WAIT 30
```

---

## MQTT Commands

### Trigger Topics

| Topic | Payload | Effect |
|-------|---------|--------|
| `control/trigger/<deviceName>` | `SENSORS` \| `S` | Trigger sensor measurement |
| `control/trigger/<deviceName>` | `CAMERA` \| `C` | Trigger camera capture |
| `control/trigger/<deviceName>` | `BOTH` \| `ALL` | Trigger both |
| `control/trigger/all` | Same as above | Broadcast trigger to every device |

```bash
mosquitto_pub -h localhost -t "control/trigger/all" -m "ALL"
```

---

### Timing

| Topic | Payload | Effect |
|-------|---------|--------|
| `control/wait_time` | `<minutes>` | Set **both** sensor and camera intervals |
| `control/S_wait_time` | `<minutes>` | Set spectral sensor interval only |
| `control/C_wait_time` | `<minutes>` | Set camera capture interval only |
| `control/upload_stagger` | `<ms>` | Upload delay per device number before FTP |

Intervals are saved in NVS. Minimum value: `MIN_WAIT_MINUTES` (defined in `config.h`). Publish with the retain flag so devices get the value after a reboot.

```bash
mosquitto_pub -h localhost -r -t "control/wait_time" -m "10"
```

---

### Camera

| Topic | Payload | Effect |
|-------|---------|--------|
| `control/cam_cal` | `<bool>` | Enable / disable absolute luminance calibration |
| `control/cam_vign` | `<bool>` | Enable / disable vignetting correction |
| `control/cam_crop` | `<bool>` | Enable / disable fisheye bounding-box crop |
| `control/cam_cal_scale/<deviceName>` | `<float>` \| `RESET` | Override the calibration scale for one device |
| `control/jpeg_toggle` | `<bool>` | Enable / disable the JPEG context image |

```bash
mosquitto_pub -h localhost -t "control/cam_vign" -m "ON"
mosquitto_pub -h localhost -t "control/cam_cal_scale/sensor01" -m "RESET"
```

---

### HDR

| Topic | Payload | Effect |
|-------|---------|--------|
| `control/hdr_toggle` | `<bool>` | Enable / disable HDR mode |
| `control/hdr_avg_frames` | `<1–8>` | Frames averaged per short-exposure bracket |
| `control/hdr_sat_fill` | `<bool>` | Enable / disable the zero-pixel fill |
| `control/hdr_early_term` | `<bool>` | Enable / disable early termination |
| `control/hdr_et_pct` | `<0–100>` | Centre-fill % threshold for early exit |
| `control/hdr_et_min_exp` | `<aec ≥ 0>` | Minimum bracket exposure before the early-termination check |
| `control/exposure_values` | `1,2,4,...` | Replace the HDR exposure sequence (comma-separated AEC units, ≥ 1) |

```bash
mosquitto_pub -h localhost -t "control/hdr_toggle" -m "ON"
mosquitto_pub -h localhost -t "control/exposure_values" -m "1,2,4,8,16,32,64,128,256,512,1024,2048,4096,8192,16384,32768,65536,131072"
```

---

## MQTT Status Topics (Published by Device)

All topics are prefixed with `sensors/<deviceName>/`.

| Topic suffix | Retained | Content |
|---|---|---|
| `status` | ✅ | `online` / `offline` (LWT) |
| `rssi` | ✅ | WiFi RSSI in dBm |
| `uptime_hours` | ✅ | Device uptime (hours, 2 decimals) |
| `temperature` | ✅ | Sensor temperature (°C, 1 decimal) |
| `humidity` | ✅ | Relative humidity (%, 0 decimals) |
| `illuminance` | ✅ | Calibrated lux (0 decimals) |
| `new_csv` | ❌ | Filename of the latest CSV upload |
| `new_hdr` | ❌ | Filename of the latest HDR upload |
| `hdr_brackets` | ❌ | Brackets used / total for the latest HDR (e.g. `7/18`) |
| `new_context_jpeg` | ❌ | Filename of the latest JPEG context image |
| `crash_report` | ❌ | Reason for the last reboot, sent once after reconnect |
| `selftest` | ❌ | JSON summary of the last `TEST` run |
| `cam_calibration` | ✅ | JSON `{"cal":true,"vign":true,"crop":false}` |
