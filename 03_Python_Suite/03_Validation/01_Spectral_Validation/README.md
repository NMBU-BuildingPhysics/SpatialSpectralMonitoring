# Spectral Validation Suite

Validation framework for multi-spectral sensor array (AS7331 UV + AS7265x VIS-NIR) implementing the absolute integrated irradiance calibration methodology. Validates sensor measurements against reference spectroradiometer data across multiple light sources with proper spectral responsivity weighting. The validation uses calibrated CSV values and excludes channels where the reference spectrum has no wavelength coverage.

## Scripts

**`1_validate_measurements.py`**  
Validates sensor measurements against reference spectroradiometer data using the calibrated CSV values directly. Bins reference spectra to sensor channels using SPD weighting restricted to the reference wavelength span and excludes unsupported channels.

Calculate calibration coefficients:
```
∫ E_ref(λ) · R_p(λ) dλ
```
Where:
- `E_ref(λ)`: Reference spectral irradiance (mW/m²/nm)
- `R_p(λ)`: Normalized spectral responsivity curve for channel p

**`2_generate_plots.py`**  
Generates validation visualizations including spectral comparisons, error analysis and correlation plots.

## Directory Structure

```
0_Measurements/
    LightSource/
        reference_SPD.csv           # Reference spectroradiometer spectrum
        sensor_light.csv            # Sensor measurement under illumination

0_SPD_Reference/
    AS7265x/
        SPD_AS7265x.csv             # VIS-NIR spectral responsivity curves
    AS7331/
        SPD_AS7331_uva.csv          # UVA spectral responsivity
        SPD_AS7331_uvb.csv          # UVB spectral responsivity
        SPD_AS7331_uvc.csv          # UVC spectral responsivity

1_Results/
    validation_LED.csv                     # Validation results for LED
    validation_Daylight.csv                # Validation results for Daylight
    validation_Incandescent.csv            # Validation results for Incandescent

2_Analysis_plots/
    validation_LED.png                     # Individual validation plot
    validation_XXX                         # For each source
    validation_summary.png                 # Summary comparison plot
```

## Usage

### Step 1: Prepare Measurement Files

Create measurement files in `0_Measurements/<LightSource>/` for each light source:

**`reference_SPD.csv`** - Reference spectroradiometer measurement:
```csv
Wavelength,Intensity
380,1.534
381,0.695
...
780,45.231
```
- Column 1: Wavelength (nm)
- Column 2: Spectral irradiance (mW/m²/nm)

**`sensor_light.csv`** - Sensor measurement under illumination:
```csv
Device,cal_260nm,cal_300nm,cal_360nm,cal_410nm,..
Sensor01,...
Sensor02,...
```

### Step 2: Validate Measurements (CSV-calibrated)

Validate using calibrated CSV values and SPD-weighted reference binning with support filtering:

```bash
python 1_validate_measurements.py
```

**Outputs:**
- `1_Results/validation_<LightSource>.csv`

### Step 3: Generate Validation Plots

Creates comprehensive visualizations:

```bash
python 3_generate_plots.py
```

**Outputs:**
- Individual plots: `validation_<LightSource>.png`
- Summary plot: `validation_summary.png`