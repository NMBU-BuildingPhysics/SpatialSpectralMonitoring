# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Apply pre-computed vignetting correction map to HDR images
# Multiplies each channel by correction factor to compensate for lens falloff
# ==============================================================================

import cv2
import numpy as np
import sys
from pathlib import Path
import argparse


def apply_vignetting_correction(hdr_path: str, correction_map_path: str, output_path: str) -> bool:
    """
    Apply vignetting correction to HDR image.
    
    Args:
        hdr_path: Input HDR file path
        correction_map_path: Vignetting correction map (.npy file)
        output_path: Output corrected HDR file path
    
    Returns:
        True if successful, False otherwise
    """
    print(f"Loading HDR: {hdr_path}")
    hdr = cv2.imread(hdr_path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
    if hdr is None:
        print(f"ERROR: Could not load HDR file")
        return False
    print(f"  Shape: {hdr.shape}, dtype: {hdr.dtype}")
    
    print(f"\nLoading correction map: {correction_map_path}")
    correction_map = np.load(correction_map_path)
    print(f"  Shape: {correction_map.shape}, dtype: {correction_map.dtype}")
    print(f"  Range: [{correction_map.min():.3f}, {correction_map.max():.3f}]")
    
    print("\nApplying vignetting correction...")
    correction_3ch = np.stack([correction_map] * 3, axis=2)
    corrected_hdr = hdr * correction_3ch
    corrected_hdr = corrected_hdr.astype(np.float32)
    
    luminance_before = 0.2126 * hdr[:, :, 2] + 0.7152 * hdr[:, :, 1] + 0.0722 * hdr[:, :, 0]
    luminance_after = 0.2126 * corrected_hdr[:, :, 2] + 0.7152 * corrected_hdr[:, :, 1] + 0.0722 * corrected_hdr[:, :, 0]
    print(f"  Luminance before: [{luminance_before.min():.6f}, {luminance_before.max():.2f}]")
    print(f"  Luminance after:  [{luminance_after.min():.6f}, {luminance_after.max():.2f}]")
    
    print(f"\nSaving corrected HDR to: {output_path}")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    success = cv2.imwrite(output_path, corrected_hdr)
    
    if success:
        file_size = Path(output_path).stat().st_size
        print(f"[OK] Corrected HDR saved ({file_size:,} bytes)")
        return True
    else:
        print("[ERROR] Failed to save corrected HDR")
        return False


def main():
    parser = argparse.ArgumentParser(description='Apply vignetting correction to HDR')
    parser.add_argument('--hdr', required=True, help='Input HDR file path')
    parser.add_argument('--correction', required=True, help='Vignetting correction map (.npy)')
    parser.add_argument('--output', required=True, help='Output corrected HDR file path')
    args = parser.parse_args()
    success = apply_vignetting_correction(args.hdr, args.correction, args.output)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
