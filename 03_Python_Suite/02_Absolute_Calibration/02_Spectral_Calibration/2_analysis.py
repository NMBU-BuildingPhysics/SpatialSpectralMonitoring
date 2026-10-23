# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Analysis and validation of spectral calibration results.
# Run 1_calibrate_sensor.py first to generate calibration_factors.csv.
#
# Plots generated:
#   A1 — C_p vs wavelength per sensor (absolute calibration coefficients)
#   A2 — Inter-sensor coefficient of variation (CV) per channel
#   A3 — Spectral resolution context: sensor SPD curves vs reference spectrum
#        (shows 5 nm reference bins vs ~20–40 nm sensor channel FWHM)
#   A4 — Calibration validation: residuals (E_est vs E_ref) per channel/device
#   A5 — Mean-only vs nearest-timestamp C_p comparison
#        (re-derives C_p using mean spectrum for ALL rows; shows impact of matching)
#   A6 — SPD_sun2000_Simulator vs SUN2000-Nano measured spectra
#        (manufacturer reference vs actual instrument measurements)
# ==============================================================================

import pandas as pd
import numpy as np
import sys
from pathlib import Path
import matplotlib.pyplot as plt

CWD = Path(__file__).parent
CORRECTION_FACTORS_DIR   = CWD / "0_Correction_Factors"
MEASUREMENTS_DIR         = CWD / "0_Measurements"
SPD_DIR                  = CWD / "0_SPD_Reference"
RESULTS_DIR              = CWD / "1_Results"
ANALYSIS_DIR             = CWD / "1_Analysis_plots"
ANALYSIS_DIR.mkdir(exist_ok=True)

TEMP_COEFFS_FILE         = CORRECTION_FACTORS_DIR / "temp_coeffs.csv"
MEASUREMENTS_FILE        = MEASUREMENTS_DIR / "sensor_data.csv"
REFERENCE_FILE           = MEASUREMENTS_DIR / "SUN2000-Nano.csv"
CALIBRATION_FACTORS_FILE = RESULTS_DIR / "calibration_factors.csv"
SPD_SUN2000_FILE = SPD_DIR / "SPD_sun2000_Simulator.csv"
AS7265X_FILE = SPD_DIR / "AS7265x" / "SPD_AS7265x.csv"
UVA_FILE     = SPD_DIR / "AS7331"  / "SPD_AS7331_uva.csv"
UVB_FILE     = SPD_DIR / "AS7331"  / "SPD_AS7331_uvb.csv"
UVC_FILE     = SPD_DIR / "AS7331"  / "SPD_AS7331_uvc.csv"

MAX_TIMESTAMP_DELTA_MINUTES = 5
CAL_S_BANK_MODE = 2

# Nominal centre wavelength per raw column key (ordered for plotting)
CHANNEL_WAVELENGTHS = {
    "raw_uvc":  260, "raw_uvb":  300, "raw_uva":  360,
    "raw_ch1":  410, "raw_ch2":  435, "raw_ch3":  460,
    "raw_ch4":  485, "raw_ch5":  510, "raw_ch6":  535,
    "raw_ch13": 560, "raw_ch14": 585, "raw_ch7":  610,
    "raw_ch15": 645, "raw_ch8":  680, "raw_ch16": 705,
    "raw_ch9":  730, "raw_ch10": 760, "raw_ch11": 810,
    "raw_ch12": 860, "raw_ch17": 900, "raw_ch18": 940,
}


def get_as7265x_time_sec(register_val, bank_mode):
    base = (register_val * 2.8) / 1000.0
    return base * 2.0 if bank_mode == 2 else base


def load_and_normalize_spd(filepaths):
    spd = {}
    for f in filepaths:
        try:
            df = pd.read_csv(f)
        except FileNotFoundError:
            print(f"ERROR: Cannot find SPD file: {f}"); sys.exit()
        wl = df.iloc[:, 0].values.astype(float)
        for col in df.columns[1:]:
            resp = df[col].values.astype(float)
            mx = resp.max()
            if mx > 0:
                resp = resp / mx
            spd[f"raw_{col.lower()}"] = (wl, resp)
    return spd


