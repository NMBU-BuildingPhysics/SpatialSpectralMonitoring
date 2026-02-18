# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Vignetting Correction: Uses calibration points to measure radial luminance falloff and corrects it
# The vignetting model assumes radial symmetry from the fisheye center
# ==============================================================================

import sys
import json
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit


def find_sensor_ids(workspace: Path) -> List[str]:
    """Scan calibration points directory for sensor IDs."""
    cal_dir = workspace / '04_map_calibration_points_output'
    if not cal_dir.exists():
        raise FileNotFoundError(f"Calibration points directory not found: {cal_dir}")
    
    sensor_ids = []
    for file in cal_dir.glob('*_calibration_points.json'):
        sensor_id = file.stem.replace('_calibration_points', '')
        sensor_ids.append(sensor_id)
    
    if not sensor_ids:
        raise ValueError(f"No calibration point files found in {cal_dir}")
    
    return sorted(sensor_ids)


def load_roi_and_calibration(sensor_id: str, workspace: Path) -> Tuple[Dict, List[Dict]]:
    """Load ROI parameters and calibration points."""

    roi_file = workspace / '01_define_roi_output' / 'roi_params.json'

    if not roi_file.exists():
        raise FileNotFoundError(f"ROI file not found: {roi_file}")
    
    with open(roi_file, 'r') as f:
        all_roi_data = json.load(f)
    
    if sensor_id not in all_roi_data:
        raise ValueError(f"Sensor {sensor_id} not found in ROI parameters")
    
    roi_data = all_roi_data[sensor_id]
    
    cal_points_file = workspace / '04_map_calibration_points_output' / f'{sensor_id}_calibration_points.json'
    if not cal_points_file.exists():
        raise FileNotFoundError(f"Calibration points not found: {cal_points_file}")
    
    with open(cal_points_file, 'r') as f:
        cal_data = json.load(f)
    
    return roi_data, cal_data['points']


def calculate_radial_distances(points: List[Dict], center: Tuple[int, int]) -> np.ndarray:
    """Calculate radial distance from fisheye center for each calibration point."""
    distances = []
    for pt in points:
        dx = pt['x'] - center[0]
        dy = pt['y'] - center[1]
        r = np.sqrt(dx**2 + dy**2)
        distances.append(r)
    return np.array(distances)


def extract_hdr_values_at_points(hdr: np.ndarray, points: List[Dict]) -> np.ndarray:
    """Extract HDR luminance values at calibration points."""

    # Calculate luminance from HDR using Y = 0.2126*R + 0.7152*G + 0.0722*B
    luminance = (0.0722 * hdr[:, :, 0] +  # B
                 0.7152 * hdr[:, :, 1] +  # G
                 0.2126 * hdr[:, :, 2])   # R
    values = []
    for pt in points:
        y, x = pt['y'], pt['x']
        val = luminance[y, x]
        values.append(val)
    
    return np.array(values)


def vignetting_poly_even(r, b, c, d):
    """
    Even-power polynomial for vignetting: V(r) = 1 + b*r^2 + c*r^4 + d*r^6
    Ensures V(0) = 1.0 at center and radial symmetry.
    """
    return 1.0 + b * (r**2) + c * (r**4) + d * (r**6)


def fit_vignetting_model(distances: np.ndarray, relative_falloff: np.ndarray) -> Tuple:
    """
    Fit even-power polynomial model to vignetting falloff.
    
    Args:
        distances: Radial distances from center (pixels)
        relative_falloff: Relative luminance (1.0 at center)
    
    Returns:
        Tuple of (fitted coefficients, max_distance, polynomial function)
    """
    max_dist = distances.max()
    norm_distances = distances / max_dist
    
    try:
        popt, _ = curve_fit(vignetting_poly_even, norm_distances, relative_falloff,
                           p0=[-0.1, -0.1, -0.1])
        
        def model_func(r_norm):
            return vignetting_poly_even(r_norm, *popt)
        
        return popt, max_dist, model_func
        
    except Exception as e:
        print(f"[WARN] Curve fitting failed: {e}. Using fallback linear model.")
        coeffs = np.polyfit(norm_distances, relative_falloff, deg=1)
        poly = np.poly1d(coeffs)
        return coeffs, max_dist, poly


