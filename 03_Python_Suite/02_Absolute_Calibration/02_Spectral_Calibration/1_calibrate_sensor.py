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

CWD = Path(__file__).parent
CORRECTION_FACTORS_DIR = CWD / "0_Correction_Factors"
MEASUREMENTS_DIR = CWD / "0_Measurements"
SPD_DIR = CWD / "0_SPD_Reference"
RESULTS_DIR = CWD / "1_Results"
ANALYSIS_PLOTS_DIR = CWD / "1_Analysis_plots"

RESULTS_DIR.mkdir(exist_ok=True)
ANALYSIS_PLOTS_DIR.mkdir(exist_ok=True)
TEMP_COEFFS_FILE = CORRECTION_FACTORS_DIR / "temp_coeffs.csv"
MEASUREMENTS_FILE = MEASUREMENTS_DIR / "sensor_data.csv"
MAX_TIMESTAMP_DELTA_MINUTES = 5
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
    temp_coeffs_df = pd.read_csv(TEMP_COEFFS_FILE).set_index('Channel')
except FileNotFoundError as e:
    print(f"ERROR: Could not find a required data file. {e}")
    sys.exit()

try:
    df_meas = pd.read_csv(MEASUREMENTS_FILE).copy()
except FileNotFoundError:
    print(f"ERROR: Cannot find '{MEASUREMENTS_FILE}'."); sys.exit()
print(f"Loaded {len(df_meas)} sensor measurement rows.")

# Load reference spectrometer data
REFERENCE_FILE = MEASUREMENTS_DIR / "SUN2000-Nano.csv"
try:
    df_ref = pd.read_csv(REFERENCE_FILE).copy()
except FileNotFoundError:
    print(f"ERROR: Cannot find reference file '{REFERENCE_FILE}'."); sys.exit()
print(f"Using reference file: {REFERENCE_FILE.name} ({len(df_ref)} rows)")

response_filepaths = [AS7265X_FILE, UVA_FILE, UVB_FILE, UVC_FILE]
sensor_data_dict = load_and_normalize_responses(response_filepaths)

# Parse timestamps for nearest-match join
df_ref['_ts'] = pd.to_datetime(df_ref['Modify Time'])
ref_date = df_ref['_ts'].dt.date.iloc[0]
df_meas['_ts'] = pd.to_datetime(ref_date.strftime('%Y-%m-%d') + ' ' + df_meas['time'].str.strip())

# Reference spectrum columns and wavelengths
spec_cols = [c for c in df_ref.columns if c.startswith('Spectrum_')]
spec_wavelengths = np.array([float(c.replace('Spectrum_', '')) for c in spec_cols])
df_ref_sorted = df_ref[['_ts'] + spec_cols].sort_values('_ts').reset_index(drop=True)

# Precompute known irradiance integral for each unique reference row × channel
print("\nPre-calculating known irradiance per reference measurement...")
ref_irradiance_maps = []
for _, ref_row in df_ref_sorted.iterrows():
    ref_spectrum = ref_row[spec_cols].values.astype(float)
    irr_map = {}
    for channel, (known_wl, known_resp) in sensor_data_dict.items():
        interp_resp = np.interp(spec_wavelengths, known_wl, known_resp)
        irr_map[channel] = np.trapezoid(y=ref_spectrum * interp_resp, x=spec_wavelengths)
    ref_irradiance_maps.append(irr_map)

# Mean reference spectrum for fallback (sensors measured outside reference time window)
ref_mean_spectrum = df_ref_sorted[spec_cols].mean().values.astype(float)
ref_mean_irr_map = {}
for channel, (known_wl, known_resp) in sensor_data_dict.items():
    interp_resp = np.interp(spec_wavelengths, known_wl, known_resp)
    ref_mean_irr_map[channel] = np.trapezoid(y=ref_mean_spectrum * interp_resp, x=spec_wavelengths)

# Nearest-timestamp merge with tolerance
tolerance = pd.Timedelta(minutes=MAX_TIMESTAMP_DELTA_MINUTES)
df_ref_for_merge = df_ref_sorted[['_ts']].copy()
df_ref_for_merge['_ref_idx'] = df_ref_sorted.index
df_ref_for_merge = df_ref_for_merge.rename(columns={'_ts': '_ts_ref'})
df_meas_sorted = df_meas.sort_values('_ts').reset_index(drop=True)
df_merged = pd.merge_asof(df_meas_sorted, df_ref_for_merge, left_on='_ts', right_on='_ts_ref', direction='nearest')