# ── Load all data ──────────────────────────────────────────────────────────────
for fpath, hint in [
    (TEMP_COEFFS_FILE,         ""),
    (MEASUREMENTS_FILE,        ""),
    (REFERENCE_FILE,           ""),
    (CALIBRATION_FACTORS_FILE, "  → Run 1_calibrate_sensor.py first"),
]:
    if not fpath.exists():
        print(f"ERROR: Cannot find '{fpath}'.{hint}"); sys.exit()

print("Loading data...")
temp_coeffs_df = pd.read_csv(TEMP_COEFFS_FILE).set_index('Channel')
temp_coeffs_df.index = temp_coeffs_df.index.str.lower()
df_meas    = pd.read_csv(MEASUREMENTS_FILE).copy()
df_ref     = pd.read_csv(REFERENCE_FILE).copy()
factors_df = pd.read_csv(CALIBRATION_FACTORS_FILE, index_col=0)
spd_dict   = load_and_normalize_spd([AS7265X_FILE, UVA_FILE, UVB_FILE, UVC_FILE])

# ── Timestamp matching (mirrors 1_calibrate_sensor.py) ────────────────────────
spec_cols        = [c for c in df_ref.columns if c.startswith('Spectrum_')]
spec_wavelengths = np.array([float(c.replace('Spectrum_', '')) for c in spec_cols])

df_ref['_ts']  = pd.to_datetime(df_ref['Modify Time'])
ref_date        = df_ref['_ts'].dt.date.iloc[0]
df_meas['_ts'] = pd.to_datetime(ref_date.strftime('%Y-%m-%d') + ' ' + df_meas['time'].str.strip())

df_ref_sorted = df_ref[['_ts'] + spec_cols].sort_values('_ts').reset_index(drop=True)
ref_merge_src = df_ref_sorted[['_ts']].rename(columns={'_ts': '_ts_ref'}).copy()
ref_merge_src['_ref_idx'] = df_ref_sorted.index

df_merged = pd.merge_asof(
    df_meas.sort_values('_ts').reset_index(drop=True),
    ref_merge_src, left_on='_ts', right_on='_ts_ref', direction='nearest')
df_merged['_delta'] = (df_merged['_ts'] - df_merged['_ts_ref']).abs()
outside   = df_merged['_delta'] > pd.Timedelta(minutes=MAX_TIMESTAMP_DELTA_MINUTES)
df_merged = df_merged.copy()
df_merged.loc[outside, '_ref_idx'] = -1  # sentinel → use mean fallback

# Pre-compute per-row and mean reference irradiance integrals
ref_mean_spectrum = df_ref_sorted[spec_cols].mean().values.astype(float)
ref_irr_maps = []
for _, ref_row in df_ref_sorted.iterrows():
    ref_spectrum = ref_row[spec_cols].values.astype(float)
    ref_irr_maps.append({
        ch: np.trapezoid(y=ref_spectrum * np.interp(spec_wavelengths, wl, resp), x=spec_wavelengths)
        for ch, (wl, resp) in spd_dict.items()
    })
ref_mean_irr_map = {
    ch: np.trapezoid(y=ref_mean_spectrum * np.interp(spec_wavelengths, wl, resp), x=spec_wavelengths)
    for ch, (wl, resp) in spd_dict.items()
}
print(f"Matched {len(df_merged)} rows, {outside.sum()} using mean-spectrum fallback")

