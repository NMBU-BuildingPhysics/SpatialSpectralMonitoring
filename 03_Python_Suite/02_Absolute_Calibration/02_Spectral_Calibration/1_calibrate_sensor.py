# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Sensor calibration and responsivity analysis for AS7265x and AS7331 spectral sensors
# Calibrate and generates C++ calibration factor arrays for sensor firmware
# ==============================================================================

import pandas as pd
import numpy as np
import sys
from pathlib import Path
import matplotlib.pyplot as plt

CWD = Path.cwd()
CORRECTION_FACTORS_DIR = CWD / "0_Correction_Factors"
MEASUREMENTS_DIR = CWD / "0_Measurements" / "Sun2000" #Change to correct calibration source
SPD_DIR = CWD / "0_SPD_Reference"
RESULTS_DIR = CWD / "1_Results"
ANALYSIS_PLOTS_DIR = CWD / "1_Analysis_plots"

RESULTS_DIR.mkdir(exist_ok=True)
ANALYSIS_PLOTS_DIR.mkdir(exist_ok=True)
TEMP_COEFFS_FILE = CORRECTION_FACTORS_DIR / "temp_coeffs.csv"
LIGHT_COUNTS_FILE = MEASUREMENTS_DIR / "measured_counts.csv"
DARK_COUNTS_FILE = MEASUREMENTS_DIR / "measured_counts_dark.csv"
SUN2000_FILE = SPD_DIR / "Sun2000" / "SPD_sun2000_Simulator.csv"
AS7265X_FILE = SPD_DIR / "AS7265x" / "SPD_AS7265x.csv"
UVA_FILE = SPD_DIR / "AS7331" / "SPD_AS7331_uva.csv"
UVB_FILE = SPD_DIR / "AS7331" / "SPD_AS7331_uvb.csv"
UVC_FILE = SPD_DIR / "AS7331" / "SPD_AS7331_uvc.csv"

CAL_S_BANK_MODE = 2

def get_as7265x_time_sec(register_val, bank_mode):
    base_time_sec = (register_val * 2.8) / 1000.0
    return base_time_sec * 2.0 if bank_mode == 2 else base_time_sec

def load_and_normalize_responses(filepaths):
    all_responses = {}
    print("Loading and normalizing sensor response data...")
    for f in filepaths:
        try:
            df = pd.read_csv(f)
            wavelengths = df.iloc[:, 0].values
            for channel_name in df.columns[1:]:
                responses = df[channel_name].values
                max_response = np.max(responses)
                if max_response > 1.0001:
                    print(f"  - Channel '{channel_name}' from {f.name} is not normalized. Normalizing.")
                    responses = responses / max_response
                all_responses[f"raw_{channel_name.lower()}"] = (wavelengths, responses)
        except FileNotFoundError:
            print(f"ERROR: Cannot find data file: {f}"); sys.exit()
    return all_responses

print(f"Loading data from folder: {CWD}\n")
try:
    source_df = pd.read_csv(SUN2000_FILE)
    light_df = pd.read_csv(LIGHT_COUNTS_FILE)
    dark_df = pd.read_csv(DARK_COUNTS_FILE)
    temp_coeffs_df = pd.read_csv(TEMP_COEFFS_FILE).set_index('Channel')
except FileNotFoundError as e:
    print(f"ERROR: Could not find a required data file. {e}")
    sys.exit()
response_filepaths = [AS7265X_FILE, UVA_FILE, UVB_FILE, UVC_FILE]
sensor_data_dict = load_and_normalize_responses(response_filepaths)

print("\nPre-calculating known irradiance for each channel...")
target_wavelengths = source_df['Wavelength'].values
source_irradiance = source_df['Irradiance'].values
known_irradiance_map = {}
for channel, (known_wl, known_resp) in sensor_data_dict.items():
    interp_resp = np.interp(target_wavelengths, known_wl, known_resp)
    effective_irradiance = source_irradiance * interp_resp
    known_irradiance_map[channel] = np.trapz(y=effective_irradiance, x=target_wavelengths)

all_device_factors = {}
device_names = sorted(light_df['DeviceName'].unique())
print(f"\nFound {len(device_names)} devices to process: {', '.join(device_names)}")

