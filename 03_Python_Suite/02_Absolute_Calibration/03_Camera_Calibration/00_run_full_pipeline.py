# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Description:
# Full calibration pipeline orchestrator for camera sensors.
# Runs all stages in order for all sensors found in the calibration outputs.
#
# Stages:
#   1. 01_apply_calibration.py    — compute scale factors and generate _Cal.hdr
#   2. 02_validate_calibration.py — validate accuracy, falsecolor, Markdown report
#   3. 03_export_firmware_cal.py  — generate C++ struct snippets for firmware
#
# Usage:
#   python 00_run_full_pipeline.py [--start-at STAGE] [--sensor SENSOR_ID]
#
# Options:
#   --start-at  Resume at a specific stage (1-3). Default: 1
#   --sensor    Process a single sensor ID only. Default: all detected sensors
#
# Examples:
#   python 00_run_full_pipeline.py
#   python 00_run_full_pipeline.py --start-at 2
#   python 00_run_full_pipeline.py --sensor sensor11
# ==============================================================================

import sys
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

STAGES = [
    (1, "Apply calibration",        "01_apply_calibration.py"),
    (2, "Validate calibration",     "02_validate_calibration.py"),
    (3, "Export firmware cal data", "03_export_firmware_cal.py"),
]


def run_stage(script_name: str, extra_args: list[str]) -> bool:
    script_path = SCRIPT_DIR / script_name
    cmd = [sys.executable, str(script_path)] + extra_args
    print(f"  Running: {script_name} {' '.join(extra_args)}")
    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    return result.returncode == 0


def main():
    start_at  = 1
    sensor_id = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--start-at' and i + 1 < len(args):
            start_at = int(args[i + 1])
            i += 2
        elif args[i] == '--sensor' and i + 1 < len(args):
            sensor_id = args[i + 1]
            i += 2
        else:
            print(f"Unknown argument: {args[i]}")
            sys.exit(1)

    batch_arg = sensor_id if sensor_id else 'all'

    print("=" * 70)
    print("CAMERA CALIBRATION PIPELINE")
    if sensor_id:
        print(f"  Sensor: {sensor_id}")
    else:
        print("  Sensors: all detected")
    if start_at > 1:
        print(f"  Starting at stage {start_at}")
    print("=" * 70)
    print()

    failed_stage = None
    for stage_num, stage_name, script_name in STAGES:
        if stage_num < start_at:
            print(f"[{stage_num}/3] SKIP  {stage_name}")
            continue

        print(f"[{stage_num}/3] START {stage_name}")
        print("-" * 50)

        ok = run_stage(script_name, [batch_arg])

        if ok:
            print(f"[{stage_num}/3] DONE  {stage_name}")
        else:
            print(f"[{stage_num}/3] FAIL  {stage_name}")
            failed_stage = stage_num
            break
        print()

    print()
    print("=" * 70)
    if failed_stage:
        print(f"PIPELINE STOPPED at stage {failed_stage}")
        print(f"  Fix the issue and re-run with: --start-at {failed_stage}")
    else:
        print("CALIBRATION PIPELINE COMPLETE")
        print()
        print("Combined firmware snippet:")
        combined = SCRIPT_DIR / '03_export_firmware_cal_output' / 'all_sensors_firmware_cal.cpp_snippet'
        if combined.exists():
            print(f"  {combined}")
            print()
            print("Copy this array into 02_Firmware/Main/calibration.cpp")
        else:
            print("  (not found — check stage 3 output)")
    print("=" * 70)


if __name__ == "__main__":
    main()