df_merged['_delta'] = (df_merged['_ts'] - df_merged['_ts_ref']).abs()
outside = df_merged['_delta'] > tolerance
df_merged = df_merged.copy()
if outside.any():
    bad_devices = df_merged.loc[outside, 'device'].unique()
    print(f"WARNING: {outside.sum()} row(s) for {list(bad_devices)} have no reference within "
          f"{MAX_TIMESTAMP_DELTA_MINUTES} min — using mean reference spectrum as fallback.")
    df_merged.loc[outside, '_ref_idx'] = -1
valid_delta = df_merged.loc[~outside, '_delta']
print(f"Timestamp match — median delta: {valid_delta.median()}, max: {valid_delta.max()}")

# Iterate over each measurement row, compute C_p using its nearest reference spectrum
device_names = sorted(df_merged['device'].unique())
print(f"\nFound {len(device_names)} devices to process: {', '.join(device_names)}")
device_factors_all = {dev: {ch: [] for ch in sensor_data_dict.keys()} for dev in device_names}

temp_coeffs_df.index = temp_coeffs_df.index.str.lower()

for _, row in df_merged.iterrows():
    device = row['device']
    ref_idx = int(row['_ref_idx'])
    known_irradiance_map = ref_mean_irr_map if ref_idx < 0 else ref_irradiance_maps[ref_idx]
    temperature = row['temperature']
    cal_s_gain, cal_s_time_reg_val = row['S_gain'], row['S_time']
    cal_u_gain, cal_u_time_ms = row['U_gain'], row['U_time']
    cal_s_int_time_sec = get_as7265x_time_sec(cal_s_time_reg_val, CAL_S_BANK_MODE)
    cal_u_int_time_sec = cal_u_time_ms / 1000.0

    for channel_key in sensor_data_dict.keys():
        is_uv_channel = 'uv' in channel_key
        gain_cal = cal_u_gain if is_uv_channel else cal_s_gain
        int_time_sec_cal = cal_u_int_time_sec if is_uv_channel else cal_s_int_time_sec

        S_p = row.get(channel_key, 0)

        if int_time_sec_cal <= 0 or pd.isna(S_p) or S_p <= 0:
            continue

        key_for_temp_lookup = channel_key.replace('raw_', '')
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
        Sp_prime_net = S_p / (f_Tp * int_time_sec_cal * gain_cal)  # count/s (normalized)

        # C_p = ∫ E_ref(λ) · R_p(λ) dλ / S'_p
        # Where:
        #   E_ref = Reference spectral irradiance from spectrometer (mW/m²/nm)
        #   R_p = Normalized spectral responsivity curve of channel p (-)
        if Sp_prime_net <= 0 or known_irradiance_map[channel_key] == 0:
            continue
        C_p = known_irradiance_map[channel_key] / Sp_prime_net
        device_factors_all[device][channel_key].append(C_p)

# Average C_p per device
all_device_factors = {}
for device in device_names:
    n_rows = df_merged[df_merged['device'] == device].shape[0]
    print(f"  - {device}: averaging {n_rows} measurement rows")
    all_device_factors[device] = {}
    for channel_key, values in device_factors_all[device].items():
        valid = [v for v in values if v > 0]
        all_device_factors[device][channel_key] = float(np.mean(valid)) if valid else 0.0


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
factors_df.to_csv(RESULTS_DIR / "calibration_factors.csv")
print(f"Calibration factors saved to: {RESULTS_DIR / 'calibration_factors.csv'}")

if not factors_df.empty:
    print("\nGenerating visualizations...")

    uv_keys_for_plot = [k for k in ["raw_uvc", "raw_uvb", "raw_uva"] if k in factors_df.columns]
    uv_display_names = [k.replace('raw_', '').upper() for k in uv_keys_for_plot]
    uv_df = factors_df[uv_keys_for_plot].copy()
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

    vis_nir_keys_for_plot = [f"raw_ch{i}" for i in range(1, 19) if f"raw_ch{i}" in factors_df.columns]
    vis_nir_display_names = [k.replace('raw_', '').upper() for k in vis_nir_keys_for_plot]
    vis_nir_df = factors_df[vis_nir_keys_for_plot].copy()
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
print("="*70)