def create_vignetting_correction_map(shape: Tuple[int, int], 
                                     center: Tuple[int, int],
                                     model_func,
                                     max_dist: float) -> np.ndarray:
    """
    Create vignetting correction map for entire image.
    
    Args:
        shape: Image shape (height, width)
        center: Fisheye center (x, y)
        model_func: Function that maps normalized radius to vignetting factor
        max_dist: Maximum distance for normalization
    
    Returns:
        Correction map (multiply HDR by this to correct vignetting)
    """
    h, w = shape
    y, x = np.ogrid[:h, :w]
    
    dx = x - center[0]
    dy = y - center[1]
    distances = np.sqrt(dx**2 + dy**2)
    
    norm_distances = distances / max_dist
    
    vignetting_factor = model_func(norm_distances)
    
    vignetting_factor = np.clip(vignetting_factor, 0.1, 1.0)
    correction_map = 1.0 / vignetting_factor
    
    correction_map = np.clip(correction_map, 1.0, 10.0)
    
    return correction_map


def apply_vignetting_correction(hdr: np.ndarray, correction_map: np.ndarray) -> np.ndarray:
    """Apply vignetting correction to HDR image."""
    correction_3ch = np.stack([correction_map] * 3, axis=2)
    corrected_hdr = hdr * correction_3ch
    
    return corrected_hdr


