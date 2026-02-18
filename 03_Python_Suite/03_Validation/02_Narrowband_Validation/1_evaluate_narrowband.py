# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Narrowband validation analysis for spectral sensor calibration
# Validates sensor response against narrowband light sources and evaluates crosstalk
# ==============================================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import math

CWD = Path.cwd()
MEASUREMENTS_DIR = CWD / "0_Measurements"
SPD_DIR = CWD / "0_SPD_Reference"
RESULTS_DIR = CWD / "1_Results"
ANALYSIS_PLOTS_DIR = CWD / "1_Analysis_plots"

RESULTS_DIR.mkdir(exist_ok=True)
ANALYSIS_PLOTS_DIR.mkdir(exist_ok=True)

REFERENCE_FILE = SPD_DIR / "lightsource_narrowband_reference.csv"
SENSOR_FILE = MEASUREMENTS_DIR / "measurement_narrowband.csv"
VALIDATION_PLOTS_DIR = ANALYSIS_PLOTS_DIR / "validation_plots_Individual"
VALIDATION_PLOTS_DIR.mkdir(exist_ok=True)

CHANNEL_WAVELENGTHS = {
    'uvc': 260, 'uvb': 300, 'uva': 360, '410nm': 410, 
    '435nm': 435, '460nm': 460, '485nm': 485, '510nm': 510, 
    '535nm': 535, '560nm': 560, '585nm': 585, '610nm': 610, 
    '645nm': 645, '680nm': 680, '705nm': 705, '730nm': 730, 
    '760nm': 760, '810nm': 810, '860nm': 860, '900nm': 900, '940nm': 940
}

def load_data():
    try:
        df_ref_raw = pd.read_csv(REFERENCE_FILE, index_col=0)
        df_ref = df_ref_raw.T
        df_ref.index = df_ref.index.str.replace('nm', '').astype(float)
        df_ref.columns = df_ref.columns.astype(str).str.strip() + " nm"
        print(f"Loaded and standardized reference data for {len(df_ref.columns)} light sources.")

        df_sensor = pd.read_csv(SENSOR_FILE, index_col=0)
        df_sensor.index = df_sensor.index.str.strip()
        df_sensor = df_sensor[list(CHANNEL_WAVELENGTHS.keys())]
        print(f"Loaded and standardized sensor data for {len(df_sensor.index)} light sources.")
        
        return df_ref, df_sensor
    except FileNotFoundError as e:
        print(f"ERROR: File not found. Make sure '{e.filename}' is in the correct folder."); return None, None
    except Exception as e:
        print(f"ERROR: An unexpected error occurred while loading data: {e}"); return None, None

def analyze_and_plot_individuals(df_ref, df_sensor):
    VALIDATION_PLOTS_DIR.mkdir(exist_ok=True)
    summary_results = []
    
    common_sources = sorted(list(df_ref.columns.intersection(df_sensor.index)))
    print(f"\nFound {len(common_sources)} common light sources to analyze.")

    for source_name in common_sources:
        ref_spd = df_ref[source_name].dropna()
        sensor_response = df_sensor.loc[source_name]
        ref_spd_normalized = ref_spd / ref_spd.max() if ref_spd.max() > 0 else ref_spd
        sensor_response_normalized = sensor_response / sensor_response.max() if sensor_response.max() > 0 else sensor_response
        true_peak_wl = ref_spd_normalized.idxmax()
        winning_channel_name = sensor_response_normalized.idxmax()
        winning_channel_wl = CHANNEL_WAVELENGTHS[winning_channel_name]
        total_signal = sensor_response.sum()
        purity = (sensor_response.max() / total_signal) * 100 if total_signal > 0 else 0
        
        summary_results.append({
            'Light Source': source_name, 'True Peak (nm)': true_peak_wl,
            'Dominant Sensor Channel': winning_channel_name,
            'Dominant Channel WL (nm)': winning_channel_wl,
            'Signal Purity (%)': purity
        })
        
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(ref_spd_normalized.index, ref_spd_normalized.values, color='dodgerblue', linewidth=2, label='Reference')
        ax.bar([CHANNEL_WAVELENGTHS[ch] for ch in sensor_response_normalized.index], sensor_response_normalized.values, width=10, color='coral', alpha=0.8, label='Sensor')
        ax.set_title(f"Sensor Response to '{source_name}' Light Source", fontsize=16)
        ax.set_xlabel("Wavelength (nm)"); ax.set_ylabel("Normalized Response")
        ax.legend(); ax.grid(True, linestyle='--', alpha=0.6)
        ax.set_xlim(ref_spd_normalized.index.min() - 10, ref_spd_normalized.index.max() + 10)
        
        stats_text = (f"Source Peak: {true_peak_wl:.1f} nm\n"
                      f"Dominant Channel: {winning_channel_name} ({winning_channel_wl} nm)")
        ax.text(0.95, 0.85, stats_text, transform=ax.transAxes, fontsize=10, va='top', ha='right', bbox=dict(boxstyle='round,pad=0.5', fc='white', alpha=0.8))

        plt.tight_layout()
        plot_filename = VALIDATION_PLOTS_DIR / f"individual_validation_{source_name.replace(' ', '_').replace('nm','')}.png"
        plt.savefig(plot_filename, dpi=100); plt.close(fig)

    return pd.DataFrame(summary_results)

