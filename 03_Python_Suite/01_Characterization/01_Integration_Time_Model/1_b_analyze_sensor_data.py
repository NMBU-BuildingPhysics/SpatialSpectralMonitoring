# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Analyzes the relationship between TSL2591 Lux readings and optimal spectral integration times.
# First initial analysis script to QC merged CSV data from sweep measurements.
# ==============================================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
from pathlib import Path

base_folder = Path(__file__).parent
merged_csv_path = base_folder / "1_a_merged_data" / "master_sweep_data1.csv"
analysis_output_folder = base_folder / "1_b_analysis_plots_QC"
os.makedirs(analysis_output_folder, exist_ok=True)

def get_lux_status(lux_value):
    if np.isinf(lux_value): return 'Infinite'
    elif pd.isna(lux_value) or lux_value == '': return 'NaN'
    else: return 'Valid'

def analyze_data(filepath):
    try:
        df_raw = pd.read_csv(filepath, low_memory=False)
        print(f"Loaded {filepath}. Found {len(df_raw)} total rows.")
    except FileNotFoundError:
        print(f"ERROR: File not found at {filepath}")
        return

    if df_raw['sensor'].empty:
        print("ERROR: No sensor data found.")
        return

    sensor_order = sorted(df_raw['sensor'].unique(), key=lambda x: int(x.replace('sensor', '')))
    df_raw['sensor'] = pd.Categorical(df_raw['sensor'], categories=sensor_order, ordered=True)
    df_raw['raw_lux_numeric'] = pd.to_numeric(df_raw['raw_lux'], errors='coerce')
    df_raw['lux_status'] = df_raw['raw_lux_numeric'].apply(get_lux_status)
    
    plt.figure(figsize=(14, 8))
    sns.histplot(data=df_raw, x='sensor', hue='lux_status', multiple='stack', shrink=0.8,
                 hue_order=['Valid', 'NaN', 'Infinite'],
                 palette={'Valid': 'cornflowerblue', 'NaN': 'orange', 'Infinite': 'crimson'})
    plt.title('Data Quality: Valid, NaN, and Inf Values per Sensor', fontsize=16)
    plt.ylabel('Count'); plt.xlabel('Sensor'); plt.xticks(rotation=45, ha='right')
    plt.tight_layout(); plt.savefig(analysis_output_folder / "1_data_quality_counts.png"); plt.close()

    g = sns.displot(
        data=df_raw, x='S_time', col='sensor', hue='lux_status',
        hue_order=['Valid', 'NaN', 'Infinite'],
        palette={'Valid': 'cornflowerblue', 'NaN': 'orange', 'Infinite': 'crimson'},
        col_wrap=4, multiple='stack', kind='hist', height=4, aspect=1.2, binwidth=20, shrink=0.8
    )
    g.fig.suptitle('Data Status by S_time Setting for Each Sensor', y=1.03, fontsize=16)
    g.set_axis_labels("S_time Value", "Count"); g.set_titles("Sensor: {col_name}")
    plt.tight_layout(rect=[0, 0, 1, 0.97]); plt.savefig(analysis_output_folder / "2_s_time_breakdown.png"); plt.close(g.fig)

    df_clean = df_raw[df_raw['lux_status'] == 'Valid'].copy()
    df_clean['sensor'] = pd.Categorical(df_clean['sensor'], categories=sensor_order, ordered=True)
    df_clean['raw_lux'] = pd.to_numeric(df_clean['raw_lux'])
    ch_cols = [f'raw_ch{i}' for i in range(1, 19)]
    df_clean[ch_cols] = df_clean[ch_cols].apply(pd.to_numeric, errors='coerce')
    df_clean.dropna(subset=ch_cols + ['raw_lux'], inplace=True)
    df_clean['max_channel_value'] = df_clean[ch_cols].max(axis=1)
    print(f"Clean DataFrame: {len(df_clean)} valid rows.")

    print(f"Raw Lux Summary:\n{df_clean['raw_lux'].describe().round(2)}")
    print(f"Max Channel Summary:\n{df_clean['max_channel_value'].describe().round(2)}")

    fig, ax = plt.subplots(figsize=(15, 8))
    sns.boxplot(data=df_clean, x='sensor', y='raw_lux', ax=ax, whis=np.inf)
    ax.set_title('Raw Lux Distribution by Sensor (Whiskers: Min/Max)', fontsize=16)
    ax.set_xlabel('Sensor'); ax.set_ylabel('Raw Lux Value')
    plt.xticks(rotation=45, ha='right'); ax.grid(True, which="both", ls="--", axis='y')
    plt.tight_layout(); plt.savefig(analysis_output_folder / "3_raw_lux_distribution.png"); plt.close()

    fig, ax = plt.subplots(figsize=(15, 8))
    sns.boxplot(data=df_clean, x='sensor', y='max_channel_value', ax=ax, whis=np.inf)
    ax.set_title('Max Channel Distribution by Sensor (Whiskers: Min/Max)', fontsize=16)
    ax.set_xlabel('Sensor'); ax.set_ylabel('Max Raw Channel Value')
    plt.xticks(rotation=45, ha='right'); ax.grid(True, which="both", ls="--", axis='y')
    plt.tight_layout(); plt.savefig(analysis_output_folder / "4_max_channel_distribution.png"); plt.close()

    df_clean['rank'] = df_clean.groupby('sensor')['max_channel_value'].rank(method='first', ascending=False)
    g = sns.relplot(data=df_clean.sort_values(by=['sensor', 'rank']), x='rank', y='max_channel_value', col='sensor', col_wrap=4, kind='line', height=4, aspect=1.2)
    g.fig.suptitle('Max Channel Values per Sensor, Sorted High to Low', y=1.03, fontsize=16)
    g.set_axis_labels("Reading Index", "Max Channel Value"); g.set_titles("Sensor: {col_name}")
    plt.tight_layout(rect=[0, 0, 1, 0.97]); plt.savefig(analysis_output_folder / "5_sorted_max_channel.png"); plt.close()

    df_norm = df_clean[df_clean['raw_lux'] > 1e-6].copy()
    norm_ch_cols = []
    for col in ch_cols:
        norm_col_name = f'norm_{col}'
        df_norm[norm_col_name] = df_norm[col] / df_norm['raw_lux']
        norm_ch_cols.append(norm_col_name)
    df_melted = pd.melt(df_norm, id_vars=['sensor'], value_vars=norm_ch_cols, var_name='Channel', value_name='Normalized Response')
    df_melted['Channel'] = df_melted['Channel'].str.replace('norm_raw_', '')

    g = sns.catplot(data=df_melted, x='Channel', y='Normalized Response', col='sensor',
                    kind='box', col_wrap=3, height=5, aspect=1.5, showfliers=False,
                    order=[f'ch{i}' for i in range(1, 19)])
    g.fig.suptitle('Relative Spectral Response per Sensor', y=1.03, fontsize=16)
    g.set_axis_labels("Channel", "Normalized Response (per Lux)"); g.set_titles("Sensor: {col_name}")
    g.set_xticklabels(rotation=90); plt.tight_layout(rect=[0, 0, 1, 0.98])
    plt.savefig(analysis_output_folder / "6_spectral_response.png"); plt.close()

    df_pivot_spec = df_melted.pivot_table(index='Channel', columns='sensor', values='Normalized Response', aggfunc='mean')
    df_pivot_spec = df_pivot_spec.reindex(columns=sensor_order) 
    spectral_corr_matrix = df_pivot_spec.corr()
    print(f"Inter-Sensor Spectral Correlation:\n{spectral_corr_matrix.round(4)}")

    fig, ax = plt.subplots(figsize=(12, 10))
    sns.heatmap(spectral_corr_matrix, annot=True, cmap='viridis', fmt='.3f', linewidths=.5, ax=ax)
    ax.set_title('Inter-Sensor Spectral Response Correlation', fontsize=16)
    plt.tight_layout(); plt.savefig(analysis_output_folder / "7_spectral_correlation.png"); plt.close()

    df_clean['temperature'] = pd.to_numeric(df_clean['temperature'], errors='coerce')
    g = sns.relplot(data=df_clean.dropna(subset=['temperature']), x='temperature', y='raw_lux', col='sensor', col_wrap=4, kind='scatter', alpha=0.5, height=4, aspect=1.2)
    g.fig.suptitle('Temperature vs. Raw Lux per Sensor', y=1.03, fontsize=16)
    g.set_axis_labels("Temperature (°C)", "Raw Lux"); g.set_titles("Sensor: {col_name}")
    plt.tight_layout(rect=[0, 0, 1, 0.97]); plt.savefig(analysis_output_folder / "8_temp_vs_lux.png"); plt.close()
    
    df_clean['timestamp'] = pd.to_datetime(df_clean['date'] + ' ' + df_clean['time'], errors='coerce')
    g = sns.relplot(data=df_clean.sort_values('timestamp').dropna(subset=['timestamp']), x='timestamp', y='raw_lux', col='sensor', col_wrap=4, kind='line', height=4, aspect=1.5, facet_kws={'sharex': False})
    g.fig.suptitle('Sensor Stability: Raw Lux over Time', y=1.03, fontsize=16)
    g.set_axis_labels("Timestamp", "Raw Lux"); g.set_titles("Sensor: {col_name}")
    g.fig.autofmt_xdate(); plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.savefig(analysis_output_folder / "9_stability_over_time.png"); plt.close()


if __name__ == "__main__":
    analyze_data(str(merged_csv_path))
    print(f"\n--- Analysis complete. All plots and tables saved to '{analysis_output_folder}' subfolder. ---")