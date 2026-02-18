# Sensor Libraries

This folder contains sensor-specific header and source files for the ESP32-S3 spectral sensing system.

## Included Sensors

- **TSL2591**: High-dynamic-range illuminance (lux) sensor
- **SHT4X**: Temperature and humidity sensor
- **AS7265X**: 18-channel VIS/NIR multispectral sensor (410–940 nm)
- **AS7331**: 3-channel UV sensor (UVA, UVB, UVC)

## Additional Files

- **camera_index.h**: Camera index definitions
- **camera_pins.h**: Camera pin configurations

## Usage

Include sensor libraries in your sketch as follows:

```cpp
#include "src/sensors/TSL2591.h"
#include "src/sensors/SHT4X.h"
#include "src/sensors/AS7265X.h"
#include "src/sensors/AS7331.h"
#include "src/sensors/camera_index.h"
#include "src/sensors/camera_pins.h"
```

## File Organization

Place all sensor header (`.h`) and source (`.cpp`) files in this directory. Sensor initialization and reading functions are called from `sensors.cpp` in the parent `Main/` folder.