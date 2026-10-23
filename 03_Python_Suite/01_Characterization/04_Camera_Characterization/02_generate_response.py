# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Auto-Generate Response File:Automatically creates .rsp file based on images found in the images/ folder
# Allows user to detect all exposure bracketed images for the sensor
# ==============================================================================

import sys
import re
from pathlib import Path
from typing import List, Tuple


def find_all_sensor_ids(images_dir: Path) -> List[str]:
    """
    Scan images directory for all unique sensor IDs found in image filenames.

    Args:
        images_dir: Path to images directory

    Returns:
        Sorted list of unique sensor IDs (e.g. ['sensor01', 'sensor11'])
    """
    sensor_ids = set()
    for ext in ('*.jpeg', '*.jpg'):
        for img in images_dir.glob(ext):
            match = re.search(r'(sensor\d{2})', img.name)
            if match:
                sensor_ids.add(match.group(1))
    return sorted(sensor_ids)


def find_sensor_images(images_dir: Path, sensor_id: str) -> List[Path]:
    """
    Find all images for a specific sensor in the images directory.
    
    Args:
        images_dir: Path to images directory
        sensor_id: Sensor identifier (e.g., 'sensor11')
    
    Returns:
        List of image paths sorted by filename
    """
    pattern = f"*_{sensor_id}_exp*.jpeg"
    images = list(images_dir.glob(pattern))
    
    pattern_jpg = f"*_{sensor_id}_exp*.jpg"
    images.extend(images_dir.glob(pattern_jpg))
    
    return sorted(images)


def extract_exposure_value(filename: str) -> Tuple[float, str]:
    """
    Extract exposure value from filename.
    
    Expected format: TIMESTAMP_sensorXX_expNNN.jpeg
    where NNN is the exposure multiplier (1, 2, 8, 16, 32, 64, 128, 256, 512, 1200, etc.)
    
    Args:
        filename: Image filename
    
    Returns:
        Tuple of (exposure_value, exposure_key)
    """
    
    match = re.search(r'_exp(\d+)', filename)
    
    if not match:
        raise ValueError(f"Could not extract exposure from filename: {filename}")
    
    exp_num = int(match.group(1))
    exposure_value = float(exp_num)
    
    return exposure_value, f"exp{exp_num}"


def group_by_timestamp(images: List[Path]) -> dict:
    """
    Group images by timestamp (capture session).
    
    Args:
        images: List of image paths
    
    Returns:
        Dictionary mapping timestamp to list of images
    """
    sessions = {}
    
    for img in images:
        
        timestamp = img.stem[:15] # Extract timestamp (first 15 chars: YYYYMMDD_HHMMSS)

        if timestamp not in sessions:
            sessions[timestamp] = []
        
        sessions[timestamp].append(img)
    
    return sessions


