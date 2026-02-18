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


def main():
    """Main entry point."""
    sensor_id = sys.argv[1] if len(sys.argv) > 1 else "sensor11"
    workspace = Path(__file__).parent
    images_dir = workspace / "images"
    output_dir = workspace / "02_generate_response_output"
    output_path = output_dir / f"{sensor_id}.rsp"
    
    print("=" * 70)
    print("PHASE 2: AUTO-GENERATE RESPONSE FILE")
    print("=" * 70)
    print()
    print(f"Sensor: {sensor_id}")
    print(f"Searching: {images_dir}")
    print()
    
    if not images_dir.exists():
        print(f"ERROR: Images directory not found: {images_dir}")
        print("Please create images/ folder and add bracketed exposure images.")
        sys.exit(1)
    
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
        sys.exit(1)
    
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


if __name__ == "__main__":
    main()