def visualize_vignetting(distances: np.ndarray, 
                         measured_falloff: np.ndarray,
                         model_func,
                         max_dist: float,
                         output_path: Path):
    """Create visualization of vignetting model."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    
    norm_distances = distances / max_dist
    ax1.scatter(distances, measured_falloff, s=100, alpha=0.6, label='Measured')
    
    x_smooth = np.linspace(0, max_dist, 100)
    y_smooth = model_func(x_smooth / max_dist)
    ax1.plot(x_smooth, y_smooth, 'r-', linewidth=2, label='Fitted model')
    
    ax1.set_xlabel('Distance from Center (pixels)', fontsize=12)
    ax1.set_ylabel('Relative Luminance', fontsize=12)
    ax1.set_title('Vignetting: Measured vs Model', fontsize=14)
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim([0, 1.1])
    
    correction_factors = 1.0 / np.clip(model_func(x_smooth / max_dist), 0.1, 1.0)
    ax2.plot(x_smooth, correction_factors, 'b-', linewidth=2)
    ax2.set_xlabel('Distance from Center (pixels)', fontsize=12)
    ax2.set_ylabel('Correction Factor (multiplier)', fontsize=12)
    ax2.set_title('Vignetting Correction Applied', fontsize=14)
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5)
    ax2.set_ylim([0.9, correction_factors.max() + 0.2])
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"Vignetting visualization saved: {output_path}")


def process_sensor(sensor_id: str, workspace: Path):
    """Process vignetting correction for a single sensor."""
    print("=" * 70)
    print(f"PHASE 5: VIGNETTING CORRECTION - {sensor_id}")
    print("=" * 70)
    print()
    
    output_dir = workspace / '05_correct_vignetting_output'
    output_dir.mkdir(exist_ok=True, parents=True)
    
    print("[1/7] Loading ROI and calibration points...")
    roi_data, cal_points = load_roi_and_calibration(sensor_id, workspace)
    fisheye_center = (roi_data['center_x'], roi_data['center_y'])
    print(f"  Fisheye center: {fisheye_center}")
    print(f"  Calibration points: {len(cal_points)}")
    
    print("\n[2/7] Loading uncalibrated HDR...")
    hdr_path = workspace / '03_generate_hdr_output' / f'{sensor_id}_raw.hdr'
    hdr = cv2.imread(str(hdr_path), cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
    
    if hdr is None:
        print(f"[ERROR] Could not load HDR: {hdr_path}")
        sys.exit(1)
    
    print(f"  HDR shape: {hdr.shape}")
    print(f"  HDR range: [{hdr.min():.6f}, {hdr.max():.6f}]")
    
    print("\n[3/7] Calculating radial distances from fisheye center...")
    distances = calculate_radial_distances(cal_points, fisheye_center)
    print(f"  Distance range: [{distances.min():.1f}, {distances.max():.1f}] pixels")
    
    print("\n[4/7] Extracting HDR luminance at calibration points...")
    hdr_values = extract_hdr_values_at_points(hdr, cal_points)
    
    center_value = hdr_values[0]
    relative_falloff = hdr_values / center_value
    
    print(f"  Center HDR value: {center_value:.6f}")
    print(f"  Relative luminance range: [{relative_falloff.min():.3f}, {relative_falloff.max():.3f}]")
    print(f"  Edge falloff: {(1 - relative_falloff.min()) * 100:.1f}%")
    
    print("\n[5/7] Fitting vignetting model...")
    popt, max_dist, model_func = fit_vignetting_model(distances, relative_falloff)
    print(f"  Even-power polynomial coefficients (b, c, d): {popt}")
    print(f"  Model: V(r) = 1 + {popt[0]:.6f}*r^2 + {popt[1]:.6f}*r^4 + {popt[2]:.6f}*r^6")
    
    print("\n[6/7] Creating vignetting correction map...")
    correction_map = create_vignetting_correction_map(
        (hdr.shape[0], hdr.shape[1]),
        fisheye_center,
        model_func,
        max_dist
    )
    print(f"  Correction range: [{correction_map.min():.2f}x, {correction_map.max():.2f}x]")
    
    print("\n[7/7] Applying vignetting correction to HDR...")
    corrected_hdr = apply_vignetting_correction(hdr, correction_map)
    
    print(f"  Before correction - mean: {np.mean(hdr):.6f}")
    print(f"  After correction  - mean: {np.mean(corrected_hdr):.6f}")
    
    output_hdr = output_dir / f'{sensor_id}_vignetting_corrected.hdr'
    cv2.imwrite(str(output_hdr), corrected_hdr.astype(np.float32))
    print(f"\n  Saved: {output_hdr}")
    
    correction_map_path = output_dir / f'{sensor_id}_vignetting_correction_map.npy'
    np.save(correction_map_path, correction_map)
    print(f"  Saved: {correction_map_path}")
    
    vis_path = output_dir / f'{sensor_id}_vignetting_plot.png'
    visualize_vignetting(distances, relative_falloff, model_func, max_dist, vis_path)
    
    report = {
        'sensor_id': sensor_id,
        'input_hdr': str(hdr_path),
        'output_hdr': str(output_hdr),
        'fisheye_center': fisheye_center,
        'calibration_points_used': len(cal_points),
        'vignetting': {
            'center_hdr_value': float(center_value),
            'edge_falloff_percent': float((1 - relative_falloff.min()) * 100),
            'correction_range': {
                'min': float(correction_map.min()),
                'max': float(correction_map.max())
            },
            'polynomial_degree': len(popt) - 1,
            'polynomial_coeffs': popt.tolist()
        },
        'statistics': {
            'before_mean': float(np.mean(hdr)),
            'after_mean': float(np.mean(corrected_hdr)),
            'before_std': float(np.std(hdr)),
            'after_std': float(np.std(corrected_hdr))
        }
    }
    
    report_path = output_dir / f'{sensor_id}_vignetting_report.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"  Sav: {report_path}")
    
    print("\n" + "=" * 70)
    print("PHASE 5 COMPLETE")
    print("=" * 70)
    print(f"\nVignetting-corrected HDR: {output_hdr}")
    print(f"Edge luminance falloff: {(1 - relative_falloff.min()) * 100:.1f}%")
    print(f"Max correction applied: {correction_map.max():.2f}×")


def main():
    workspace = Path(__file__).parent.resolve()
    
    if len(sys.argv) >= 2:
        sensor_id = sys.argv[1]
        print(f"Processing single sensor: {sensor_id}\n")
        process_sensor(sensor_id, workspace)
    else:
        print("No sensor_id provided. Auto-detecting sensors from calibration points...\n")
        try:
            sensor_ids = find_sensor_ids(workspace)
            print(f"Found {len(sensor_ids)} sensor(s): {', '.join(sensor_ids)}\n")
            
            for i, sensor_id in enumerate(sensor_ids, 1):
                print(f"\n{'=' * 70}")
                print(f"Processing sensor {i}/{len(sensor_ids)}: {sensor_id}")
                print(f"{'=' * 70}\n")
                
                try:
                    process_sensor(sensor_id, workspace)
                except Exception as e:
                    print(f"\n[ERROR] Failed to process {sensor_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            print(f"\n{'=' * 70}")
            print(f"ALL SENSORS COMPLETE - Processed {len(sensor_ids)} sensor(s)")
            print(f"{'=' * 70}")
            
        except Exception as e:
            print(f"[ERROR] {e}")
            print("\nUsage:")
            print("  Auto-detect mode: python 05_correct_vignetting.py")
            print("  Single sensor:    python 05_correct_vignetting.py <sensor_id>")
            print("\nExample: python 05_correct_vignetting.py sensor11")
            sys.exit(1)


if __name__ == '__main__':
    main()


