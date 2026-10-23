# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Description:
# Full characterization pipeline orchestrator for camera sensors.
# Designed for the on-device HDR pipeline: the sensor generates a single .hdr
# file per capture which is placed in 01_define_roi_input/.
#
# Stages:
#   1. 01_define_roi.py         — interactive fisheye ROI definition (reads 01_define_roi_input/)
#   2. 04_map_cal_points.py     — interactive calibration point mapping
#   3. 05_correct_vignetting.py — fit & apply vignetting correction
#
# Usage:
#   python 00_run_full_pipeline.py [--start-at STAGE] [--sensor SENSOR_ID]
#
# Options:
#   --start-at  Resume at a specific stage (1-3). Default: 1
#   --sensor    Process a single sensor ID only (stage 2-3). Default: all detected sensors
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
    (1, "Define fisheye ROI",       "01_define_roi.py"),
    (2, "Map calibration points",   "04_map_cal_points.py"),
    (3, "Correct vignetting",       "05_correct_vignetting.py"),
]


# Stage 1 (01_define_roi.py) is interactive and takes no batch args — it reads
# from 01_define_roi_input/ and processes whatever images are placed there.
ROI_STAGE = 1


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

    # Batch arg: 'all' for batch, or specific sensor id
    batch_arg = sensor_id if sensor_id else 'all'

    print("=" * 70)
    print("CAMERA CHARACTERIZATION PIPELINE")
    if sensor_id:
        print(f"  Sensor: {sensor_id}")
    else:
        print("  Sensors: all detected")
    if start_at > 1:
        print(f"  Starting at stage {start_at}")
    print("=" * 70)
    print()

    n_stages = len(STAGES)
    failed_stage = None
    for stage_num, stage_name, script_name in STAGES:
        if stage_num < start_at:
            print(f"[{stage_num}/{n_stages}] SKIP  {stage_name}")
            continue

        print(f"[{stage_num}/{n_stages}] START {stage_name}")
        print("-" * 50)

        # Stage 1 (ROI definition) is interactive and takes no batch argument.
        stage_args = [] if stage_num == ROI_STAGE else [batch_arg]

        ok = run_stage(script_name, stage_args)

        if ok:
            print(f"[{stage_num}/{n_stages}] DONE  {stage_name}")
        else:
            print(f"[{stage_num}/{n_stages}] FAIL  {stage_name}")
            failed_stage = stage_num
            break
        print()

    print()
    print("=" * 70)
    if failed_stage:
        print(f"PIPELINE STOPPED at stage {failed_stage}")
        print(f"  Fix the issue and re-run with: --start-at {failed_stage}")
    else:
        print("CHARACTERIZATION PIPELINE COMPLETE")
        print()
        print("Next step: run the calibration pipeline")
        print("  cd ../../02_Absolute_Calibration/03_Camera_Calibration")
        print("  python 00_run_full_pipeline.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
