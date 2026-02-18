# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# This script validates sensor measurements against reference spectroradiometer data
# Calculates errors and exports results for analysis.
# ==============================================================================

import pandas as pd
import numpy as np
from pathlib import Path
import json
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

PROJECT_ROOT = Path(__file__).parent
SPD_REFERENCE_DIR = PROJECT_ROOT / "0_SPD_Reference"
MEASUREMENTS_DIR = PROJECT_ROOT / "0_Measurements"
RESULTS_DIR = PROJECT_ROOT / "1_Results"
PLOTS_DIR = PROJECT_ROOT / "2_Analysis_plots"

VALIDATION_SOURCES = ["Daylight", "LED", "Incandescent"]

CALIBRATION_SOURCE = "Daylight"

SENSOR_CHANNELS = [
    {"name": "UVC", "wavelength": 260, "sensor": "AS7331"},
    {"name": "UVB", "wavelength": 300, "sensor": "AS7331"},
    {"name": "UVA", "wavelength": 360, "sensor": "AS7331"},
    {"name": "CH1", "wavelength": 410, "sensor": "AS7265x"},
    {"name": "CH2", "wavelength": 435, "sensor": "AS7265x"},
    {"name": "CH3", "wavelength": 460, "sensor": "AS7265x"},
    {"name": "CH4", "wavelength": 485, "sensor": "AS7265x"},
    {"name": "CH5", "wavelength": 510, "sensor": "AS7265x"},
    {"name": "CH6", "wavelength": 535, "sensor": "AS7265x"},
    {"name": "CH13", "wavelength": 560, "sensor": "AS7265x"},
    {"name": "CH14", "wavelength": 585, "sensor": "AS7265x"},
    {"name": "CH7", "wavelength": 610, "sensor": "AS7265x"},
    {"name": "CH15", "wavelength": 645, "sensor": "AS7265x"},
    {"name": "CH8", "wavelength": 680, "sensor": "AS7265x"},
    {"name": "CH16", "wavelength": 705, "sensor": "AS7265x"},
    {"name": "CH9", "wavelength": 730, "sensor": "AS7265x"},
    {"name": "CH10", "wavelength": 760, "sensor": "AS7265x"},
    {"name": "CH11", "wavelength": 810, "sensor": "AS7265x"},
    {"name": "CH12", "wavelength": 860, "sensor": "AS7265x"},
    {"name": "CH17", "wavelength": 900, "sensor": "AS7265x"},
    {"name": "CH18", "wavelength": 940, "sensor": "AS7265x"},
]

CALIBRATED_COLUMN_MAP = {
    "UVC": "cal_260nm",    
    "UVB": "cal_300nm",    
    "UVA": "cal_360nm",
    "CH1": "cal_410nm",
    "CH2": "cal_435nm",
    "CH3": "cal_460nm",
    "CH4": "cal_485nm",
    "CH5": "cal_510nm",
    "CH6": "cal_535nm",
    "CH13": "cal_560nm",
    "CH14": "cal_585nm",
    "CH7": "cal_610nm",
    "CH15": "cal_645nm",
    "CH8": "cal_680nm",
    "CH16": "cal_705nm",
    "CH9": "cal_730nm",
    "CH10": "cal_760nm",
    "CH11": "cal_810nm",
    "CH12": "cal_860nm",
    "CH17": "cal_900nm",
    "CH18": "cal_940nm",
}

def load_calibration_coefficients(calibration_source):
    """Load calibration coefficients from JSON file."""
    coeff_file = RESULTS_DIR / f"calibration_coefficients_{calibration_source}.json"
    
    if not coeff_file.exists():
        raise FileNotFoundError(
            f"Calibration coefficients not found: {coeff_file}\n"
            f"Please run 1_calculate_calibration_coefficients.py first."
        )
    
    with open(coeff_file, 'r') as f:
        coefficients = json.load(f)
    
    print(f"[OK] Loaded calibration coefficients from {calibration_source}")
    return coefficients

