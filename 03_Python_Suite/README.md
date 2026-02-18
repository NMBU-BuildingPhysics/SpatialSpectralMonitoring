# Python Analysis & Calibration Suite

This suite contains the scientific processing pipeline used to characterize, calibrate, and validate the sensor system. The folders are numbered to represent the workflow order.

## Requirements
*   Python 3.11.9 or higher
*   Libraries: `pandas`, `numpy`, `matplotlib`, `scipy`, `seaborn`, `opencv-python`, `pyserial`

### Installation
Install all required dependencies using:
```bash
pip install -r requirements.txt
```

## Workflow Overview

### 00_Utilities
Helper scripts for general data management.
- [hdr_viewer.py](00_Utilities/hdr_viewer.py) - Interactive HDR image viewer
- [merge_csv_data.py](00_Utilities/merge_csv_data.py) - CSV data consolidation utility
- [serial_data_logger.py](00_Utilities/serial_data_logger.py) - Real-time serial data capture

### 01_Characterization
Characterization of fundamental hardware behavior.
- [01_Integration_Time_Model](01_Characterization/01_Integration_Time_Model/) - Auto-exposure model generation
- [02_Thermal_Analysis](01_Characterization/02_Thermal_Analysis/) - Temperature compensation
- [03_Cosine_Correction](01_Characterization/03_Cosine_Correction/) - Angular response correction
- [04_Camera_Characterization](01_Characterization/04_Camera_Characterization/) - HDR imaging & vignetting correction

### 02_Absolute_Calibration
Derive calibration factors to convert raw counts to absolute units.
- [01_Lux_Calibration](02_Absolute_Calibration/01_Lux_Calibration/) - Illuminance calibration
- [02_Spectral_Calibration](02_Absolute_Calibration/02_Spectral_Calibration/) - Spectral irradiance calibration
- [03_Camera_Calibration](02_Absolute_Calibration/03_Camera_Calibration/) - Camera luminance calibration

### 03_Validation
Validation plots and analysis results.
- [01_Spectral_Validation](03_Validation/01_Spectral_Validation/) - Spectral validation analysis
- [02_Narrowband_Validation](03_Validation/02_Narrowband_Validation/) - Narrowband validation analysis
- [03_Camera_Validation](03_Validation/03_Camera_Validation/) - Camera luminance and illuminance validation