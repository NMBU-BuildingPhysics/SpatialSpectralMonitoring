# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Apply calibration scale factor to HDR images for absolute luminance
# Converts relative HDR values to physically accurate cd/m² measurements
# ==============================================================================

import cv2
import numpy as np
import sys
from pathlib import Path
import argparse


def apply_calibration(hdr_path: str, scale_factor: float, output_path: str) -> bool:
    """
    Apply calibration scale factor to HDR image.
    
    Args:
        hdr_path: Input HDR file path
        scale_factor: Calibration scale factor to multiply
        output_path: Output calibrated HDR file path
    
    Returns:
        True if successful, False otherwise
    """
    print(f"Loading HDR: {hdr_path}")
    hdr = cv2.imread(hdr_path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
    if hdr is None:
        print(f"ERROR: Could not load HDR file")
        return False
    print(f"  Shape: {hdr.shape}, dtype: {hdr.dtype}")
    
    luminance_before = 0.2126 * hdr[:, :, 2] + 0.7152 * hdr[:, :, 1] + 0.0722 * hdr[:, :, 0]
    print(f"  Luminance before: [{luminance_before.min():.6f}, {luminance_before.max():.2f}]")
    
    print(f"\nApplying calibration scale factor: {scale_factor:.6f}")
    calibrated_hdr = hdr * scale_factor
    calibrated_hdr = calibrated_hdr.astype(np.float32)
    
    luminance_after = 0.2126 * calibrated_hdr[:, :, 2] + 0.7152 * calibrated_hdr[:, :, 1] + 0.0722 * calibrated_hdr[:, :, 0]
    print(f"  Luminance after:  [{luminance_after.min():.6f}, {luminance_after.max():.2f}]")
    
    print(f"\nSaving calibrated HDR to: {output_path}")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    success = cv2.imwrite(output_path, calibrated_hdr)
    
    if success:
        file_size = Path(output_path).stat().st_size
        print(f"[OK] Calibrated HDR saved ({file_size:,} bytes)")
        return True
    else:
        print("[ERROR] Failed to save calibrated HDR")
        return False


def main():
    parser = argparse.ArgumentParser(description='Apply calibration scale factor to HDR')
    parser.add_argument('--hdr', required=True, help='Input HDR file path')
    parser.add_argument('--scale', required=True, type=float, help='Calibration scale factor')
    parser.add_argument('--output', required=True, help='Output calibrated HDR file path')
    args = parser.parse_args()
    success = apply_calibration(args.hdr, args.scale, args.output)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
