# Camera Characterization

Characterizes the OV5640 camera response for HDR luminance imaging. Generates the camera response function (CRF), merges multi-exposure images into HDR, maps luminance calibration points, and corrects vignetting.

---

## Quick Start

### Prerequisites
- Python 3.8+
- Required packages: `numpy`, `opencv-python`, `matplotlib`

Install dependencies:
```bash
pip install numpy opencv-python matplotlib
```

### Input Data
If multi exposure JPEG is used: 
- Place raw multi-exposure JPEG images in `01_define_roi_input/` before starting. Run scripts in order.
If HDR is used:
- Place HDRs in `03_generate_hdr_output/` and start from `04_map_cal_points.py`.


## Scripts

| # | Script | Purpose |
|---|--------|---------|
| 1 | `01_define_roi.py` | Interactively define an elliptical region of interest (ROI) for the camera field of view. Output saved to `01_define_roi_output/`. |
| 2 | `02_generate_response.py` | Generate the camera response function (CRF) from multi-exposure calibration images. Output saved to `02_generate_response_output/`. |
| 3 | `03_generate_hdr.py` | Merge LDR image sequences into HDR images using the CRF. Output saved to `03_generate_hdr_output/`. |
| 4 | `04_map_cal_points.py` | Map luminance calibration reference points onto HDR images for absolute luminance calibration. |
| 5 | `05_correct_vignetting.py` | Apply vignetting correction and generate corrected HDR files, correction maps, and reports. Output saved to `05_correct_vignetting_output/`. |
| 6 | `06_open_HDR_files.ps1` | PowerShell helper to open HDR files from `03_generate_hdr_output/` and `05_correct_vignetting_output/` in the HDR Viewer. |

## Output

- Calibrated HDR images (`.hdr`) with accurate absolute luminance values
- Vignetting correction map and correction report
- Camera response function curve
