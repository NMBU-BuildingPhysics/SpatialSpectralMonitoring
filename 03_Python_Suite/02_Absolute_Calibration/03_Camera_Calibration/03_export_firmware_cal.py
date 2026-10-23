# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Export camera calibration data for firmware embedding.
# Reads the three JSON reports from the characterization pipeline and generates
# the CameraCalibrationEntry C++ struct initializer for calibration.cpp.
#
# Prerequisites (run in order):
#   01_Characterization/04_Camera_Characterization/01_define_roi.py
#   01_Characterization/04_Camera_Characterization/05_correct_vignetting.py
#   02_Absolute_Calibration/03_Camera_Calibration/01_apply_calibration.py
#
# Usage:
#   python 03_export_firmware_cal.py [sensor_id | all]
#   python 03_export_firmware_cal.py sensor11
#   python 03_export_firmware_cal.py all
# ==============================================================================

import sys
import json
import re
import datetime
from pathlib import Path

# OV5640 VGA capture dimensions (colour HDR mode)
FRAME_W = 640
FRAME_H = 480


def compute_crop(center_x: int, center_y: int,
                 radius_x: int, radius_y: int,
                 frame_w: int = FRAME_W, frame_h: int = FRAME_H):
    """
    Compute the axis-aligned bounding box for the fisheye ellipse.

    Python image-slice convention: end indices are exclusive, so
    slicing arr[crop_y : crop_y+crop_h] gives exactly crop_h rows
    spanning from the top of the circle to the bottom inclusive.
    """
    crop_x = max(0, center_x - radius_x)
    crop_y = max(0, center_y - radius_y)
    end_x  = min(frame_w, center_x + radius_x + 1)
    end_y  = min(frame_h, center_y + radius_y + 1)
    crop_w = end_x - crop_x
    crop_h = end_y - crop_y
    return crop_x, crop_y, crop_w, crop_h


def find_all_sensor_ids(script_dir: Path) -> list:
    """Return sorted list of sensor IDs that have a calibration report."""
    cal_out = script_dir / '01_apply_calibration_output'
    sensor_ids = sorted(set(
        re.search(r'(sensor\d{2})', p.stem).group(1)
        for p in cal_out.glob('*_calibration_report.json')
        if re.search(r'(sensor\d{2})', p.stem)
    ))
    return sensor_ids