# ── Validation: E_est vs E_ref for every row/channel ──────────────────────────
print("Computing calibration validation residuals...")
val_rows = []
for _, row in df_merged.iterrows():
    device = row['device']
    if device not in factors_df.index:
        continue
    ref_idx = int(row['_ref_idx'])
    irr_map = ref_mean_irr_map if ref_idx < 0 else ref_irr_maps[ref_idx]
    temp    = row['temperature']
    t_s     = get_as7265x_time_sec(row['S_time'], CAL_S_BANK_MODE)
    t_u     = row['U_time'] / 1000.0

    for ch in CHANNEL_WAVELENGTHS:
        if ch not in factors_df.columns:
            continue
        C_p = factors_df.loc[device, ch]
        if C_p == 0:
            continue
        is_uv = 'uv' in ch
        gain  = row['U_gain'] if is_uv else row['S_gain']
        t_int = t_u          if is_uv else t_s
        if t_int <= 0:
            continue
        S_p = row.get(ch)
        if S_p is None or pd.isna(S_p) or S_p <= 0:
            continue
        tc_key = ch.replace('raw_', '')
        if tc_key not in temp_coeffs_df.index:
            continue
        a, b, c = temp_coeffs_df.loc[tc_key, ['a', 'b', 'c']]
        f_T = a * temp**2 + b * temp + c
        if f_T == 0:
            continue
        Sp_prime = S_p / (f_T * t_int * gain)
        E_est    = C_p * Sp_prime
        E_ref    = irr_map.get(ch, 0)
        if E_ref == 0:
            continue
        val_rows.append({
            'device':        device,
            'channel':       ch,
            'wavelength_nm': CHANNEL_WAVELENGTHS[ch],
            'E_est':         E_est,
            'E_ref':         E_ref,
            'error_pct':     (E_est - E_ref) / E_ref * 100,
        })

val_df       = pd.DataFrame(val_rows)
device_names = sorted(factors_df.index.tolist())

# Only channels with non-zero C_p in at least one device
active_channels    = [ch for ch in CHANNEL_WAVELENGTHS
                      if ch in factors_df.columns and (factors_df[ch] > 0).any()]
active_wavelengths = [CHANNEL_WAVELENGTHS[ch] for ch in active_channels]
active_in_val      = [ch for ch in active_channels
                      if not val_df.empty and ch in val_df['channel'].values]

# ── Plot 1: C_p vs wavelength per sensor ──────────────────────────────────────
print("Plot 1: C_p vs wavelength...")
fig, ax = plt.subplots(figsize=(14, 6))
colors = plt.cm.tab20(np.linspace(0, 1, max(len(device_names), 1)))
for i, dev in enumerate(device_names):
    vals = [factors_df.loc[dev, ch] if ch in factors_df.columns else np.nan
            for ch in active_channels]
    vals = [v if v > 0 else np.nan for v in vals]
    ax.plot(active_wavelengths, vals, marker='o', markersize=6, linewidth=1.5,
            label=dev, color=colors[i], alpha=0.85)
ax.set_xlabel('Nominal Wavelength (nm)', fontsize=13)
ax.set_ylabel('C_p  (mW/m² per count/s)', fontsize=13)
ax.set_title('Spectral Calibration Coefficients C_p per Sensor', fontsize=15)
ax.legend(ncol=2, fontsize=9)
ax.grid(True, linestyle='--', alpha=0.5)
plt.tight_layout()
plt.savefig(ANALYSIS_DIR / 'A1_calibration_factors_vs_wavelength.png', dpi=150)
plt.close()
print("  Saved A1_calibration_factors_vs_wavelength.png")

# ── Plot 2: Inter-sensor CV per channel ───────────────────────────────────────
print("Plot 2: Inter-sensor coefficient of variation...")
cv_rows = []
for ch in active_channels:
    if ch not in factors_df.columns:
        continue
    vals = factors_df[ch].replace(0, np.nan).dropna()
    if len(vals) > 1:
        cv_rows.append({'channel': ch,
                        'wavelength_nm': CHANNEL_WAVELENGTHS[ch],
                        'cv_pct': vals.std() / vals.mean() * 100})
cv_df = pd.DataFrame(cv_rows)

fig, ax = plt.subplots(figsize=(14, 5))
bar_colors = ['#d62728' if cv > 5 else '#2ca02c' for cv in cv_df['cv_pct']]
ax.bar(cv_df['wavelength_nm'].astype(str), cv_df['cv_pct'],
       color=bar_colors, edgecolor='black', linewidth=0.5)
ax.axhline(5, color='red', linestyle='--', linewidth=1.2, label='5% threshold')
ax.set_xlabel('Nominal Wavelength (nm)', fontsize=13)
ax.set_ylabel('Coefficient of Variation (%)', fontsize=13)
ax.set_title('Inter-Sensor Variability of C_p per Channel  (red = CV > 5%)', fontsize=15)
ax.legend()
ax.grid(axis='y', linestyle='--', alpha=0.5)
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(ANALYSIS_DIR / 'A2_inter_sensor_cv.png', dpi=150)
plt.close()
print("  Saved A2_inter_sensor_cv.png")