def load_sensor_responsivity_curves():
    """Load sensor SPD curves for spectral binning."""
    print("\n--- Loading Sensor Responsivity Curves ---")
    
    as7265x_file = SPD_REFERENCE_DIR / "AS7265x" / "SPD_AS7265x.csv"
    df_vis = pd.read_csv(as7265x_file)
    
    uva_file = SPD_REFERENCE_DIR / "AS7331" / "SPD_AS7331_uva.csv"
    uvb_file = SPD_REFERENCE_DIR / "AS7331" / "SPD_AS7331_uvb.csv"
    uvc_file = SPD_REFERENCE_DIR / "AS7331" / "SPD_AS7331_uvc.csv"
    
    df_uva = pd.read_csv(uva_file)
    df_uvb = pd.read_csv(uvb_file)
    df_uvc = pd.read_csv(uvc_file)
    
    responsivity = {}
    wavelengths = df_vis['Wavelength'].values
    
    for ch in SENSOR_CHANNELS:
        if ch["sensor"] == "AS7265x":
            col_name = ch["name"].lower()
            if col_name in df_vis.columns:
                responsivity[ch["name"]] = {
                    'wavelength': wavelengths,
                    'response': df_vis[col_name].values
                }
    
    responsivity["UVA"] = {
        'wavelength': df_uva['Wavelength'].values,
        'response': df_uva['uva'].values
    }
    responsivity["UVB"] = {
        'wavelength': df_uvb['Wavelength'].values,
        'response': df_uvb['uvb'].values
    }
    responsivity["UVC"] = {
        'wavelength': df_uvc['Wavelength'].values,
        'response': df_uvc['uvc'].values
    }
    
    print(f"[OK] Loaded responsivity curves for {len(responsivity)} channels")
    return responsivity


def extract_calibrated_values(light_df):
    sensor_values = {}

    for ch in SENSOR_CHANNELS:
        ch_name = ch["name"]
        col_name = CALIBRATED_COLUMN_MAP.get(ch_name)

        if col_name is None or col_name not in light_df.columns:
            continue

        light_cal = light_df[col_name].mean()

        sensor_values[ch_name] = {
            'wavelength': ch['wavelength'],
            'irradiance_mW_m2_nm': light_cal,
            'light_value': light_cal
        }

    return sensor_values

def calculate_reference_binned_irradiance(ref_wavelength, ref_intensity, responsivity):
    """Bin reference spectrum to sensor channels, and mark unsupported channels.

    Excludes channels when the reference spectrum has no usable wavelength
    coverage over the channel's responsivity band. Overlap is computed only
    within the actual reference range (min/max wavelengths where data exists).
    """
    binned_ref = {}

    nonzero = np.where(ref_intensity > 0)[0]
    if nonzero.size > 0:
        ref_min = ref_wavelength[nonzero[0]]
        ref_max = ref_wavelength[nonzero[-1]]
    else:
        ref_min = float(ref_wavelength.min())
        ref_max = float(ref_wavelength.max())


    min_resp_area = 1e-5 
    min_weighted_signal = 1e-4

    ref_mask = (ref_wavelength >= ref_min) & (ref_wavelength <= ref_max)
    rw = ref_wavelength[ref_mask]
    ri = ref_intensity[ref_mask]

    for ch in SENSOR_CHANNELS:
        ch_name = ch["name"]

        if ch_name not in responsivity:
            continue

        resp_wl = responsivity[ch_name]['wavelength']
        resp_curve = responsivity[ch_name]['response']

        resp_interp_full = np.interp(ref_wavelength, resp_wl, resp_curve, left=0.0, right=0.0)
        resp_interp = resp_interp_full[ref_mask]

        numerator = np.trapz(ri * resp_interp, rw)
        denominator = np.trapz(resp_interp, rw)

        center_in_span = (ch['wavelength'] >= ref_min) and (ch['wavelength'] <= ref_max)
        supported = center_in_span and (denominator > min_resp_area) and (abs(numerator) > min_weighted_signal)

        if supported:
            E_p_ref = numerator / denominator if denominator > 0 else 0.0
        else:
            E_p_ref = None

        binned_ref[ch_name] = {
            'wavelength': ch['wavelength'],
            'irradiance_mW_m2_nm': E_p_ref,
            'supported': supported,
            'ref_min': ref_min,
            'ref_max': ref_max
        }

    return binned_ref


