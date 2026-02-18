# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Apply calibration: Extracts HDR pixel values at calibration points, calculates median scale factor
# Applies calibration to generate luminance-accurate HDR image
# ==============================================================================

import numpy as np
import cv2
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
import sys


def compute_luminance(rgb: np.ndarray) -> np.ndarray:
    """
    Convert RGB to luminance coefficients.
    
    OpenCV uses BGR format, so indices are: B=0, G=1, R=2
    Formula: L = 0.2126*R + 0.7152*G + 0.0722*B
    
    Args:
        rgb: BGR image array (OpenCV format) with shape (H, W, 3)
    
    Returns:
        Luminance array with shape (H, W)
    """
    luminance = 0.2126 * rgb[:, :, 2] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 0]
   
    return luminance


def extract_hdr_values(hdr: np.ndarray, points: List[Dict[str, Any]], 
                      region_size: int = 5) -> List[float]:
    """
    Extract HDR luminance values at calibration points.
    
    Samples a region around each point to reduce noise, then computes
    average luminance in that region.
    
    Args:
        hdr: HDR image array (H, W, 3) in BGR format
        points: List of calibration points with 'x', 'y' coordinates
        region_size: Size of sampling region (must be odd)
    
    Returns:
        List of HDR luminance values at each point
    """
    if region_size % 2 == 0:
        region_size += 1
    
    half_size = region_size // 2
    height, width = hdr.shape[:2]
    hdr_values = []
    
    for point in points:
        x, y = point['x'], point['y']
        
        y_min = max(0, y - half_size)
        y_max = min(height, y + half_size + 1)
        x_min = max(0, x - half_size)
        x_max = min(width, x + half_size + 1)
        
        region = hdr[y_min:y_max, x_min:x_max, :]
        
        luminance = compute_luminance(region)
        
        hdr_value = np.mean(luminance)
        hdr_values.append(float(hdr_value))
    
    return hdr_values


def calculate_scale_factors(measured_luminances: List[float], 
                           hdr_values: List[float],
                           epsilon: float = 1e-6) -> List[float]:
    """
    Calculate scale factors for each calibration point.
    
    Formula: scale_factor = measured_luminance / hdr_value
    
    Args:
        measured_luminances: Ground truth luminance values (cd/m²)
        hdr_values: HDR luminance values at same points
        epsilon: Small value to prevent division by zero
    
    Returns:
        List of scale factors
    """
    scale_factors = []
    
    for measured, hdr_val in zip(measured_luminances, hdr_values):
        safe_hdr_val = max(abs(hdr_val), epsilon)
        scale_factor = measured / safe_hdr_val
        scale_factors.append(float(scale_factor))
    
    return scale_factors


def compute_median_scale(scale_factors: List[float], 
                        outlier_threshold: float = 2.0) -> Dict[str, Any]:
    """
    Compute median scale factor with statistics and outlier detection.
    
    Args:
        scale_factors: List of scale factors from calibration points
        outlier_threshold: Number of standard deviations for outlier detection
    
    Returns:
        Dictionary with statistics: median, mean, std_dev, min, max, outliers
    """
    scale_array = np.array(scale_factors)
    
    median_scale = float(np.median(scale_array))
    mean_scale = float(np.mean(scale_array))
    std_dev = float(np.std(scale_array))
    min_scale = float(np.min(scale_array))
    max_scale = float(np.max(scale_array))
    
    outliers = []
    for i, sf in enumerate(scale_factors):
        deviation = abs(sf - median_scale) / (std_dev + 1e-9)
        if deviation > outlier_threshold:
            outliers.append({
                "index": i,
                "scale_factor": float(sf),
                "deviation_sigma": float(deviation)
            })
    
    return {
        "median": median_scale,
        "mean": mean_scale,
        "std_dev": std_dev,
        "min": min_scale,
        "max": max_scale,
        "outliers": outliers
    }


def apply_calibration(hdr: np.ndarray, scale_factor: float) -> np.ndarray:
    """
    Apply calibration scale factor to HDR image.
    
    Args:
        hdr: Uncalibrated HDR image (H, W, 3)
        scale_factor: Median scale factor to apply
    
    Returns:
        Calibrated HDR image (H, W, 3)
    """
    calibrated = hdr * scale_factor
    return calibrated.astype(np.float32)


