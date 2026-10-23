# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# HDR Generation:Automatic HDR image generation using OpenCV's Debevec algorithm
# Uses .rsp file and images from image folder to create HDR in Radiance format.
# ==============================================================================

import cv2
import numpy as np
import sys
from pathlib import Path
from typing import List, Tuple
import re

# ============================================================================
# CONFIGURATION: Saturation Patching
# ============================================================================
# Toggle to enable/disable automatic patching of saturated pixels
# When enabled: Pixels saturated in shortest exposure are set to max HDR luminance
# When disabled: Original Debevec merge output is used without modification
ENABLE_SATURATION_PATCHING = True
# ============================================================================


def find_all_sensor_ids(workspace: Path) -> List[str]:
    """
    Scan for all sensor IDs that have response files or pre-existing HDR files.

    Checks:
      - 02_generate_response_output/ for *.rsp files
      - 01_define_roi_input/ for device-generated *.hdr files
      - 04_map_calibration_points_input/ for device-generated *.hdr files

    Args:
        workspace: Path to the script's directory

    Returns:
        Sorted list of unique sensor IDs.
    """
    sensor_ids = set()

    rsp_dir = workspace / '02_generate_response_output'
    if rsp_dir.exists():
        for f in rsp_dir.glob('*.rsp'):
            match = re.search(r'(sensor\d{2})', f.stem)
            if match:
                sensor_ids.add(match.group(1))

    for hdr_dir_name in ('01_define_roi_input', '04_map_calibration_points_input'):
        hdr_dir = workspace / hdr_dir_name
        if hdr_dir.exists():
            for f in hdr_dir.glob('*.hdr'):
                match = re.search(r'(sensor\d{2})', f.name)
                if match:
                    sensor_ids.add(match.group(1))

    return sorted(sensor_ids)