# ── Plot 3: Spectral resolution context ───────────────────────────────────────
# The reference spectrometer outputs 5 nm bins (340–1010 nm).
# The sensor channels have FWHM of ~20–40 nm (AS7265x) or broader (AS7331).
# The convolution integral ∫ E_ref(λ)·R_p(λ) dλ is well-resolved at 5 nm.
print("Plot 3: Spectral resolution context...")
ref_mean_norm = ref_mean_spectrum / ref_mean_spectrum.max()

fig, ax = plt.subplots(figsize=(16, 7))
ax.fill_between(spec_wavelengths, ref_mean_norm, alpha=0.12, color='black')
ax.plot(spec_wavelengths, ref_mean_norm, color='black', linewidth=0.9,
        label='Mean reference spectrum (SUN2000-Nano, 5 nm bins)')

spd_colors = plt.cm.turbo(np.linspace(0, 1, len(spd_dict)))
for i, (ch_key, (wl, resp)) in enumerate(spd_dict.items()):
    nom = CHANNEL_WAVELENGTHS.get(ch_key)
    lbl = f"{nom} nm" if nom else ch_key
    ax.plot(wl, resp, linewidth=1.2, color=spd_colors[i], alpha=0.8, label=lbl)

ax.set_xlim(300, 1050)
ax.set_xlabel('Wavelength (nm)', fontsize=13)
ax.set_ylabel('Normalised Response / Irradiance', fontsize=13)
ax.set_title(
    'Sensor Channel SPD Response Curves vs Reference Spectrum\n'
    'Reference: 5 nm bins  |  Sensor channel FWHM: ~20–40 nm  →  reference fully resolves each channel',
    fontsize=13)
ax.legend(ncol=4, fontsize=8, loc='upper right')
ax.grid(True, linestyle='--', alpha=0.4)
plt.tight_layout()
plt.savefig(ANALYSIS_DIR / 'A3_spectral_resolution_context.png', dpi=150)
plt.close()
print("  Saved A3_spectral_resolution_context.png")

# ── Plot 4: Calibration validation residuals ──────────────────────────────────
print("Plot 4: Calibration validation residuals...")
if not val_df.empty and active_in_val:
    fig, axes = plt.subplots(2, 1, figsize=(16, 11),
                             gridspec_kw={'height_ratios': [2, 1]})

    # Top: per-channel box plot of residual %
    ax_top = axes[0]
    groups = [val_df[val_df['channel'] == ch]['error_pct'].values for ch in active_in_val]
    labels = [str(CHANNEL_WAVELENGTHS[ch]) for ch in active_in_val]
    ax_top.boxplot(groups, tick_labels=labels, patch_artist=True,
                   boxprops=dict(facecolor='#aec6e8', color='#333333'),
                   medianprops=dict(color='red', linewidth=2),
                   whiskerprops=dict(color='#555555'),
                   flierprops=dict(marker='.', markersize=4, alpha=0.5))
    ax_top.axhline(0,  color='black',  linewidth=0.8, linestyle='--')
    ax_top.axhline( 5, color='orange', linewidth=1,   linestyle=':', label='±5%')
    ax_top.axhline(-5, color='orange', linewidth=1,   linestyle=':')
    ax_top.set_xlabel('Nominal Wavelength (nm)', fontsize=12)
    ax_top.set_ylabel('Calibration Residual (%)\n(E_est − E_ref) / E_ref', fontsize=12)
    ax_top.set_title(
        'Per-Channel Calibration Residuals across all Measurement Rows\n'
        '(spread reflects measurement noise + light-source fluctuation; C_p is the mean)',
        fontsize=13)
    ax_top.legend(fontsize=9)
    ax_top.grid(axis='y', linestyle='--', alpha=0.5)
    plt.setp(ax_top.get_xticklabels(), rotation=45, ha='right')

    # Bottom: per-device RMSE
    ax_bot = axes[1]
    active_val = val_df[val_df['channel'].isin(active_in_val)]
    rmse_df = (active_val.groupby('device')['error_pct']
               .apply(lambda x: np.sqrt(np.mean(x**2)))
               .reset_index(name='rmse_pct'))
    ax_bot.bar(rmse_df['device'], rmse_df['rmse_pct'],
               color='#5a9bd4', edgecolor='black', linewidth=0.5)
    ax_bot.axhline(5, color='red', linestyle='--', linewidth=1.2, label='5% RMSE target')
    ax_bot.set_xlabel('Device', fontsize=12)
    ax_bot.set_ylabel('RMSE (%)', fontsize=12)
    ax_bot.set_title('Per-Device Calibration RMSE (all active channels)', fontsize=13)
    ax_bot.legend()
    ax_bot.grid(axis='y', linestyle='--', alpha=0.5)

    plt.tight_layout()
    plt.savefig(ANALYSIS_DIR / 'A4_calibration_validation.png', dpi=150)
    plt.close()
    print("  Saved A4_calibration_validation.png")
