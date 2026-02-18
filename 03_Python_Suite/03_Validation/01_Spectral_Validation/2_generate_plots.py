# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# This script validates sensor measurements against reference spectroradiometer data
# Visualizes the results with detailed plots for analysis.
# ==============================================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path
import json


PROJECT_ROOT = Path(__file__).parent
RESULTS_DIR = PROJECT_ROOT / "1_Results"
PLOTS_DIR = PROJECT_ROOT / "2_Analysis_plots"
MEASUREMENTS_DIR = PROJECT_ROOT / "0_Measurements"
SPD_REFERENCE_DIR = PROJECT_ROOT / "0_SPD_Reference"

VALIDATION_SOURCES = ["Daylight", "LED", "Incandescent"]

plt.style.use('seaborn-v0_8-darkgrid')
COLORS = {
    'sensor': '#E74C3C',
    'reference': '#3498DB',
    'reference_spectrum': '#95A5A6',
    'error': '#9B59B6'
}

def load_validation_results(light_source):
    csv_file = RESULTS_DIR / f"validation_{light_source}.csv"
    if not csv_file.exists():
        return None
    return pd.read_csv(csv_file)


def load_reference_spectrum(light_source):
    ref_file = MEASUREMENTS_DIR / light_source / "reference_SPD.csv"
    if not ref_file.exists():
        return None, None
    df = pd.read_csv(ref_file)
    return df.iloc[:, 0].values, df.iloc[:, 1].values