def calculate_validation_errors(measured_luminances: List[float],
                                hdr_values: List[float],
                                calibrated_hdr_values: List[float]) -> Dict[str, Any]:
    """
    Calculate validation errors after calibration.
    
    Args:
        measured_luminances: Ground truth luminances
        hdr_values: Original HDR values (uncalibrated)
        calibrated_hdr_values: Calibrated HDR values
    
    Returns:
        Dictionary with error statistics
    """
    errors_percent = []
    
    for measured, calibrated in zip(measured_luminances, calibrated_hdr_values):
        error_pct = abs(calibrated - measured) / measured * 100.0
        errors_percent.append(error_pct)
    
    errors_array = np.array(errors_percent)
    
    return {
        "mean_error_percent": float(np.mean(errors_array)),
        "max_error_percent": float(np.max(errors_array)),
        "min_error_percent": float(np.min(errors_array)),
        "points_within_5_percent": int(np.sum(errors_array < 5.0)),
        "points_within_10_percent": int(np.sum(errors_array < 10.0))
    }


def save_calibration_report(report: Dict[str, Any], output_path: str) -> None:
    """
    Save calibration report to JSON file.
    
    Args:
        report: Calibration report dictionary
        output_path: Path to save JSON file
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Calibration report saved to: {output_path}")


def main():
    """Main execution function for calibration."""
    script_dir = Path(__file__).parent
    input_dir = script_dir / "01_apply_calibration_input"
    
    input_dir.mkdir(parents=True, exist_ok=True)
    sensor_id = None
    
    if len(sys.argv) > 1:
        sensor_id = sys.argv[1]
    else:
        import re
        detected_sensors = set()
        
        for hdr_file in input_dir.glob("*.hdr"):
            match = re.search(r'(sensor\d+)', hdr_file.name)
            if match:
                detected_sensors.add(match.group(1))
        
        for json_file in input_dir.glob("*_calibration_points.json"):
            match = re.search(r'(sensor\d+)', json_file.name)
            if match:
                detected_sensors.add(match.group(1))
        
        for csv_file in input_dir.glob("*.csv"):
            match = re.search(r'(sensor\d+)', csv_file.name)
            if match:
                detected_sensors.add(match.group(1))
        
        if len(detected_sensors) == 1:
            sensor_id = list(detected_sensors)[0]
            print(f"Auto-detected sensor: {sensor_id}")
            print()
        elif len(detected_sensors) > 1:
            print("=" * 60)
            print("MULTIPLE SENSORS DETECTED")
            print("=" * 60)
            print()
            print(f"Found files for {len(detected_sensors)} sensors: {', '.join(sorted(detected_sensors))}")
            print()
            print("Please specify which sensor to calibrate:")
            print(f"  python 01_apply_calibration.py <sensor_id>")
            print()
            print("Example:")
            print(f"  python 01_apply_calibration.py {sorted(detected_sensors)[0]}")
            print("=" * 60)
            sys.exit(1)
        else:
            sensor_id = "sensor11"
            print(f"No sensor files detected. Using default: {sensor_id}")
            print()
    
    calibration_points_path = input_dir / f"{sensor_id}_calibration_points.json"
    
    calibration_points_path = input_dir / f"{sensor_id}_calibration_points.json"
    
    vignetting_corrected_path = input_dir / f"{sensor_id}_vignetting_corrected.hdr"
    raw_hdr_path = input_dir / f"{sensor_id}_raw.hdr"
    
    if vignetting_corrected_path.exists():
        uncalibrated_hdr_path = vignetting_corrected_path
        using_vignetting_correction = True
    else:
        uncalibrated_hdr_path = raw_hdr_path
        using_vignetting_correction = False
    
    output_dir = script_dir / "01_apply_calibration_output"
    calibrated_hdr_path = output_dir / f"{sensor_id}_calibrated.hdr"
    report_path = output_dir / f"{sensor_id}_calibration_report.json"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    csv_files = list(input_dir.glob("*.csv"))
    has_calibration_points = calibration_points_path.exists()
    has_hdr = vignetting_corrected_path.exists() or raw_hdr_path.exists()
    
    if csv_files and not has_calibration_points and has_hdr:
        print("=" * 60)
        print("SETUP REQUIRED: CALIBRATION POINTS NOT FOUND")
        print("=" * 60)
        print()
        print(f"Found in input directory:")
        print(f"  ✓ CSV file(s): {', '.join([f.name for f in csv_files])}")
        print(f"  ✓ HDR file: {vignetting_corrected_path.name if vignetting_corrected_path.exists() else raw_hdr_path.name}")
        print(f"  ✗ Calibration points JSON")
        print()
        print("NEXT STEP: Generate calibration points using the helper script")
        print()
        print("  Run this command:")
        print(f"    .\\Run_CalibrationMapping.ps1 -SensorId {sensor_id}")
        print()
        print("  This will:")
        print("  1. Load your HDR and CSV files")
        print("  2. Launch an interactive tool to mark calibration points")
        print("  3. Save the calibration points JSON to the input folder")
        print()
        print("  After generating calibration points, run this script again.")
        print("=" * 60)
        sys.exit(0)
    
    if not has_calibration_points or not has_hdr:
        print("=" * 60)
        print("MISSING REQUIRED FILES")
        print("=" * 60)
        print()
        print("Required files in input directory:")
        print()
        print(f"  1. Calibration Points JSON: {calibration_points_path.name}")
        print(f"     Status: {'✓ Found' if has_calibration_points else '✗ Missing'}")
        print()
        print(f"  2. HDR Image (one of):")
        print(f"     - {vignetting_corrected_path.name} (recommended)")
        print(f"       Status: {'✓ Found' if vignetting_corrected_path.exists() else '✗ Missing'}")
        print(f"     - {raw_hdr_path.name} (fallback)")
        print(f"       Status: {'✓ Found' if raw_hdr_path.exists() else '✗ Missing'}")
        print()
        print("OPTIONS:")
        print()
        print("  Option A: Generate new calibration points")
        print("    1. Place a CSV file with luminance values in the input folder")
        print("    2. Place an HDR file in the input folder")
        print(f"    3. Run: .\\Run_CalibrationMapping.ps1 -SensorId {sensor_id}")
        print()
        print("  Option B: Copy existing files from characterization workflow")
        print("    From: 03_Python_Suite/01_Characterization/04_Camera_Characterization/")
        print(f"    To: {input_dir.name}/")
        print()
        print("See README.md for detailed instructions.")
        print("=" * 60)
        sys.exit(1)
    
    print("=" * 60)
    print("PHASE 5: CALIBRATION SCALE FACTOR CALCULATION")
    print("=" * 60)
    print()
    if using_vignetting_correction:
        print("[INFO] Using vignetting-corrected HDR")
    else:
        print("[INFO] Using raw HDR (no vignetting correction found)")
    print()
    
    print("\n[1/6] Loading calibration points...")
    if not calibration_points_path.exists():
        print(f"ERROR: Calibration points not found at {calibration_points_path}")
        print(f"\nPlease copy the calibration points file to the input directory:")
        print(f"  From: 03_Python_Suite/01_Characterization/04_Camera_Characterization/04_map_calibration_points_output/")
        print(f"  To: {input_dir.name}/")
        sys.exit(1)
    
    with open(calibration_points_path) as f:
        calibration_data = json.load(f)
    
    points = calibration_data['points']
    sensor_id = calibration_data['sensor_id']
    print(f"  Loaded {len(points)} calibration points for {sensor_id}")
    
    print("\n[2/6] Loading uncalibrated HDR image...")
    if not uncalibrated_hdr_path.exists():
        print(f"ERROR: HDR file not found at {uncalibrated_hdr_path}")
        print(f"\nPlease copy an HDR file to the input directory:")
        print(f"  Option 1 (recommended): {sensor_id}_vignetting_corrected.hdr")
        print(f"    From: 03_Python_Suite/01_Characterization/04_Camera_Characterization/05_correct_vignetting_output/")
        print(f"  Option 2 (fallback): {sensor_id}_raw.hdr")
        print(f"    From: 03_Python_Suite/01_Characterization/04_Camera_Characterization/03_generate_hdr_output/")
        print(f"  To: {input_dir.name}/")
        sys.exit(1)
    
    hdr = cv2.imread(str(uncalibrated_hdr_path), cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
    if hdr is None:
        print(f"ERROR: Failed to load HDR file: {uncalibrated_hdr_path}")
        sys.exit(1)
    
    print(f"  HDR shape: {hdr.shape}, dtype: {hdr.dtype}")
    
    print("\n[3/6] Extracting HDR values at calibration points...")
    hdr_values = extract_hdr_values(hdr, points, region_size=5)
    
    for i, (point, hdr_val) in enumerate(zip(points, hdr_values)):
        print(f"  Point {i}: ({point['x']}, {point['y']}) -> HDR={hdr_val:.4f}")
    
    print("\n[4/6] Calculating scale factors...")
    measured_luminances = [point['luminance'] for point in points]
    scale_factors = calculate_scale_factors(measured_luminances, hdr_values)
    
    for i, sf in enumerate(scale_factors):
        print(f"  Point {i}: scale_factor = {measured_luminances[i]:.1f} / {hdr_values[i]:.4f} = {sf:.2f}")
    
    print("\n[5/6] Computing median scale factor...")
    stats = compute_median_scale(scale_factors)
    
    print(f"  Median scale: {stats['median']:.2f}")
    print(f"  Mean scale: {stats['mean']:.2f}")
    print(f"  Std dev: {stats['std_dev']:.2f}")
    print(f"  Range: [{stats['min']:.2f}, {stats['max']:.2f}]")
    
    if stats['outliers']:
        print(f"  Outliers detected: {len(stats['outliers'])}")
        for outlier in stats['outliers']:
            print(f"    Point {outlier['index']}: {outlier['scale_factor']:.2f} ({outlier['deviation_sigma']:.1f} sigma)")
    else:
        print("  No outliers detected")
    
    print("\n[6/6] Applying calibration to HDR image...")
    median_scale = stats['median']
    calibrated_hdr = apply_calibration(hdr, median_scale)
    calibrated_hdr_values = extract_hdr_values(calibrated_hdr, points, region_size=5)
    validation = calculate_validation_errors(measured_luminances, hdr_values, calibrated_hdr_values)
    
    print(f"  Mean error: {validation['mean_error_percent']:.2f}%")
    print(f"  Max error: {validation['max_error_percent']:.2f}%")
    print(f"  Points within 5%: {validation['points_within_5_percent']}/{len(points)}")
    print(f"  Points within 10%: {validation['points_within_10_percent']}/{len(points)}")
    
    print(f"\nSaving calibrated HDR to: {calibrated_hdr_path}")
    cv2.imwrite(str(calibrated_hdr_path), calibrated_hdr)
    
    print(f"Generating calibration report...")
    
    calibration_points_report = []
    for i, point in enumerate(points):
        error_pct = abs(calibrated_hdr_values[i] - measured_luminances[i]) / measured_luminances[i] * 100.0
        calibration_points_report.append({
            "id": point['id'],
            "x": point['x'],
            "y": point['y'],
            "label": point.get('label', f'Point {i}'),
            "measured_luminance": measured_luminances[i],
            "hdr_value": hdr_values[i],
            "scale_factor": scale_factors[i],
            "calibrated_hdr_value": calibrated_hdr_values[i],
            "error_percent": error_pct
        })
    
    report = {
        "sensor_id": sensor_id,
        "uncalibrated_hdr": str(uncalibrated_hdr_path),
        "calibrated_hdr": str(calibrated_hdr_path),
        "calibration_points": calibration_points_report,
        "statistics": stats,
        "validation": validation
    }
    
    save_calibration_report(report, str(report_path))
    
    print("\n" + "=" * 60)
    print("PHASE 5 COMPLETE")
    print("=" * 60)
    print(f"  Calibrated HDR: {calibrated_hdr_path.name}")
    print(f"  Median scale factor: {median_scale:.2f}")
    print(f"  Mean calibration error: {validation['mean_error_percent']:.2f}%")
    print(f"  Calibration quality: {'[OK] EXCELLENT' if validation['mean_error_percent'] < 10 else '[OK] GOOD' if validation['mean_error_percent'] < 20 else '[WARNING] FAIR'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