for device in device_names:
    print(f"  - Processing {device}...")
    light_row = light_df[light_df['DeviceName'] == device]
    dark_row = dark_df[dark_df['DeviceName'] == device]
    if light_row.empty or dark_row.empty:
        continue
    
    light_data = light_row.iloc[0]
    dark_data = dark_row.iloc[0]
    temperature = light_data['temperature']
    cal_s_gain, cal_s_time_reg_val = light_data['S_gain'], light_data['S_time']
    cal_u_gain, cal_u_time_ms = light_data['U_gain'], light_data['U_time']
    cal_s_int_time_sec = get_as7265x_time_sec(cal_s_time_reg_val, CAL_S_BANK_MODE)
    cal_u_int_time_sec = cal_u_time_ms / 1000.0
    device_factors = {}
    
    for channel_key in sensor_data_dict.keys():
        is_uv_channel = 'uv' in channel_key
        gain_cal = cal_u_gain if is_uv_channel else cal_s_gain
        int_time_sec_cal = cal_u_int_time_sec if is_uv_channel else cal_s_int_time_sec
        
        S_p_light = light_data.get(channel_key, 0)
        S_p_dark = dark_data.get(channel_key, 0)
        
        if int_time_sec_cal <= 0:
            continue
        
        key_for_temp_lookup = channel_key.replace('raw_', '')
        temp_coeffs_df.index = temp_coeffs_df.index.str.lower()
        
        try:
            coeffs = temp_coeffs_df.loc[key_for_temp_lookup]
        except KeyError:
            continue
        
        a, b, c = coeffs['a'], coeffs['b'], coeffs['c']
        f_Tp = (a * temperature**2) + (b * temperature) + c
        
        if f_Tp == 0:
            continue
        
        # S'_p = S_p / (f_T,p · t_int · G)
        # Where:
        #   S_p = Measured counts in channel p (count)
        #   f_T,p = Temperature correction factor in channel p (-)
        #   t_int = Integration time in seconds (s)
        #   G = Gain factor (-)
        
        Sp_prime_light = S_p_light / (f_Tp * int_time_sec_cal * gain_cal)  # count/s (normalized)
        Sp_prime_dark = S_p_dark / (f_Tp * int_time_sec_cal * gain_cal)   # count/s (normalized)
        Sp_prime_net = Sp_prime_light - Sp_prime_dark  # count/s
        
        # C_p = ∫ E_ref(λ) · R_p(λ) dλ / (S'_p^Light - S'_p^Dark)
        # Where:
        #   E_ref = Reference spectral irradiance (mW/m²/nm)
        #   R_p = Normalized spectral responsivity curve of channel p (-)
        #   S'_p^Light = Normalized counts under light (count/s)
        #   S'_p^Dark = Normalized counts in dark (count/s)
        
        # The integral ∫ E_ref(λ) · R_p(λ) dλ is pre-calculated in known_irradiance_map
        # Units: mW/m² (since we integrate mW/m²/nm over nm)
        
        if Sp_prime_net <= 0 or known_irradiance_map[channel_key] == 0:
            C_p = 0
        else:
            C_p = known_irradiance_map[channel_key] / Sp_prime_net
        
        device_factors[channel_key] = C_p
    
    all_device_factors[device] = device_factors


cpp_output_order_keys = [
    "raw_uvc",   # 260nm (UVC)
    "raw_uvb",   # 300nm (UVB)
    "raw_uva",   # 360nm (UVA)
    "raw_ch1",   # 410nm (A)
    "raw_ch2",   # 435nm (B)
    "raw_ch3",   # 460nm (C)
    "raw_ch4",   # 485nm (D)
    "raw_ch5",   # 510nm (E)
    "raw_ch6",   # 535nm (F)
    "raw_ch13",  # 560nm (G)
    "raw_ch14",  # 585nm (H)
    "raw_ch7",   # 610nm (R)
    "raw_ch15",  # 645nm (I)
    "raw_ch8",   # 680nm (S)
    "raw_ch16",  # 705nm (J)
    "raw_ch9",   # 730nm (T)
    "raw_ch10",  # 760nm (U)
    "raw_ch11",  # 810nm (V)
    "raw_ch12",  # 860nm (W)
    "raw_ch17",  # 900nm (K)
    "raw_ch18"   # 940nm (L)
]

factors_df = pd.DataFrame(all_device_factors).T