def load_reference_spectrum(light_source):
    ref_file = MEASUREMENTS_DIR / light_source / "reference_SPD.csv"
    df = pd.read_csv(ref_file)
    return df.iloc[:, 0].values, df.iloc[:, 1].values


def load_sensor_measurement(light_source, measurement_type):
    filename = f"sensor_{measurement_type}.csv"
    meas_file = MEASUREMENTS_DIR / light_source / filename
    
    if not meas_file.exists():
        raise FileNotFoundError(f"Measurement file not found: {meas_file}")
    
    return pd.read_csv(meas_file)


def validate_light_source(light_source, responsivity):
    print(f"\n{'='*70}")
    print(f"VALIDATING: {light_source}")
    print(f"{'='*70}")
    
    ref_wl, ref_intensity = load_reference_spectrum(light_source)
    print(f"[OK] Loaded reference spectrum: {len(ref_wl)} points")
    
    light_df = load_sensor_measurement(light_source, "light")
    print(f"[OK] Loaded sensor measurements")
    
    sensor_results = extract_calibrated_values(light_df)
    print(f"[OK] Extracted calibrated irradiance for {len(sensor_results)} channels")
    
    ref_binned = calculate_reference_binned_irradiance(ref_wl, ref_intensity, responsivity)
    print(f"[OK] Calculated SPD-weighted reference irradiance")
    
    comparison = []
    for ch_name in sensor_results.keys():
        if ch_name not in ref_binned:
            continue
        # Skip channels with no reference support/overlap
        if not ref_binned[ch_name].get('supported', True):
            continue

        sensor_val = sensor_results[ch_name]['irradiance_mW_m2_nm']
        ref_val = ref_binned[ch_name]['irradiance_mW_m2_nm']
        wavelength = sensor_results[ch_name]['wavelength']
        
        abs_error = sensor_val - ref_val
        rel_error = (abs_error / ref_val * 100) if ref_val > 0 else 0
        
        comparison.append({
            'channel': ch_name,
            'wavelength_nm': wavelength,
            'sensor_irradiance': sensor_val,
            'reference_binned': ref_val,
            'absolute_error': abs_error,
            'relative_error_pct': rel_error
        })
    
    df_comparison = pd.DataFrame(comparison)
    
    mean_abs_error = df_comparison['relative_error_pct'].abs().mean()
    rmse = np.sqrt((df_comparison['absolute_error']**2).mean())
    
    print(f"\n Validation Statistics:")
    print(f"   Mean Absolute Relative Error: {mean_abs_error:.2f}%")
    print(f"   RMSE: {rmse:.4f} mW/m²/nm")
    
    return df_comparison, ref_wl, ref_intensity, sensor_results, ref_binned

def main():
    print("="*70)
    print("SPECTRAL VALIDATION ANALYSIS")
    print("="*70)
    
    responsivity = load_sensor_responsivity_curves()
    
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    
    all_results = {}
    
    for light_source in VALIDATION_SOURCES:
        try:
            df_comp, ref_wl, ref_int, sensor_res, ref_binned = validate_light_source(
                light_source, responsivity
            )
            
            all_results[light_source] = {
                'comparison': df_comp,
                'ref_wavelength': ref_wl,
                'ref_intensity': ref_int,
                'sensor_results': sensor_res,
                'ref_binned': ref_binned
            }
            
            output_csv = RESULTS_DIR / f"validation_{light_source}.csv"
            df_comp.to_csv(output_csv, index=False)
            print(f"[OK] Saved validation results to: {output_csv}")
            
        except FileNotFoundError as e:
            print(f"Skipping {light_source}: {e}")
            continue
    
    print(f"\n{'='*70}")
    print("VALIDATION COMPLETE")
    print(f"{'='*70}")
    print(f"\nValidated {len(all_results)} light sources")
    print(f"Results saved to: {RESULTS_DIR}")
    
    return all_results


if __name__ == "__main__":
    results = main()
