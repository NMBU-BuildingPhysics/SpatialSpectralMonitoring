# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Calculate horizontal illuminance from calibrated fisheye HDR images
# Integrates luminance over hemisphere using equidistant projection model
# ==============================================================================

import cv2
import numpy as np
import json
import sys
import argparse
from pathlib import Path


def compute_luminance(rgb_image):
    """
    Convert RGB image to luminance using ITU-R BT.709 formula.
    
    Args:
        rgb_image: RGB image (H, W, 3) in any format
        
    Returns:
        Luminance image (H, W) in cd/m²
    """
    # ITU-R BT.709 luminance weights
    # Note: OpenCV loads as BGR, so we need to reverse
    b, g, r = cv2.split(rgb_image)
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return luminance


def create_fisheye_angle_map(height, width, center_x, center_y, radius, fov_degrees=180.0):
    """
    Create zenith angle map for fisheye projection.
    
    Assumes equidistant projection: r = f × θ
    where r is radial distance in pixels, f is focal length, θ is angle
    
    Args:
        height: Image height
        width: Image width
        center_x: Fisheye center X coordinate
        center_y: Fisheye center Y coordinate
        radius: Fisheye radius in pixels (from ROI)
        fov_degrees: Field of view in degrees (default 180 for hemisphere)
        
    Returns:
        zenith_angles: Array of zenith angles (radians) for each pixel
        valid_mask: Boolean mask for pixels within fisheye circle
    """
    # Create coordinate grids
    y_coords, x_coords = np.mgrid[0:height, 0:width]
    
    # Calculate radial distance from center
    dx = x_coords - center_x
    dy = y_coords - center_y
    r_pixels = np.sqrt(dx**2 + dy**2)
    
    # Valid pixels are within fisheye radius
    valid_mask = r_pixels <= radius
    
    # Equidistant projection: θ = r / f
    # For 180° FOV hemisphere: edge of circle is at θ = π/2 (90°)
    # So: radius corresponds to π/2 radians
    # f = radius / (π/2)
    fov_radians = np.deg2rad(fov_degrees)
    max_angle = fov_radians / 2.0  # Half FOV is max zenith angle
    focal_length = radius / max_angle
    
    # Calculate zenith angle for each pixel
    zenith_angles = r_pixels / focal_length
    
    # Limit to valid FOV (0 to max_angle)
    zenith_angles = np.clip(zenith_angles, 0, max_angle)
    zenith_angles = np.clip(zenith_angles, 0, max_angle)
    
    # Mask out invalid pixels
    zenith_angles[~valid_mask] = np.nan
    
    return zenith_angles, valid_mask


def calculate_solid_angle_weights(zenith_angles, pixel_area):
    """
    Calculate solid angle weight for each pixel.
    
    For equidistant fisheye projection:
    dΩ = sin(θ) × dθ × dφ
    
    In discrete pixel form:
    dΩ ≈ sin(θ) × (Δθ × Δφ)
    
    Args:
        zenith_angles: Zenith angle array (radians)
        pixel_area: Area contribution per pixel (Δθ × Δφ)
        
    Returns:
        Solid angle weights for each pixel
    """
    # Solid angle element: dΩ = sin(θ) dθ dφ
    solid_angle = np.sin(zenith_angles) * pixel_area
    
    return solid_angle


def calculate_horizontal_illuminance(luminance_map, zenith_angles, valid_mask, pixel_solid_angle):
    """
    Calculate horizontal illuminance from luminance map.
    
    Formula: E_h = ∫∫ L(θ,φ) × cos(θ) × dΩ
    
    Args:
        luminance_map: Luminance values (cd/m²)
        zenith_angles: Zenith angle for each pixel (radians)
        valid_mask: Boolean mask for valid pixels
        pixel_solid_angle: Solid angle per pixel
        
    Returns:
        Illuminance in lux
    """
    # Cosine weighting for horizontal surface
    cos_theta = np.cos(zenith_angles)
    
    # Only integrate over valid pixels
    valid_luminance = luminance_map[valid_mask]
    valid_cos = cos_theta[valid_mask]
    valid_solid_angle = pixel_solid_angle[valid_mask]
    
    # Filter out NaN and invalid values
    valid_data = ~(np.isnan(valid_luminance) | np.isnan(valid_cos) | np.isnan(valid_solid_angle))
    
    # Integrate: E = Σ L × cos(θ) × dΩ
    illuminance = np.sum(
        valid_luminance[valid_data] * 
        valid_cos[valid_data] * 
        valid_solid_angle[valid_data]
    )
    
    return illuminance