def load_json_soft(path: Path) -> dict | None:
    """Load JSON, returning None on failure (non-fatal)."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def build_snippet(sensor_id: str, script_dir: Path, char_dir: Path) -> str | None:
    """
    Build the C++ struct initializer snippet for one sensor.
    Returns the snippet string, or None if required data is missing.
    """
    vign_path = char_dir / '05_correct_vignetting_output' / f'{sensor_id}_vignetting_report.json'
    cal_path  = script_dir / '01_apply_calibration_output' / f'{sensor_id}_calibration_report.json'
    roi_path  = char_dir / '01_define_roi_output' / 'roi_params.json'

    vign    = load_json_soft(vign_path)
    cal     = load_json_soft(cal_path)
    roi_all = load_json_soft(roi_path)

    if vign is None:
        print(f"  [SKIP] {sensor_id}: vignetting report not found at {vign_path}")
        return None
    if cal is None:
        print(f"  [SKIP] {sensor_id}: calibration report not found at {cal_path}")
        return None
    if roi_all is None:
        print(f"  [SKIP] {sensor_id}: ROI params not found at {roi_path}")
        return None
    if sensor_id not in roi_all:
        print(f"  [SKIP] {sensor_id}: not found in roi_params.json (available: {list(roi_all.keys())})")
        return None

    vign_data = vign.get('vignetting', {})
    coeffs = vign_data.get('polynomial_coeffs')
    if not coeffs or len(coeffs) < 3:
        print(f"  [SKIP] {sensor_id}: polynomial_coeffs missing from vignetting report")
        return None
    if 'max_distance' not in vign_data:
        print(f"  [SKIP] {sensor_id}: max_distance missing from vignetting report")
        return None

    b, c, d   = float(coeffs[0]), float(coeffs[1]), float(coeffs[2])
    max_dist  = float(vign_data['max_distance'])

    if 'median_scale_factor' in cal:
        cal_scale = float(cal['median_scale_factor'])
    elif 'statistics' in cal and 'median' in cal['statistics']:
        cal_scale = float(cal['statistics']['median'])
    else:
        print(f"  [SKIP] {sensor_id}: cannot find median scale factor")
        return None

    roi = roi_all[sensor_id]
    cx, cy = int(roi['center_x']), int(roi['center_y'])
    rx, ry = int(roi['radius_x']), int(roi['radius_y'])
    crop_x, crop_y, crop_w, crop_h = compute_crop(cx, cy, rx, ry)

    n_pts        = len(cal.get('calibration_points', []))
    val          = cal.get('validation', {})
    mean_err     = val.get('mean_error_percent', float('nan'))
    pts_within_5 = val.get('points_within_5_percent', '?')
    corr_max     = vign_data.get('correction_range', {}).get('max', float('nan'))
    edge_falloff = vign_data.get('edge_falloff_percent', float('nan'))
    year         = datetime.date.today().year

    formula = f"V(r) = 1 {b:+.5f}*r\u00b2 {c:+.5f}*r\u2074 {d:+.5f}*r\u2076"

    snippet = (
        f'    // {sensor_id}: characterized {year} \u2014 polynomial from {n_pts} calibration points\n'
        f'    //   Vignetting: {formula}\n'
        f'    //   Cal scale: median of {n_pts} points, mean error {mean_err:.1f}%, '
        f'{pts_within_5}/{n_pts} points within 5%\n'
        f'    //   ROI: elliptical fisheye, center=({cx},{cy}), radii=({rx},{ry})\n'
        f'    //   max_dist: {max_dist:.1f} px (farthest calibration point from center)\n'
        f'    //   Edge falloff: {edge_falloff:.1f}%, max correction: {corr_max:.2f}x\n'
        f'    //   Crop: bounding box of elliptical ROI clamped to {FRAME_W}x{FRAME_H}\n'
        f'    {{"{sensor_id}", {{\n'
        f'        {b:.8f}f, {c:.8f}f, {d:.8f}f,   // vign_b, vign_c, vign_d\n'
        f'        {cx:.1f}f, {cy:.1f}f, {max_dist:.1f}f,                     '
        f'// vign_cx, vign_cy, vign_max_dist\n'
        f'        {cal_scale:.4f}f,                                   '
        f'// cal_scale (cd/m\u00b2 per HDR unit)\n'
        f'        {crop_x}, {crop_y}, {crop_w}, {crop_h},                             '
        f'// crop_x, crop_y, crop_w, crop_h\n'
        f'        {FRAME_W}, {FRAME_H}                                     '
        f'// src_width, src_height\n'
        f'    }}}},'
    )
    return snippet


def main():
    script_dir = Path(__file__).parent.resolve()
    char_dir   = script_dir.parents[1] / '01_Characterization' / '04_Camera_Characterization'

    # ---- Determine which sensors to process ----
    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg and arg.lower() == 'all':
        sensors_to_process = find_all_sensor_ids(script_dir)
        if not sensors_to_process:
            print("[ERROR] No calibration reports found in 01_apply_calibration_output/")
            sys.exit(1)
        batch_mode = True
    elif arg:
        sensors_to_process = [arg]
        batch_mode = False
    else:
        candidates = find_all_sensor_ids(script_dir)
        if len(candidates) == 1:
            sensors_to_process = candidates
            batch_mode = False
            print(f"Auto-detected sensor: {candidates[0]}\n")
        elif len(candidates) > 1:
            sensors_to_process = candidates
            batch_mode = True
            print(f"Auto-detected {len(candidates)} sensors — running batch export.\n")
        else:
            print("[ERROR] No calibration reports found in 01_apply_calibration_output/")
            print("  Run 01_apply_calibration.py first.")
            sys.exit(1)

    print("=" * 70)
    if batch_mode:
        print(f"FIRMWARE CALIBRATION EXPORT — {len(sensors_to_process)} sensors")
    else:
        print(f"FIRMWARE CALIBRATION EXPORT — {sensors_to_process[0]}")
    print("=" * 70)
    print()

    out_dir = script_dir / '03_export_firmware_cal_output'
    out_dir.mkdir(exist_ok=True)

    processed, failed, snippets = [], [], []

    for i, sensor_id in enumerate(sensors_to_process, 1):
        if batch_mode:
            print(f"[{i}/{len(sensors_to_process)}] {sensor_id}...")

        snippet = build_snippet(sensor_id, script_dir, char_dir)
        if snippet is None:
            failed.append(sensor_id)
            continue

        out_path = out_dir / f'{sensor_id}_firmware_cal.cpp_snippet'
        out_path.write_text(snippet, encoding='utf-8')
        if batch_mode:
            print(f"  Saved: {out_path.name}")
        else:
            print("-" * 70)
            print("Paste this entry into cameraCals[] in:")
            print("  02_Firmware/Main/calibration.cpp")
            print("-" * 70)
            print()
            print(snippet)
            print()
            print(f"Saved to: {out_path}")

        processed.append(sensor_id)
        snippets.append(snippet)

    # ---- Combined array file (always written when batch, or when single succeeds) ----
    if snippets:
        combined_entries = "\n\n".join(snippets)
        combined = (
            f'// Auto-generated by 03_export_firmware_cal.py\n'
            f'// Generated: {datetime.date.today().isoformat()}\n'
            f'// Sensors: {", ".join(processed)}\n'
            f'//\n'
            f'// Copy this array into 02_Firmware/Main/calibration.cpp:\n'
            f'\n'
            f'static constexpr CameraCalibrationEntry cameraCals[] = {{\n'
            f'{combined_entries}\n'
            f'}};\n'
        )
        combined_path = out_dir / 'all_sensors_firmware_cal.cpp_snippet'
        combined_path.write_text(combined, encoding='utf-8')
        if batch_mode:
            print()
            print(f"Combined array: {combined_path}")

    print()
    print("=" * 70)
    if batch_mode:
        print(f"EXPORT COMPLETE: {len(processed)}/{len(sensors_to_process)} succeeded")
        if failed:
            print(f"  Skipped: {', '.join(failed)}")
    else:
        if processed:
            print("EXPORT COMPLETE")
    print("=" * 70)
    print()
    print("Next step: copy all_sensors_firmware_cal.cpp_snippet into calibration.cpp")


if __name__ == '__main__':
    main()
