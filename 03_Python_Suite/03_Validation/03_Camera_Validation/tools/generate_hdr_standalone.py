# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Generate HDR images from JPEG exposure brackets using Debevec algorithm
# Includes saturation patching for over-exposed pixels in shortest exposure
# ==============================================================================

import cv2
import numpy as np
import sys
from pathlib import Path
from typing import List
import argparse


def generate_hdr(image_paths: List[str], exposure_times: List[float], output_path: str) -> bool:
    """
    Generate HDR image from exposure bracket images.
    
    Args:
        image_paths: List of JPEG image paths
        exposure_times: List of exposure times (must match image count)
        output_path: Output HDR file path
    
    Returns:
        True if successful, False otherwise
    """
    if len(image_paths) != len(exposure_times):
        print(f"ERROR: Number of images ({len(image_paths)}) doesn't match exposures ({len(exposure_times)})")
        return False
    
    print(f"Loading {len(image_paths)} images...")
    images = []
    for i, img_path in enumerate(image_paths):
        img = cv2.imread(img_path)
        if img is None:
            print(f"ERROR: Could not load image: {img_path}")
            return False
        images.append(img)
        print(f"  [{i+1}/{len(image_paths)}] {Path(img_path).name}")
    
    times = np.array(exposure_times, dtype=np.float32)
    print(f"\nExposure times: {times.tolist()}")
    print(f"Range: {times.min():.2f} to {times.max():.2f}")
    
    print("\nMerging with Debevec algorithm...")
    merge_debevec = cv2.createMergeDebevec()
    hdr = merge_debevec.process(images, times)
    
    shortest_idx = np.argmin(exposure_times)
    shortest_img = images[shortest_idx]
    saturation_mask = np.any(shortest_img > 250, axis=2)
    num_saturated = np.count_nonzero(saturation_mask)
    
    if num_saturated > 0:
        luminance = 0.2126 * hdr[:, :, 2] + 0.7152 * hdr[:, :, 1] + 0.0722 * hdr[:, :, 0]
        max_luminance = np.max(luminance)
        print(f"\nSaturation patching:")
        print(f"  Saturated pixels: {num_saturated:,}")
        print(f"  Patch value: {max_luminance:.2f} cd/m²")
        hdr[saturation_mask] = max_luminance
    
    print(f"\nSaving HDR to: {output_path}")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    success = cv2.imwrite(output_path, hdr)
    
    if success:
        file_size = Path(output_path).stat().st_size
        print(f"[OK] HDR saved ({file_size:,} bytes)")
        return True
    else:
        print("[ERROR] Failed to save HDR")
        return False


def main():
    parser = argparse.ArgumentParser(description='Generate HDR from exposure brackets')
    parser.add_argument('images', nargs='+', help='Image file paths')
    parser.add_argument('--exposures', required=True, help='Comma-separated exposure times')
    parser.add_argument('--output', required=True, help='Output HDR file path')
    args = parser.parse_args()
    exposure_times = [float(x) for x in args.exposures.split(',')]
    success = generate_hdr(args.images, exposure_times, args.output)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