def calculate_lux(hdr_path, center_x, center_y, radius, fov_degrees=180.0):
    """
    Calculate illuminance (lux) from calibrated HDR image.
    
    Args:
        hdr_path: Path to calibrated HDR file (in cd/m²)
        center_x: Fisheye center X coordinate
        center_y: Fisheye center Y coordinate  
        radius: Fisheye radius in pixels
        fov_degrees: Field of view in degrees
        
    Returns:
        Dictionary with illuminance results and statistics
    """
    # Load calibrated HDR
    hdr = cv2.imread(str(hdr_path), cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
    
    if hdr is None:
        raise ValueError(f"Could not load HDR image: {hdr_path}")
    
    height, width = hdr.shape[:2]
    print(f"Loaded HDR image: {width}x{height}")
    
    # Convert to luminance
    print("Converting to luminance...")
    luminance_map = compute_luminance(hdr)
    
    # Create angle map
    print("Creating fisheye angle map...")
    zenith_angles, valid_mask = create_fisheye_angle_map(
        height, width, center_x, center_y, radius, fov_degrees
    )
    
    # Calculate pixel solid angle
    # For equidistant projection with N pixels over radius:
    # Δθ = FOV / N, where N is number of pixels from center to edge
    # Δφ = 2π / (circumference in pixels) ≈ average over circle
    
    fov_radians = np.deg2rad(fov_degrees)
    delta_theta = fov_radians / radius  # Angular resolution
    
    # Approximate azimuthal resolution (average over circle)
    # At radius r, circumference = 2πr, so Δφ ≈ 2π / (2πr) = 1/r pixel
    # But we want consistent solid angle, so use average
    delta_phi = 2 * np.pi / (2 * np.pi * radius)  # Simplified for hemisphere
    
    pixel_solid_angle_base = delta_theta * delta_phi
    
    print("Calculating solid angle weights...")
    solid_angle_weights = calculate_solid_angle_weights(zenith_angles, pixel_solid_angle_base)
    
    # Calculate illuminance
    print("Integrating luminance to calculate illuminance...")
    illuminance = calculate_horizontal_illuminance(
        luminance_map, zenith_angles, valid_mask, solid_angle_weights
    )
    
    # Calculate statistics
    valid_luminance = luminance_map[valid_mask]
    valid_luminance = valid_luminance[~np.isnan(valid_luminance)]
    
    stats = {
        'horizontal_illuminance_lux': float(illuminance),
        'luminance_mean_cd_m2': float(np.mean(valid_luminance)),
        'luminance_median_cd_m2': float(np.median(valid_luminance)),
        'luminance_min_cd_m2': float(np.min(valid_luminance)),
        'luminance_max_cd_m2': float(np.max(valid_luminance)),
        'luminance_std_cd_m2': float(np.std(valid_luminance)),
        'valid_pixels': int(np.sum(valid_mask)),
        'total_pixels': int(height * width),
        'coverage_percent': float(100 * np.sum(valid_mask) / (height * width)),
        'fov_degrees': fov_degrees,
        'fisheye_center': [int(center_x), int(center_y)],
        'fisheye_radius': int(radius)
    }
    
    return stats


def load_roi_parameters(sensor_id):
    """
    Load ROI parameters for sensor from roi_params.json.
    
    Looks in 02_calibration_input first, then falls back to characterization folder.
    
    Args:
        sensor_id: Sensor identifier (e.g., 'sensor11')
        
    Returns:
        Dictionary with center_x, center_y, radius_x, radius_y
    """
    script_dir = Path(__file__).parent
    
    # First, check in 02_calibration_input folder (preferred location)
    calibration_input_dir = script_dir.parent / '02_calibration_input'
    roi_path = calibration_input_dir / 'roi_params.json'
    
    # Fallback: check in characterization folder
    if not roi_path.exists():
        characterization_dir = script_dir.parent.parent.parent / '01_Characterization' / '04_Camera_Characterization'
        roi_path = characterization_dir / '01_define_roi_output' / 'roi_params.json'
        
        if not roi_path.exists():
            raise FileNotFoundError(
                f"ROI parameters not found in:\n"
                f"  1. {calibration_input_dir / 'roi_params.json'}\n"
                f"  2. {roi_path}\n"
                f"Please copy roi_params.json to 02_calibration_input folder."
            )
    
    with open(roi_path, 'r') as f:
        roi_data = json.load(f)
    
    if sensor_id not in roi_data:
        raise ValueError(f"Sensor {sensor_id} not found in ROI parameters")
    
    return roi_data[sensor_id]


def save_lux_report(sensor_id, stats, output_path):
    """
    Save lux calculation report to JSON file.
    
    Args:
        sensor_id: Sensor identifier
        stats: Dictionary with lux statistics
        output_path: Output JSON file path
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    report = {
        'sensor_id': sensor_id,
        'lux_calculation': stats
    }
    
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Lux report saved to: {output_path}")


def main():
    """Main execution function."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Calculate illuminance from calibrated HDR')
    parser.add_argument('--hdr', required=True, help='Path to calibrated HDR file')
    parser.add_argument('--output', required=True, help='Path to output JSON report')
    parser.add_argument('--sensor-id', required=True, help='Sensor identifier (e.g., sensor11)')
    parser.add_argument('--fov', type=float, default=180.0, help='Field of view in degrees (default: 180)')
    
    args = parser.parse_args()
    
    sensor_id = args.sensor_id
    calibrated_hdr_path = Path(args.hdr)
    output_path = Path(args.output)
    fov_degrees = args.fov
    
    print("=" * 70)
    print("LUX CALCULATION FROM CALIBRATED HDR")
    print("=" * 70)
    print()
    
    # Check if calibrated HDR exists
    if not calibrated_hdr_path.exists():
        print(f"ERROR: Calibrated HDR not found: {calibrated_hdr_path}")
        sys.exit(1)
    
    # Load ROI parameters
    print(f"[1/3] Loading ROI parameters for {sensor_id}...")
    try:
        roi_params = load_roi_parameters(sensor_id)
        center_x = roi_params['center_x']
        center_y = roi_params['center_y']
        # Use average of radius_x and radius_y for circular approximation
        radius = (roi_params['radius_x'] + roi_params['radius_y']) / 2
        
        print(f"  Fisheye center: ({center_x}, {center_y})")
        print(f"  Fisheye radius: {radius:.1f} pixels")
        print(f"  Field of view: {fov_degrees}°")
    except Exception as e:
        print(f"ERROR: Could not load ROI parameters: {e}")
        sys.exit(1)
    
    # Calculate lux
    print(f"\n[2/3] Calculating illuminance from {calibrated_hdr_path.name}...")
    try:
        stats = calculate_lux(
            calibrated_hdr_path,
            center_x,
            center_y,
            radius,
            fov_degrees
        )
    except Exception as e:
        print(f"ERROR: Lux calculation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Save report
    print(f"\n[3/3] Saving lux report...")
    save_lux_report(sensor_id, stats, output_path)
    
    # Display results
    print("\n" + "=" * 70)
    print("LUX CALCULATION RESULTS")
    print("=" * 70)
    print()
    print(f"Sensor: {sensor_id}")
    print(f"Calibrated HDR: {calibrated_hdr_path.name}")
    print()
    print("ILLUMINANCE:")
    print(f"  Horizontal illuminance: {stats['horizontal_illuminance_lux']:.2f} lux")
    print()
    print("LUMINANCE STATISTICS:")
    print(f"  Mean luminance: {stats['luminance_mean_cd_m2']:.2f} cd/m²")
    print(f"  Median luminance: {stats['luminance_median_cd_m2']:.2f} cd/m²")
    print(f"  Range: [{stats['luminance_min_cd_m2']:.2f}, {stats['luminance_max_cd_m2']:.2f}] cd/m²")
    print(f"  Std deviation: {stats['luminance_std_cd_m2']:.2f} cd/m²")
    print()
    print("IMAGE INFO:")
    print(f"  Valid pixels: {stats['valid_pixels']:,} ({stats['coverage_percent']:.1f}%)")
    print(f"  FOV: {stats['fov_degrees']}°")
    print(f"  Fisheye center: {stats['fisheye_center']}")
    print(f"  Fisheye radius: {stats['fisheye_radius']} pixels")
    print()
    print("=" * 70)
    print()
    print(f"Output: {output_path}")
    print()


if __name__ == "__main__":
    main()