def generate_response_file(images: List[Path], output_path: Path, sensor_id: str):
    """
    Generate response file for hdrgen/OpenCV.
    
    Format:
    exposure_value path/to/image.jpeg
    
    Args:
        images: List of image paths
        output_path: Path to output .rsp file
        sensor_id: Sensor identifier
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    image_exposures = []
    for img in images:
        try:
            exp_value, exp_key = extract_exposure_value(img.name)
            image_exposures.append((exp_value, img))
        except ValueError as e:
            print(f"Warning: {e}")
            continue
    
    image_exposures.sort(key=lambda x: x[0])
    
    with open(output_path, 'w') as f:
        f.write(f"# Response file for {sensor_id}\n")
        f.write(f"# Auto-generated from images/ folder\n")
        f.write(f"# Total images: {len(image_exposures)}\n")
        f.write("#\n")
        
        for exp_value, img_path in image_exposures:
            rel_path = f"images/{img_path.name}"
            f.write(f"{exp_value} {rel_path}\n")
    
    print(f"Generated response file: {output_path}")
    print(f"  Images: {len(image_exposures)}")
    print(f"  Exposure range: {image_exposures[0][0]:.1f} to {image_exposures[-1][0]:.1f}")


def process_single_sensor(images_dir: Path, output_dir: Path, sensor_id: str) -> bool:
    """
    Process a single sensor: find images and generate response file.

    Args:
        images_dir: Path to images directory
        output_dir: Path to output directory
        sensor_id: Sensor identifier (e.g., 'sensor11')

    Returns:
        True if successful, False otherwise.
    """
    output_path = output_dir / f"{sensor_id}.rsp"

    print("=" * 70)
    print("PHASE 2: AUTO-GENERATE RESPONSE FILE")
    print("=" * 70)
    print()
    print(f"Sensor: {sensor_id}")
    print(f"Searching: {images_dir}")
    print()

    print("Searching for images...")
    images = find_sensor_images(images_dir, sensor_id)

    if len(images) == 0:
        print(f"ERROR: No images found for {sensor_id}")
        print(f"Expected pattern: *_{sensor_id}_exp*.jpeg")
        print()
        print("Please add exposure-bracketed images to images/ folder:")
        print("  Example: 20250208_114436_sensor11_exp1.jpeg")
        print("           20250208_114436_sensor11_exp2.jpeg")
        print("           20250208_114436_sensor11_exp8.jpeg")
        print("           ...")
        return False

    print(f"Found {len(images)} images")
    print()

    sessions = group_by_timestamp(images)

    if len(sessions) > 1:
        print(f"WARNING: Found {len(sessions)} different capture sessions:")
        for timestamp, session_images in sorted(sessions.items()):
            print(f"  {timestamp}: {len(session_images)} images")
        print()

        selected_timestamp = sorted(sessions.keys())[-1]
        print(f"Using most recent session: {selected_timestamp}")
        images = sessions[selected_timestamp]
        print()
    else:
        timestamp = list(sessions.keys())[0]
        print(f"Capture session: {timestamp}")
        print()

    print("Images to include:")
    for img in sorted(images):
        try:
            exp_value, _ = extract_exposure_value(img.name)
            print(f"  {img.name} (exp={exp_value:.1f})")
        except ValueError:
            print(f"  {img.name} (unknown exposure)")
    print()

    generate_response_file(images, output_path, sensor_id)

    print()
    print("=" * 70)
    print("PHASE 2 COMPLETE")
    print("=" * 70)
    print()
    print(f"Response file: {output_path}")
    print()
    print("Next step:")
    print(f"  python 03_generate_hdr.py {sensor_id}")
    print()
    return True


def main():
    """Main entry point. Supports single-sensor and batch ('all') modes."""
    workspace = Path(__file__).parent
    images_dir = workspace / "images"
    output_dir = workspace / "02_generate_response_output"

    if not images_dir.exists():
        print(f"ERROR: Images directory not found: {images_dir}")
        print("Please create images/ folder and add bracketed exposure images.")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    all_sensor_ids = find_all_sensor_ids(images_dir)
    explicit_arg = sys.argv[1] if len(sys.argv) > 1 else None

    # Determine mode and sensor list
    if explicit_arg == "all":
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
        # No sensors detected; fall back to default
        batch_mode = False
        sensors_to_process = ["sensor11"]

    if not sensors_to_process:
        print("ERROR: No sensor images found in images/ directory.")
        sys.exit(1)

    if batch_mode:
        print("=" * 70)
        print("PHASE 2: AUTO-GENERATE RESPONSE FILES (BATCH MODE)")
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
                ok = process_single_sensor(images_dir, output_dir, sensor_id)
                (processed if ok else failed).append(sensor_id)
            except Exception as e:
                print(f"[ERROR] {e}")
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
        print("  python 03_generate_hdr.py all")
        print()
    else:
        sensor_id = sensors_to_process[0]
        ok = process_single_sensor(images_dir, output_dir, sensor_id)
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