if not factors_df.empty:
    print("\nGenerating visualizations...")
    
    uv_keys_for_plot = [f"raw_{ch.lower()}" for ch in ["UVC", "UVB", "UVA"]]
    uv_display_names = [key.replace('raw_', '').upper() for key in uv_keys_for_plot]
    uv_df = factors_df[uv_keys_for_plot]
    uv_df.columns = uv_display_names
    
    fig1, ax1 = plt.subplots(figsize=(12, 8))
    uv_df.T.plot(ax=ax1, marker='o', linestyle='-', markersize=10)
    ax1.set_title('UV Channel Calibration Coefficient Comparison', fontsize=18, pad=15)
    ax1.set_ylabel('Calibration Coefficient C_p\n(mJ/m²/count)', fontsize=12)
    ax1.set_xlabel('Sensor Channel', fontsize=12)
    ax1.grid(True, which='major', linestyle='--', linewidth=0.6)
    ax1.legend(title='Device Name')
    plt.tight_layout()
    plt.savefig(ANALYSIS_PLOTS_DIR / "calibration_coefficients_UV.png", dpi=120)
    plt.close(fig1)

    vis_nir_keys_for_plot = [f"raw_ch{i}" for i in range(1, 19)]
    vis_nir_display_names = [key.replace('raw_', '').upper() for key in vis_nir_keys_for_plot]
    vis_nir_df = factors_df[vis_nir_keys_for_plot]
    vis_nir_df.columns = vis_nir_display_names
    
    fig2, ax2 = plt.subplots(figsize=(20, 10))
    vis_nir_df.T.plot(ax=ax2, marker='o', linestyle='-', markersize=6, alpha=0.8)
    ax2.set_title('VIS-NIR Channel Calibration Coefficient Comparison', fontsize=20, pad=20)
    ax2.set_ylabel('Calibration Coefficient C_p\n(mJ/m²/count)', fontsize=14)
    ax2.set_xlabel('Sensor Channel', fontsize=14, labelpad=15)
    ax2.set_xticks(range(len(vis_nir_display_names)))
    ax2.set_xticklabels(vis_nir_display_names, rotation=45, ha='right')
    ax2.grid(True, which='major', axis='y', linestyle='--', linewidth=0.7)
    ax2.legend(title='Device Name', bbox_to_anchor=(1.01, 1), loc='upper left')
    plt.tight_layout(rect=[0, 0, 0.92, 1])
    plt.savefig(ANALYSIS_PLOTS_DIR / "calibration_coefficients_VIS_NIR.png", dpi=150)
    plt.close(fig2)

else:
    print("No data to plot. Skipping visualization.")

cpp_lines = []
comment_header_labels = [key.replace('raw_', '') for key in cpp_output_order_keys]
comment_line = "// " + ", ".join(comment_header_labels)

for device_name in device_names:
    if device_name in all_device_factors:
        factors = all_device_factors[device_name]
        formatted_factors = [f"{factors.get(ch, 0.0):.5f}f" for ch in cpp_output_order_keys]
        cpp_lines.append(f'    {{"{device_name}",    {{{", ".join(formatted_factors)}}}}},')

cpp_code_block = "constexpr CalibrationFactorSet factorData[] = {\n"
cpp_code_block += f"    {comment_line}\n"
cpp_code_block += "\n".join(cpp_lines)
cpp_code_block += "\n};"

print("\nGenerating C++ code dump: calibration_results.txt")
with open(RESULTS_DIR / "calibration_results.txt", "w") as f:
    f.write("="*70 + "\nAUTOMATICALLY GENERATED C++ CALIBRATION COEFFICIENTS (C_p)\n" + "="*70 + "\n\n")
    f.write("// These are the calibration coefficients C_p from Equation 3\n")
    f.write("// Units: mJ/m²/count (or equivalently mW/m² per count/s)\n")
    f.write("// To convert sensor counts to irradiance: E = C_p × S'_p\n\n")
    f.write(cpp_code_block)

print(f"Results saved to: {RESULTS_DIR / 'calibration_results.txt'}")

print("\n\n" + "="*70)
print("=== COMPLETE C++ CALIBRATION COEFFICIENT ARRAY (Eq. 3) ===")
print("="*70)
print(cpp_code_block)
print("\n" + "="*70)