else:
    print("  No validation data — skipping.")

# ── Plot 5: Mean-only vs nearest-timestamp C_p comparison ────────────────────
# Re-derive C_p for every measurement row using ONLY the mean spectrum (no
# per-row timestamp matching).  Compare to the per-row C_p in factors_df.
# A small relative difference means timestamp-matching adds little benefit;
# a large difference reveals rows where source fluctuation matters.
print("Plot 5: Mean-only vs nearest-timestamp C_p comparison...")
mean_only_rows = []
for _, row in df_merged.iterrows():
    device = row['device']
    temp    = row['temperature']
    t_s     = get_as7265x_time_sec(row['S_time'], CAL_S_BANK_MODE)
    t_u     = row['U_time'] / 1000.0
    for ch in active_channels:
        is_uv = 'uv' in ch
        gain  = row['U_gain'] if is_uv else row['S_gain']
        t_int = t_u          if is_uv else t_s
        if t_int <= 0:
            continue
        S_p = row.get(ch)
        if S_p is None or pd.isna(S_p) or S_p <= 0:
            continue
        tc_key = ch.replace('raw_', '')
        if tc_key not in temp_coeffs_df.index:
            continue
        a, b, c = temp_coeffs_df.loc[tc_key, ['a', 'b', 'c']]
        f_T = a * temp**2 + b * temp + c
        if f_T == 0:
            continue
        Sp_prime = S_p / (f_T * t_int * gain)
        E_ref    = ref_mean_irr_map.get(ch, 0)
        if E_ref == 0 or Sp_prime == 0:
            continue
        mean_only_rows.append({'device': device, 'channel': ch, 'C_p': E_ref / Sp_prime})

