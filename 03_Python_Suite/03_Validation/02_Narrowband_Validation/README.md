# Narrowband Validation Suite

Validation workflow for CoolLED pE-4000 multi-wavelength LED illuminator analyzing sensor response across 21 spectral channels (3× AS7331 UV + 18× AS7265x VIS-NIR). Quantifies signal purity, wavelength correspondence, and validates sensor performance against reference spectra.

## Scripts

**`1_evaluate_narrowband.py`**  
Main validation analysis comparing sensor response to narrowband reference sources. Generates signal purity metrics, wavelength correspondence plots, and comprehensive validation summaries.

**`x1_merge_SPDs.py`**  
Merges individual sensor spectral response files (AS7265x, AS7331 UV channels) into unified reference database with normalized, interpolated data on common wavelength axis (200-1100 nm).

## Directory Structure

```
0_Measurements/
    measurement_narrowband.csv          # Sensor readings for narrowband sources

0_SPD_Reference/
    lightsource_narrowband_reference.csv # Reference CoolLED pE-4000 
    AS7265x/                            # AS7265x VIS-NIR spectral response data
    AS7331/                             # AS7331 UV spectral response data (uva, uvb, uvc)

1_Analysis_plots/
    summary_plot_1_signal_purity.png               # Purity bar chart
    summary_plot_2_wavelength_correspondence.png   # Peak accuracy scatter plot
    summary_plot_3_all_in_one_grid_zoomed.png      # Comprehensive grid view
    validation_plots_Individual/                   # Per-source validation plots

1_Results/
    validation_summary.csv              # Quantitative validation metrics

x1_Analysis_Plots/
    full_sensor_response.csv            # Merged sensor response (output from x1_merge_SPDs.py)
```

## Usage

### Primary Validation Analysis
```bash
python 1_evaluate_narrowband.py
```

Reads sensor measurements and reference spectra, computes validation metrics, generates individual and summary plots.

**Inputs:**
- `0_Measurements/measurement_narrowband.csv`
- `0_SPD_Reference/lightsource_narrowband_reference.csv`

**Outputs:**
- `1_Results/validation_summary.csv`
- `1_Analysis_plots/validation_plots_Individual/*.png`
- `1_Analysis_plots/summary_plot_*.png`

### Merge Sensor Response Files
```bash
python x1_merge_SPDs.py
```

Combines AS7265x and AS7331 spectral response files into single normalized dataset.

**Inputs:**
- `0_SPD_Reference/AS7265x/SPD_AS7265x.csv`
- `0_SPD_Reference/AS7331/SPD_AS7331_uva.csv`
- `0_SPD_Reference/AS7331/SPD_AS7331_uvb.csv`
- `0_SPD_Reference/AS7331/SPD_AS7331_uvc.csv`

**Outputs:**
- `x1_Analysis_Plots/full_sensor_response.csv`

## Validation Metrics

**Signal Purity**  
Percentage of total signal captured by dominant channel: `Purity = (Max_Channel / Total_Signal) × 100%`  
High purity (>90%) indicates minimal crosstalk.

**Wavelength Correspondence**  
Compares reference peak wavelength to dominant sensor channel wavelength. Ideal correspondence shows points on diagonal line (perfect match).

**Channel Mapping**  
21 channels: uvc (260nm), uvb (300nm), uva (360nm), 410nm, 435nm, 460nm, 485nm, 510nm, 535nm, 560nm, 585nm, 610nm, 645nm, 680nm, 705nm, 730nm, 760nm, 810nm, 860nm, 900nm, 940nm

## Data Formats

**measurement_narrowband.csv**
```csv
,uvc,uvb,uva,410nm,435nm,460nm,...,940nm
365 nm,120,450,12500,80,45,...,10
385 nm,95,380,11200,75,42,...,8
```

**lightsource_narrowband_reference.csv**
```csv
Wavelength,365 nm,385 nm,435 nm,...
250,0,0,0,...
260,0,0,0,...
```

