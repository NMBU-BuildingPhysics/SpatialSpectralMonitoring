# Changelog

## v2.0.0

Firmware used for the multi-node deployment in Kristiansen et al., "The variability of spatial-spectral daylight: Data collection and case study" (dataset: [10.5281/zenodo.23349221](https://doi.org/10.5281/zenodo.23349221)).

HDR files recorded during that deployment carry the pre-release version string `SpatialSpectral-Firmware/v0.0.2-alpha-5-ga3f86f8-dirty` in their header. The firmware that wrote them is identical to v2.0.0.

### Firmware
- Dual-core operation: capture task on core 1 (sensors, camera, HDR merge) and network task on core 0 (MQTT, NTP, FTP), connected by an upload queue.
- On-device HDR: 18 exposure brackets (AEC 1 to 131072, 1 unit = 1/16 line) captured as YUV422 VGA, converted to RGB and merged in PSRAM with a triangular confidence weight times exposure. Long brackets extend the frame length (VTS).
- HDR output as flat RGBE Radiance `.hdr` (640x480). The header holds firmware version, device, capture time (local and GMT), bracket count, vignetting coefficients, calibration scale and crop.
- Pixel values are calibrated luminance in cd/m² per channel (Y = 0.2126 R + 0.7152 G + 0.0722 B). The Radiance factor 179 should not be applied.
- On-device camera calibration: absolute scale and 6th-order polynomial vignetting correction per sensor.
- Early termination of the bracket sequence when 98 % of the centre region has valid pixels; averaging of 3 frames for short brackets.
- Goal-seeking auto-exposure for AS7265x and AS7331: up to 3 iterations towards about 50,000 counts (45,000–55,000), sensors adjusted independently, best unsaturated reading kept, saturation fallback by halving the integration time. Replaces the TSL2591 power-law model from v1.0.0.
- Low-light accumulation: at maximum integration time, up to 10 AS7265x frames are summed while the sum stays below 65,535.
- Dark counts measured in situ (serial command `CAL DARK`), stored in NVS and normalised by gain and integration time.
- Wall-clock scheduling aligned to the measurement interval (default 10 min), set over MQTT (`control/wait_time`, retained). Time is UTC+1 all year.
- CSV per measurement with settings, saturation, RSSI and uptime. Files are uploaded as `.tmp` and renamed when complete, with a per-device upload stagger.
- Robustness: task watchdog (6 min), Wi-Fi/MQTT reconnect with backoff, reboot on persistent NTP/FTP failures, last crash reason published over MQTT after reboot.
- Serial command line with help (`HELP`) and a pre-deployment self-test (`TEST`).
- Firmware split into modules: `camera`, `comms`, `measurement`, `sensor_init`, `selftest`.
- Firmware version stamped from git with `02_Firmware/generate_version.ps1`.

### Utilities
- New: `spectral_gain_time_sweep`, `thermal_characterization`, `tsl_gain_integration_sweep`.
- Each utility is in its own sketch folder.

### Python suite
- HDR viewer with log scale, colormap, histogram, luminance readout and header metadata.
- Camera characterisation and calibration for multiple sensors, with export of the firmware calibration table.
- Script-relative paths and temperature correction in the cosine scripts.

## v1.0.0

Release for Kristiansen et al. (2026), "Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings", Building and Environment 294, 114364.