mean_only_df = pd.DataFrame(mean_only_rows)
if not mean_only_df.empty:
    factors_mean_df = (mean_only_df.groupby(['device', 'channel'])['C_p']
                       .mean().unstack(level='channel'))

    # Build relative-difference table: (C_p_mean_only - C_p_ts) / C_p_ts * 100
    rel_diff_rows = []
    for ch in active_channels:
        if ch not in factors_df.columns or ch not in factors_mean_df.columns:
            continue
        for dev in device_names:
            if dev not in factors_df.index or dev not in factors_mean_df.index:
                continue
            cp_ts   = factors_df.loc[dev, ch]
            cp_mean = factors_mean_df.loc[dev, ch]
            if cp_ts > 0 and cp_mean > 0:
                rel_diff_rows.append({
                    'device':       dev,
                    'channel':      ch,
                    'wavelength_nm': CHANNEL_WAVELENGTHS[ch],
                    'rel_diff_pct': (cp_mean - cp_ts) / cp_ts * 100,
                })
    rel_diff_df = pd.DataFrame(rel_diff_rows)

    fig, axes = plt.subplots(2, 1, figsize=(16, 10),
                             gridspec_kw={'height_ratios': [2, 1]})

    # Top: per-row scatter, one colour per device
    ax_top = axes[0]
    for i, dev in enumerate(device_names):
        sub = rel_diff_df[rel_diff_df['device'] == dev]
        ax_top.plot(sub['wavelength_nm'], sub['rel_diff_pct'],
                    marker='o', markersize=6, linewidth=1.5,
                    label=dev, color=colors[i], alpha=0.85)
    ax_top.axhline(0,  color='black', linewidth=0.9, linestyle='--')
    ax_top.axhline( 2, color='orange', linewidth=1, linestyle=':', label='±2%')
    ax_top.axhline(-2, color='orange', linewidth=1, linestyle=':')
    ax_top.set_xlabel('Nominal Wavelength (nm)', fontsize=12)
    ax_top.set_ylabel('Relative C_p difference (%)\n(mean-only − timestamp) / timestamp', fontsize=12)
    ax_top.set_title(
        'Impact of Nearest-Timestamp Matching vs Mean-Spectrum Reference\n'
        'Values near 0%: mean-only is equivalent  |  Large deviation: source fluctuation matters',
        fontsize=13)
    ax_top.legend(ncol=2, fontsize=9)
    ax_top.grid(True, linestyle='--', alpha=0.5)

    # Bottom: mean ± 1 std across all devices per channel
    ax_bot = axes[1]
    grp = rel_diff_df.groupby('wavelength_nm')['rel_diff_pct']
    ch_wl  = grp.mean().index.values
    ch_mu  = grp.mean().values
    ch_std = grp.std().fillna(0).values
    ax_bot.bar(ch_wl.astype(str), ch_mu, color='#5a9bd4', edgecolor='black',
               linewidth=0.5, label='Mean across sensors')
    ax_bot.errorbar(ch_wl.astype(str), ch_mu, yerr=ch_std, fmt='none',
                    ecolor='black', elinewidth=1.2, capsize=4)
    ax_bot.axhline(0, color='black', linewidth=0.8, linestyle='--')
    ax_bot.set_xlabel('Nominal Wavelength (nm)', fontsize=12)
    ax_bot.set_ylabel('Mean rel. diff. (%)', fontsize=12)
    ax_bot.set_title('Mean relative C_p difference per channel (error bars = ±1 SD across sensors)', fontsize=12)
    ax_bot.legend()
    ax_bot.grid(axis='y', linestyle='--', alpha=0.5)
    plt.setp(ax_bot.get_xticklabels(), rotation=45, ha='right')

    plt.tight_layout()
    plt.savefig(ANALYSIS_DIR / 'A5_mean_vs_timestamp_Cp.png', dpi=150)
    plt.close()
    max_diff = rel_diff_df['rel_diff_pct'].abs().max()
    mean_diff = rel_diff_df['rel_diff_pct'].abs().mean()
    print(f"  Saved A5_mean_vs_timestamp_Cp.png  "
          f"(max |diff|={max_diff:.2f}%  mean |diff|={mean_diff:.2f}%)")
else:
    print("  No data — skipping A5.")