def create_summary_plots(summary_df):
    """Generates focused summary plots (Purity and Correspondence)."""
    if summary_df.empty: return
    summary_df = summary_df.sort_values('True Peak (nm)').reset_index(drop=True)

    print("--- Generating Summary Plot 1: Signal Purity ---")
    fig, ax = plt.subplots(figsize=(16, 8))
    bars = ax.bar(summary_df['Light Source'], summary_df['Signal Purity (%)'], color='seagreen', alpha=0.8)
    ax.set_ylim(0, 105)
    ax.axhline(100, color='black', linewidth=0.8, linestyle='--')
    ax.set_title('Sensor Signal Purity for Narrowband Sources', fontsize=18, pad=20)
    ax.set_ylabel('Signal Purity (%)', fontsize=14)
    ax.set_xlabel('Light Source', fontsize=14)
    ax.grid(True, axis='y', linestyle='--', alpha=0.7)
    
    ax.tick_params(axis='x', labelsize=14) 
    plt.setp(ax.get_xticklabels(), rotation=45, ha='right', rotation_mode='anchor')
    
    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2.0, yval + 1, f'{yval:.1f}%', ha='center', va='bottom')
    plt.tight_layout()
    plt.savefig(ANALYSIS_PLOTS_DIR / "summary_plot_1_signal_purity.png", dpi=300)
    plt.close(fig)

    print("--- Generating Summary Plot 2: Wavelength Correspondence ---")
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([350, 750], [350, 750], color='black', linestyle='--', label='Ideal Correspondence')
    ax.scatter(summary_df['True Peak (nm)'], summary_df['Dominant Channel WL (nm)'], 
           s=100, c='dodgerblue', edgecolors='black', linewidth=1.2, alpha=0.8, 
           label='Sensor Dominant Response')
    
    ax.set_xlabel('True Peak Wavelength of Light Source (nm)', fontsize=14)
    ax.set_ylabel('Central Wavelength of Dominant Sensor Channel (nm)', fontsize=14)
    ax.grid(True, linestyle='--', alpha=0.7); ax.axis('equal'); ax.legend()
    plt.tight_layout()
    plt.savefig(ANALYSIS_PLOTS_DIR / "summary_plot_2_wavelength_correspondence.png", dpi=300)
    plt.close(fig)

def create_all_in_one_summary_plot(df_ref, df_sensor, summary_df):
    """
    Generates a single figure containing a grid of all individual
    sensor response plots for a quick overview.
    (This version has dynamically zoomed x-axes for each subplot).
    """
    if summary_df.empty: return
    print("\n--- Generating All-in-One Summary Grid Plot (Zoomed In) ---")
    
    summary_df = summary_df.sort_values('True Peak (nm)').reset_index(drop=True)
    num_plots = len(summary_df)
    
    ncols = 4
    nrows = math.ceil(num_plots / ncols)
    
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 5, nrows * 4))
    axes = axes.flatten()

    for i, row in summary_df.iterrows():
        ax = axes[i]
        source_name = row['Light Source']
        
        ref_spd = df_ref[source_name].dropna()
        sensor_response = df_sensor.loc[source_name]
        
        ref_spd_normalized = ref_spd / ref_spd.max() if ref_spd.max() > 0 else ref_spd
        sensor_response_normalized = sensor_response / sensor_response.max() if sensor_response.max() > 0 else sensor_response

        ax.plot(ref_spd_normalized.index, ref_spd_normalized.values, color='dodgerblue', linewidth=2, label='Reference')
        ax.bar([CHANNEL_WAVELENGTHS[ch] for ch in sensor_response_normalized.index], 
               sensor_response_normalized.values, width=10, color='coral', alpha=0.8, label='Sensor')
        ax.set_title(f"{source_name}", fontsize=12, weight='bold')
        ax.grid(True, linestyle='--', alpha=0.6)

        ax.set_xlim(ref_spd_normalized.index.min() - 10, ref_spd_normalized.index.max() + 10)

        stats_text = (f"Peak: {row['True Peak (nm)']:.1f} nm\n"
                      f"Dominant: {row['Dominant Sensor Channel']}")
        ax.text(0.95, 0.95, stats_text, transform=ax.transAxes, fontsize=9, 
                va='top', ha='right', bbox=dict(boxstyle='round,pad=0.4', fc='white', alpha=0.7))

    for j in range(num_plots, len(axes)):
        axes[j].set_visible(False)

    fig.supxlabel("Wavelength (nm)", fontsize=16)
    fig.supylabel("Normalized Response", fontsize=16)
    fig.suptitle("Comprehensive Sensor Response to Narrowband Sources", fontsize=22, weight='bold')
    
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(ANALYSIS_PLOTS_DIR / "summary_plot_3_all_in_one_grid_zoomed.png", dpi=300)
    plt.close(fig)

if __name__ == "__main__":
    df_ref, df_sensor = load_data()
    if df_ref is not None and df_sensor is not None:
        summary_df = analyze_and_plot_individuals(df_ref, df_sensor)
        
        if not summary_df.empty:
            print("\n" + "="*90)
            print("=== NARROWBAND VALIDATION SUMMARY ===")
            print("="*90)
            summary_to_print = summary_df[['Light Source', 'True Peak (nm)', 'Dominant Sensor Channel', 'Signal Purity (%)']].copy()
            summary_to_print['True Peak (nm)'] = summary_to_print['True Peak (nm)'].round(1)
            summary_to_print['Signal Purity (%)'] = summary_to_print['Signal Purity (%)'].round(1)
            print(summary_to_print.to_string(index=False))
            print("="*90)

            summary_to_print.to_csv(RESULTS_DIR / "1_Validation_summary.csv", index=False)
            print(f"\nSummary table saved to '{RESULTS_DIR / '1_Validation_summary.csv'}'")
            
            create_summary_plots(summary_df)
            create_all_in_one_summary_plot(df_ref, df_sensor, summary_df)
            
            print("\n--- All summary plots generated successfully. ---")