def parse_response_file(response_file: str, base_path: Path) -> Tuple[List[float], List[str]]:
    """
    Parse response file to get exposures and image paths.

    Args:
        response_file: Path to .rsp file
        base_path: Base directory to resolve relative paths

    Returns:
        Tuple of (exposure_times, image_paths)
    """
    exposure_times = []
    image_paths = []

    with open(response_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split()
            if len(parts) >= 2:
                exposure = float(parts[0])
                image_path = base_path / parts[1]
                exposure_times.append(exposure)
                image_paths.append(str(image_path))

    return exposure_times, image_paths


def patch_saturated_pixels(
    hdr: np.ndarray,
    image_paths: List[str],
    exposure_times: List[float],
    sensor_id: str,
    output_dir: Path
) -> np.ndarray:
    """
    Detect and patch black holes caused by saturation in the shortest exposure.
    
    When all exposures are saturated, the HDR merge creates black holes (very low
    luminance values). This function identifies those pixels and patches them with
    a reasonable maximum luminance value.
    
    Args:
        hdr: HDR image from merge (H x W x 3, BGR, float32)
        image_paths: List of original image paths
        exposure_times: List of exposure times
        sensor_id: Sensor identifier for debug output
        output_dir: Directory to save debug files
    
    Returns:
        Patched HDR image
    """
    print("\n" + "=" * 70)
    print("Saturation Patching")
    print("=" * 70)
    
    shortest_exp_idx = np.argmin(exposure_times)
    shortest_exp_time = exposure_times[shortest_exp_idx]
    shortest_exp_path = image_paths[shortest_exp_idx]
    
    print(f"\nShortest exposure: {Path(shortest_exp_path).name}")
    print(f"  Exposure time: {shortest_exp_time:.4f}")
    print(f"  Index: {shortest_exp_idx + 1}/{len(exposure_times)}")
    
    shortest_img = cv2.imread(shortest_exp_path)
    if shortest_img is None:
        print(f"Warning: Could not load shortest exposure, skipping patching")
        return hdr
    
    print(f"  Image shape: {shortest_img.shape}")
    
    saturation_threshold = 250
    saturation_mask = np.any(shortest_img > saturation_threshold, axis=2).astype(np.uint8)
    
    num_saturated = np.count_nonzero(saturation_mask)
    total_pixels = saturation_mask.shape[0] * saturation_mask.shape[1]
    saturation_pct = 100.0 * num_saturated / total_pixels
    
    print(f"\nSaturation analysis (threshold > {saturation_threshold}):")
    print(f"  Saturated pixels: {num_saturated:,} ({saturation_pct:.2f}%)")
    
    mask_path = output_dir / f"{sensor_id}_saturation_mask.png"
    cv2.imwrite(str(mask_path), saturation_mask * 255)
    print(f"  Saturation mask saved: {mask_path.name}")
    
    # Calculate luminance from HDR using Y = 0.2126*R + 0.7152*G + 0.0722*B
    luminance = (0.0722 * hdr[:, :, 0] +  # B
                 0.7152 * hdr[:, :, 1] +  # G
                 0.2126 * hdr[:, :, 2])   # R
    
    max_luminance = np.max(luminance)
    print(f"\n  Maximum luminance in HDR: {max_luminance:.2f} cd/m²")
    
    pixels_to_patch = saturation_mask > 0
    
    num_to_patch = np.count_nonzero(pixels_to_patch)
    patch_pct = 100.0 * num_to_patch / total_pixels
    
    print(f"\nSaturated pixel patching:")
    print(f"  Pixels to patch (saturated in shortest exposure): {num_to_patch:,} ({patch_pct:.2f}%)")
    print(f"  Patch value: {max_luminance:.2f} cd/m² (maximum from HDR)")
    
    if num_to_patch == 0:
        print("  No patching needed - no saturated pixels found")
        return hdr
    
    hdr_patched = hdr.copy()
    
    hdr_patched[pixels_to_patch] = max_luminance
    
    print(f"\nPatching complete:")
    print(f"  Patched pixels: {num_to_patch:,} ({patch_pct:.2f}%)")
    print(f"  Patch luminance value: {max_luminance:.2f} cd/m²")
    
    luminance_patched = (0.0722 * hdr_patched[:, :, 0] +
                        0.7152 * hdr_patched[:, :, 1] +
                        0.2126 * hdr_patched[:, :, 2])
    print(f"  Luminance range before: [{luminance.min():.6f}, {luminance.max():.2f}]")
    print(f"  Luminance range after:  [{luminance_patched.min():.6f}, {luminance_patched.max():.2f}]")
    
    return hdr_patched


def create_hdr_opencv(
    image_paths: List[str],
    exposure_times: List[float],
    output_path: str,
    sensor_id: str = "sensor",
    output_dir: Path = None
) -> bool:
    """
    Create HDR image using OpenCV's Debevec algorithm with saturation patching.
    
    Args:
        image_paths: List of image file paths
        exposure_times: List of relative exposure values
        output_path: Output HDR file path
        sensor_id: Sensor identifier for debug output
        output_dir: Directory to save debug files
    
    Returns:
        True if successful, False otherwise
    """
    print(f"Loading {len(image_paths)} images...")
    
    images = []
    for i, img_path in enumerate(image_paths):
        img = cv2.imread(img_path)
        if img is None:
            print(f"Error: Could not load image: {img_path}", file=sys.stderr)
            return False
        images.append(img)
        print(f"  [{i+1}/{len(image_paths)}] {Path(img_path).name} - {img.shape}")
    
    times = np.array(exposure_times, dtype=np.float32)
    
    print(f"\nExposure times: {times.tolist()}")
    print(f"Exposure range: {times.min():.2f} to {times.max():.2f}")
    
    print("\nMerging exposures with Debevec algorithm...")
    merge_debevec = cv2.createMergeDebevec()
    
    hdr = merge_debevec.process(images, times)
    
    if ENABLE_SATURATION_PATCHING and output_dir is not None:
        hdr = patch_saturated_pixels(hdr, image_paths, exposure_times, 
                                     sensor_id, output_dir)
    elif not ENABLE_SATURATION_PATCHING:
        print("\n[INFO] Saturation patching is DISABLED - using original Debevec output")
    
    print(f"\nSaving HDR to: {output_path}")
    success = cv2.imwrite(output_path, hdr)
    
    if success:
        file_size = Path(output_path).stat().st_size
        print(f"[OK] HDR saved successfully!")
        print(f"  Format: {hdr.dtype}")
        print(f"  Shape: {hdr.shape}")
        print(f"  File size: {file_size:,} bytes")
        return True
    else:
        print(f"[ERROR] Failed to save HDR", file=sys.stderr)
        return False


def process_single_sensor_hdr(sensor_id: str, workspace_root: Path) -> bool:
    """
    Process HDR generation for a single sensor.

    Output file: {sensor_id}_Raw.hdr (capital R).
    Skips if output already exists (checks both new _Raw.hdr and legacy _raw.hdr).
    Also skips JPEG merge if a pre-existing device HDR is found in
    04_map_calibration_points_input/.

    Returns:
        True if successful or already done/skipped, False on error.
    """
    response_file = workspace_root / '02_generate_response_output' / f'{sensor_id}.rsp'
    output_dir = workspace_root / '03_generate_hdr_output'
    output_hdr = output_dir / f'{sensor_id}_Raw.hdr'
    output_hdr_legacy = output_dir / f'{sensor_id}_raw.hdr'
    input_hdr_dir = workspace_root / '04_map_calibration_points_input'

    print("=" * 70)
    print(f"Phase 3: HDR Generation (OpenCV Debevec) — {sensor_id}")
    print("=" * 70)
    print()

    # Skip if output already exists
    if output_hdr.exists():
        print(f"Skipping (already exists): {output_hdr.name}")
        return True
    if output_hdr_legacy.exists():
        print(f"Skipping (already exists, legacy name): {output_hdr_legacy.name}")
        return True

    # Check for pre-existing device-generated HDR in either input folder
    for hdr_dir in (workspace_root / '01_define_roi_input', input_hdr_dir):
        if hdr_dir.exists():
            existing_hdrs = sorted(hdr_dir.glob(f'*{sensor_id}*.hdr'))
            if existing_hdrs:
                print(f"Using pre-existing HDR from {hdr_dir.name}: {existing_hdrs[0].name}")
                print(f"  (Skipping JPEG merge — device-generated HDR found)")
                print()
                return True

    if not response_file.exists():
        print(f"Error: Response file not found: {response_file}")
        print("Please run Phase 2 first to generate the response file.")
        return False

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Input: {response_file}")
    print(f"Output: {output_hdr}")
    print()

    print("Parsing response file...")
    exposure_times, image_paths = parse_response_file(str(response_file), workspace_root)

    print(f"Found {len(image_paths)} images")
    print()

    success = create_hdr_opencv(image_paths, exposure_times, str(output_hdr),
                                sensor_id, output_dir)

    if not success:
        print()
        print("[ERROR] HDR generation failed!")
        return False

    print()
    print("=" * 70)
    print("Phase 3 Complete!")
    print("=" * 70)
    print()
    print(f"HDR file: {output_hdr}")
    print()
    print("Next step: Map calibration points interactively")
    return True


def main():
    """
    Main function to generate HDR using OpenCV. Supports single-sensor and
    batch ('all') modes.
    """
    workspace_root = Path(__file__).parent
    explicit_arg = sys.argv[1] if len(sys.argv) > 1 else None

    all_sensor_ids = find_all_sensor_ids(workspace_root)

    if explicit_arg == 'all':
        batch_mode = True
        sensors_to_process = all_sensor_ids if all_sensor_ids else []
    elif explicit_arg is not None:
        batch_mode = False
        sensors_to_process = [explicit_arg]
    elif len(all_sensor_ids) > 1:
        batch_mode = True
        sensors_to_process = all_sensor_ids
        print(f"Auto-detected {len(all_sensor_ids)} sensors. Running batch mode.")
        print()
    elif len(all_sensor_ids) == 1:
        batch_mode = False
        sensors_to_process = all_sensor_ids
    else:
        batch_mode = False
        sensors_to_process = ['sensor11']

    if batch_mode:
        print("=" * 70)
        print("PHASE 3: HDR GENERATION (BATCH MODE)")
        print("=" * 70)
        print(f"Sensors to process ({len(sensors_to_process)}): {', '.join(sensors_to_process)}")
        print()

        processed = []
        failed = []
        n = len(sensors_to_process)

        for i, sensor_id in enumerate(sensors_to_process, 1):
            print(f"\n{'─' * 70}")
            print(f"Processing sensor {i} of {n}: {sensor_id}")
            print(f"{'─' * 70}\n")
            try:
                ok = process_single_sensor_hdr(sensor_id, workspace_root)
                (processed if ok else failed).append(sensor_id)
            except Exception as e:
                print(f"[ERROR] Failed to process {sensor_id}: {e}")
                import traceback
                traceback.print_exc()
                failed.append(sensor_id)

        print()
        print("=" * 70)
        print("BATCH COMPLETE")
        print("=" * 70)
        print(f"Processed {len(processed)} of {n} sensors.")
        if processed:
            print(f"  Success: {', '.join(processed)}")
        if failed:
            print(f"  Failed:  {', '.join(failed)}")
        print()
        print("Next step:")
        print("  python 04_map_cal_points.py all")
        print()
    else:
        sensor_id = sensors_to_process[0]
        ok = process_single_sensor_hdr(sensor_id, workspace_root)
        if not ok:
            sys.exit(1)


if __name__ == '__main__':
    main()