def create_comparison_plot(light_source, df_val, ref_wl, ref_intensity):
    fig = plt.figure(figsize=(16, 10))
    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.3, wspace=0.3)
    fig.suptitle(f'Spectral Validation: {light_source}', fontsize=18, fontweight='bold')
    ax1 = fig.add_subplot(gs[0, :])
    ax1_twin = ax1.twinx()
    
    ax1_twin.plot(ref_wl, ref_intensity, color=COLORS['reference_spectrum'], 
                  alpha=0.3, linewidth=1.5, label='Reference Spectrum (continuous)')
    ax1_twin.set_ylabel('Reference Spectral Irradiance (mW/m²/nm)', 
                        fontsize=11, color=COLORS['reference_spectrum'])
    ax1_twin.tick_params(axis='y', labelcolor=COLORS['reference_spectrum'])
    
    wavelengths = df_val['wavelength_nm'].values
    ax1.plot(wavelengths, df_val['sensor_irradiance'].values, 
             marker='o', linestyle='--', linewidth=2, markersize=8,
             color=COLORS['sensor'], label='Sensor (calibrated)')
    ax1.plot(wavelengths, df_val['reference_binned'].values, 
             marker='s', linestyle='-', linewidth=2, markersize=6,
             color=COLORS['reference'], alpha=0.7, label='Reference (SPD-weighted)')
    
    ax1.set_xlabel('Wavelength (nm)', fontsize=12)
    ax1.set_ylabel('Spectral Irradiance (mW/m²/nm)', fontsize=12, fontweight='bold')
    ax1.set_title('Spectral Irradiance: Sensor vs. Reference', fontsize=14)
    ax1.legend(loc='upper left', fontsize=10)
    ax1_twin.legend(loc='upper right', fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(280, 960)
    
    ax2 = fig.add_subplot(gs[1, 0])
    
    abs_errors = df_val['absolute_error'].values
    colors_bar = ['green' if abs(e) < 0.1 else 'orange' if abs(e) < 0.5 else 'red' 
                  for e in abs_errors]
    
    ax2.bar(wavelengths, abs_errors, width=15, color=colors_bar, alpha=0.7, edgecolor='black')
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax2.set_xlabel('Wavelength (nm)', fontsize=11)
    ax2.set_ylabel('Absolute Error (mW/m²/nm)', fontsize=11)
    ax2.set_title('Absolute Error by Channel', fontsize=13)
    ax2.grid(True, alpha=0.3, axis='y')
    
    ax3 = fig.add_subplot(gs[1, 1])
    
    rel_errors = df_val['relative_error_pct'].values
    colors_bar = ['green' if abs(e) < 5 else 'orange' if abs(e) < 10 else 'red' 
                  for e in rel_errors]
    
    ax3.bar(wavelengths, rel_errors, width=15, color=colors_bar, alpha=0.7, edgecolor='black')
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax3.axhline(y=5, color='green', linestyle='--', linewidth=1, alpha=0.5, label='±5%')
    ax3.axhline(y=-5, color='green', linestyle='--', linewidth=1, alpha=0.5)
    ax3.axhline(y=10, color='orange', linestyle='--', linewidth=1, alpha=0.5, label='±10%')
    ax3.axhline(y=-10, color='orange', linestyle='--', linewidth=1, alpha=0.5)
    
    ax3.set_xlabel('Wavelength (nm)', fontsize=11)
    ax3.set_ylabel('Relative Error (%)', fontsize=11)
    ax3.set_title('Relative Error by Channel', fontsize=13)
    ax3.legend(loc='best', fontsize=9)
    ax3.grid(True, alpha=0.3, axis='y')
    
    ax4 = fig.add_subplot(gs[2, 0])
    ax4.axis('off')
    
    mean_abs_rel_error = df_val['relative_error_pct'].abs().mean()
    max_abs_rel_error = df_val['relative_error_pct'].abs().max()
    rmse = np.sqrt((df_val['absolute_error']**2).mean())
    channels_within_5pct = (df_val['relative_error_pct'].abs() < 5).sum()
    channels_within_10pct = (df_val['relative_error_pct'].abs() < 10).sum()
    total_channels = len(df_val)
    
    stats_text = f"""
    VALIDATION STATISTICS
    {'─'*40}
    Mean Absolute Relative Error:  {mean_abs_rel_error:.2f}%
    Max Absolute Relative Error:   {max_abs_rel_error:.2f}%
    RMSE:                          {rmse:.4f} mW/m²/nm
    
    Channels within ±5%:           {channels_within_5pct}/{total_channels} ({channels_within_5pct/total_channels*100:.1f}%)
    Channels within ±10%:          {channels_within_10pct}/{total_channels} ({channels_within_10pct/total_channels*100:.1f}%)
    """
    
    ax4.text(0.1, 0.5, stats_text, fontsize=11, family='monospace',
             verticalalignment='center', bbox=dict(boxstyle='round', 
             facecolor='wheat', alpha=0.5))
    
    ax5 = fig.add_subplot(gs[2, 1])
    
    ax5.scatter(df_val['reference_binned'], df_val['sensor_irradiance'], 
                s=100, alpha=0.6, c=COLORS['sensor'], edgecolors='black', linewidth=1.5)
    
    max_val = max(df_val['reference_binned'].max(), df_val['sensor_irradiance'].max())
    min_val = min(df_val['reference_binned'].min(), df_val['sensor_irradiance'].min())
    ax5.plot([min_val, max_val], [min_val, max_val], 'k--', linewidth=2, label='1:1 Line')
    
    ax5.fill_between([min_val, max_val], 
                     [min_val*0.9, max_val*0.9], 
                     [min_val*1.1, max_val*1.1], 
                     alpha=0.2, color='green', label='±10%')
    
    ax5.set_xlabel('Reference (SPD-weighted) [mW/m²/nm]', fontsize=11)
    ax5.set_ylabel('Sensor (calibrated) [mW/m²/nm]', fontsize=11)
    ax5.set_title('Sensor vs. Reference Correlation', fontsize=13)
    ax5.legend(loc='upper left', fontsize=9)
    ax5.grid(True, alpha=0.3)
    ax5.set_aspect('equal', adjustable='box')
    
    return fig


def create_summary_plot(all_results):
    """Create summary comparison plot for all light sources."""
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('Validation Summary: All Light Sources', fontsize=18, fontweight='bold')
    
    light_sources = list(all_results.keys())
    colors_ls = {'LED': '#E74C3C', 'Daylight': '#F39C12', 'Incandescent': '#8E44AD'}
    
    ax = axes[0, 0]
    mean_errors = [all_results[ls]['relative_error_pct'].abs().mean() 
                   for ls in light_sources]
    bars = ax.bar(light_sources, mean_errors, color=[colors_ls.get(ls, 'gray') for ls in light_sources],
                  alpha=0.7, edgecolor='black', linewidth=2)
    ax.axhline(y=5, color='green', linestyle='--', linewidth=2, label='5% threshold')
    ax.axhline(y=10, color='orange', linestyle='--', linewidth=2, label='10% threshold')
    ax.set_ylabel('Mean Absolute Relative Error (%)', fontsize=12)
    ax.set_title('Mean Validation Error by Light Source', fontsize=14)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    for bar, val in zip(bars, mean_errors):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{val:.2f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')

    ax = axes[0, 1]
    for ls in light_sources:
        errors = all_results[ls]['relative_error_pct'].values
        ax.hist(errors, bins=15, alpha=0.5, label=ls, color=colors_ls.get(ls, 'gray'), 
                edgecolor='black')
    ax.axvline(x=0, color='black', linestyle='-', linewidth=2)
    ax.axvline(x=5, color='green', linestyle='--', linewidth=1.5)
    ax.axvline(x=-5, color='green', linestyle='--', linewidth=1.5)
    ax.set_xlabel('Relative Error (%)', fontsize=12)
    ax.set_ylabel('Frequency', fontsize=12)
    ax.set_title('Error Distribution', fontsize=14)
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    ax = axes[1, 0]
    for ls in light_sources:
        df = all_results[ls]
        ax.plot(df['wavelength_nm'], df['relative_error_pct'], 
                marker='o', linestyle='-', linewidth=2, markersize=6,
                label=ls, color=colors_ls.get(ls, 'gray'), alpha=0.7)
    ax.axhline(y=0, color='black', linestyle='-', linewidth=1)
    ax.fill_between([280, 960], -5, 5, alpha=0.2, color='green', label='±5% zone')
    ax.set_xlabel('Wavelength (nm)', fontsize=12)
    ax.set_ylabel('Relative Error (%)', fontsize=12)
    ax.set_title('Wavelength-Dependent Error', fontsize=14)
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xlim(280, 960)

    ax = axes[1, 1]
    ax.axis('off')
    
    summary_data = []
    for ls in light_sources:
        df = all_results[ls]
        mean_err = df['relative_error_pct'].abs().mean()
        max_err = df['relative_error_pct'].abs().max()
        rmse = np.sqrt((df['absolute_error']**2).mean())
        within_5 = (df['relative_error_pct'].abs() < 5).sum()
        within_10 = (df['relative_error_pct'].abs() < 10).sum()
        total = len(df)
        
        summary_data.append([
            ls,
            f"{mean_err:.2f}%",
            f"{max_err:.2f}%",
            f"{rmse:.4f}",
            f"{within_5}/{total}",
            f"{within_10}/{total}"
        ])
    
    table = ax.table(cellText=summary_data,
                    colLabels=['Source', 'Mean Err', 'Max Err', 'RMSE', 'Within 5%', 'Within 10%'],
                    cellLoc='center',
                    loc='center',
                    bbox=[0, 0, 1, 1])
    
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2)
    
    for i in range(6):
        table[(0, i)].set_facecolor('#3498DB')
        table[(0, i)].set_text_props(weight='bold', color='white')
    
    for i, ls in enumerate(light_sources, 1):
        for j in range(6):
            table[(i, j)].set_facecolor(colors_ls.get(ls, 'white'))
            table[(i, j)].set_alpha(0.3)
    
    ax.set_title('Summary Statistics', fontsize=14, pad=20)
    
    return fig

def main():
    print("="*70)
    print("GENERATING VALIDATION PLOTS")
    print("="*70)
    
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    
    all_results = {}
    
    # Generate individual plots for each light source
    for light_source in VALIDATION_SOURCES:
        print(f"\n--- Processing {light_source} ---")
        
        df_val = load_validation_results(light_source)
        if df_val is None:
            print(f"No validation results found for {light_source}, skipping")
            continue
        
        ref_wl, ref_intensity = load_reference_spectrum(light_source)
        if ref_wl is None:
            print(f"No reference spectrum found for {light_source}, skipping")
            continue
        
        fig = create_comparison_plot(light_source, df_val, ref_wl, ref_intensity)
        
        output_file = PLOTS_DIR / f"validation_{light_source}.png"
        fig.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close(fig)
        
        print(f"Saved plot: {output_file}")
        
        all_results[light_source] = df_val
    
    if all_results:
        print(f"\n--- Generating Summary Plot ---")
        fig_summary = create_summary_plot(all_results)
        output_summary = PLOTS_DIR / "validation_summary.png"
        fig_summary.savefig(output_summary, dpi=300, bbox_inches='tight')
        plt.close(fig_summary)
        print(f"Saved summary plot: {output_summary}")
    
    print(f"\n{'='*70}")
    print("PLOT GENERATION COMPLETE")
    print(f"{'='*70}")
    print(f"Plots saved to: {PLOTS_DIR}")


if __name__ == "__main__":
    main()
