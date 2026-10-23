# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Apply vignetting correction to HDR images using the fitted polynomial model
# from a vignetting_report.json (same even-power model used in firmware):
#   V(r) = 1 + b*r^2 + c*r^4 + d*r^6  (r normalised by max_distance)
#   correction = 1 / V(r), clipped to [1.0, 10.0]
# Also supports legacy pre-computed correction maps (.npy) for backward compat.
# ==============================================================================

import cv2
import json
import numpy as np
import sys
from pathlib import Path
import argparse


def build_correction_map_from_report(report_path: str, shape) -> np.ndarray:
    """
    Compute per-pixel vignetting correction map from a vignetting_report.json.
    Uses the same even-power polynomial model as the on-device firmware:
        V(r) = 1 + b*r^2 + c*r^4 + d*r^6
        correction = 1 / V(r)
    """
    with open(report_path, 'r') as f:
        report = json.load(f)

    cx, cy = report['fisheye_center']
    b, c, d = report['vignetting']['polynomial_coeffs']
    max_dist = report['vignetting']['max_distance']

    h, w = shape[:2]
    ys, xs = np.ogrid[:h, :w]
    r_norm = np.sqrt((xs - cx)**2 + (ys - cy)**2) / max_dist

    vignetting = 1.0 + b * (r_norm**2) + c * (r_norm**4) + d * (r_norm**6)
    vignetting = np.clip(vignetting, 0.1, 1.0)
    correction_map = np.clip(1.0 / vignetting, 1.0, 10.0).astype(np.float32)

    print(f"  Center: ({cx}, {cy}), max_dist: {max_dist:.1f} px")
    print(f"  Model:  V(r) = 1 + {b:.6f}*r^2 + {c:.6f}*r^4 + {d:.6f}*r^6")
    print(f"  Correction range: [{correction_map.min():.3f}, {correction_map.max():.3f}]")
    return correction_map


def apply_vignetting_correction(hdr_path: str, correction_source: str, output_path: str) -> bool:
    """
    Apply vignetting correction to an HDR image.

    correction_source can be:
      - a vignetting_report.json  → correction map computed from polynomial coefficients
      - a .npy file               → pre-computed correction map (legacy)
    """
    print(f"Loading HDR: {hdr_path}")
    hdr = cv2.imread(hdr_path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
    if hdr is None:
        print("ERROR: Could not load HDR file")
        return False
    print(f"  Shape: {hdr.shape}, dtype: {hdr.dtype}")

    src = Path(correction_source)
    if src.suffix.lower() == '.json':
        print(f"\nBuilding correction map from report: {correction_source}")
        correction_map = build_correction_map_from_report(correction_source, hdr.shape)
    else:
        print(f"\nLoading correction map: {correction_source}")
        correction_map = np.load(correction_source)
        print(f"  Shape: {correction_map.shape}, dtype: {correction_map.dtype}")
        print(f"  Range: [{correction_map.min():.3f}, {correction_map.max():.3f}]")

    print("\nApplying vignetting correction...")
    correction_3ch = np.stack([correction_map] * 3, axis=2)
    corrected_hdr = (hdr * correction_3ch).astype(np.float32)

    luminance_before = 0.2126 * hdr[:, :, 2] + 0.7152 * hdr[:, :, 1] + 0.0722 * hdr[:, :, 0]
    luminance_after  = 0.2126 * corrected_hdr[:, :, 2] + 0.7152 * corrected_hdr[:, :, 1] + 0.0722 * corrected_hdr[:, :, 0]
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
    parser.add_argument('--correction', required=True,
                        help='Vignetting report (.json) or pre-computed correction map (.npy)')
    parser.add_argument('--output', required=True, help='Output corrected HDR file path')
    args = parser.parse_args()
    success = apply_vignetting_correction(args.hdr, args.correction, args.output)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