# ── Plot 6: SPD_sun2000_Simulator vs SUN2000-Nano measured ─────────────────────
print("Plot 6: SPD_sun2000_Simulator vs SUN2000-Nano measured spectra...")
if SPD_SUN2000_FILE.exists():
    df_sim = pd.read_csv(SPD_SUN2000_FILE)
    sim_wl  = df_sim['Wavelength'].values.astype(float)
    sim_irr = df_sim['Irradiance'].values.astype(float)

    # Normalise both in the 400-700 nm visible window for shape comparison
    vis_mask_sim  = (sim_wl  >= 400) & (sim_wl  <= 700)
    vis_mask_nano = (spec_wavelengths >= 400) & (spec_wavelengths <= 700)
    norm_sim  = sim_irr.max()  # use absolute max — visible dominates
    norm_nano = ref_mean_spectrum[vis_mask_nano].max() if vis_mask_nano.any() else ref_mean_spectrum.max()
    sim_norm  = sim_irr  / norm_sim
    nano_mean_norm = ref_mean_spectrum / norm_nano

    fig, axes = plt.subplots(2, 1, figsize=(16, 11),
                             gridspec_kw={'height_ratios': [3, 1]})

    # Top: overlay of all Nano rows + mean + simulator
    ax_top = axes[0]
    nano_rows = df_ref_sorted[spec_cols].values.astype(float)
    for i, nano_row in enumerate(nano_rows):
        ax_top.plot(spec_wavelengths, nano_row / norm_nano,
                    color='steelblue', linewidth=0.4, alpha=0.12,
                    label='SUN2000-Nano individual' if i == 0 else '')
    ax_top.plot(spec_wavelengths, nano_mean_norm,
                color='steelblue', linewidth=2.2, label='SUN2000-Nano mean')
    ax_top.plot(sim_wl, sim_norm,
                color='darkorange', linewidth=1.8, linestyle='--',
                label='SPD_sun2000_Simulator (manufacturer reference)')
    ax_top.set_xlim(300, 1100)
    ax_top.set_xlabel('Wavelength (nm)', fontsize=13)
    ax_top.set_ylabel('Normalised Irradiance  (peak in 400–700 nm = 1)', fontsize=12)
    ax_top.set_title(
        'SUN2000 Light Source: Manufacturer Simulator SPD vs SUN2000-Nano Measured Spectra\n'
        f'Nano: {len(nano_rows)} individual measurements (blue) + mean  |  Simulator: manufacturer reference (orange dashed)',
        fontsize=13)
    ax_top.legend(fontsize=10)
    ax_top.grid(True, linestyle='--', alpha=0.4)

    # Bottom: relative residual (nano_mean - sim) / sim, on the overlapping range
    ax_bot = axes[1]
    overlap_mask = (sim_wl >= spec_wavelengths.min()) & (sim_wl <= spec_wavelengths.max())
    sim_wl_ov  = sim_wl[overlap_mask]
    sim_irr_ov = sim_irr[overlap_mask]
    # Interpolate mean nano onto simulator wavelength grid for residual
    nano_on_sim = np.interp(sim_wl_ov, spec_wavelengths, ref_mean_spectrum)
    # Normalise both to 400-700 nm peak before residual so units cancel
    vis_sim_ov  = (sim_wl_ov >= 400) & (sim_wl_ov <= 700)
    if vis_sim_ov.any():
        norm_s = sim_irr_ov[vis_sim_ov].max()
        norm_n = nano_on_sim[vis_sim_ov].max()
    else:
        norm_s = sim_irr_ov.max()
        norm_n = nano_on_sim.max()
    residual_pct = ((nano_on_sim / norm_n) - (sim_irr_ov / norm_s)) / (sim_irr_ov / norm_s) * 100
    ax_bot.plot(sim_wl_ov, residual_pct, color='#555555', linewidth=1.2)
    ax_bot.fill_between(sim_wl_ov, residual_pct, 0, alpha=0.25, color='#555555')
    ax_bot.axhline(0, color='black', linewidth=0.8, linestyle='--')
    ax_bot.set_xlim(300, 1100)
    ax_bot.set_xlabel('Wavelength (nm)', fontsize=12)
    ax_bot.set_ylabel('Residual (%)\n(Nano−Sim)/Sim', fontsize=11)
    ax_bot.set_title('Shape residual: SUN2000-Nano mean vs SPD_sun2000_Simulator (normalised to visible peak)', fontsize=12)
    ax_bot.grid(True, linestyle='--', alpha=0.4)

    plt.tight_layout()
    plt.savefig(ANALYSIS_DIR / 'A6_SPD_simulator_vs_nano.png', dpi=150)
    plt.close()
    print(f"  Saved A6_SPD_simulator_vs_nano.png")
else:
    print(f"  SPD_sun2000_Simulator.csv not found at {SPD_SUN2000_FILE} — skipping A6.")

# ── Summary ────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("CALIBRATION ANALYSIS SUMMARY")
print("="*60)
print(f"  Channels calibrated:   {len(active_channels)}  "
      f"({len(CHANNEL_WAVELENGTHS) - len(active_channels)} zero-C_p, likely UV outside source range)")
print(f"  Sensors processed:     {len(device_names)}")
if not cv_df.empty:
    print(f"  Mean inter-sensor CV:  {cv_df['cv_pct'].mean():.2f}%")
    worst = cv_df.loc[cv_df['cv_pct'].idxmax()]
    print(f"  Worst CV channel:      {int(worst['wavelength_nm'])} nm  ({worst['cv_pct']:.1f}%)")
if not val_df.empty and active_in_val:
    print(f"  Overall RMSE:          {np.sqrt(np.mean(active_val['error_pct']**2)):.2f}%")
    print(f"  Mean residual:         {active_val['error_pct'].mean():.2f}%")
print("="*60)
print(f"\nPlots saved to: {ANALYSIS_DIR}")
