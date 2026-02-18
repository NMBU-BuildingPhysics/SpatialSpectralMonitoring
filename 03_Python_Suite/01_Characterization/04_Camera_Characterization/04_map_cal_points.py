# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Interactive Calibration Point Mapper:OpenCV GUI to click calibration points on an HDR image
# The luminance values and point labels are loaded from a CSV file
# ==============================================================================

import cv2
import numpy as np
import json
import os
import re
import sys
import csv
from pathlib import Path

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FOLDER = os.path.abspath(os.path.join(PROJECT_DIR, "04_map_calibration_points_input"))
OUTPUT_FOLDER = os.path.abspath(os.path.join(PROJECT_DIR, "04_map_calibration_points_output"))
HDR_INPUT_FOLDER = os.path.abspath(os.path.join(PROJECT_DIR, "04_map_calibration_points_input"))
HDR_FALLBACK_FOLDER = os.path.abspath(os.path.join(PROJECT_DIR, "03_generate_hdr_output"))
os.makedirs(INPUT_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

MAX_DISPLAY_WIDTH = 1200
MAX_DISPLAY_HEIGHT = 900

def load_calibration_csv(csv_path):
    """
    Load calibration data from CSV file.
    
    Expected CSV format:
    - Header row: point, luminance, comment (optional)
    - Data rows: point_number/label, luminance_value, optional_comment
    
    The luminance column should contain numeric values.
    Labels will be extracted from the first column or from comments.
    
    Args:
        csv_path (str): Path to CSV file
        
    Returns:
        tuple: (luminance_values, point_labels) or (None, None) if error
    """
    try:
        luminance_values = []
        point_labels = []
        
        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
        if not rows:
            print(f"Error: CSV file is empty: {csv_path}")
            return None, None
            
        start_index = 0
        if rows[0] and any(keyword in str(rows[0]).lower() for keyword in ['point', 'luminance', 'label']):
            start_index = 1
            
        for idx, row in enumerate(rows[start_index:], start=0):
            row = [cell.strip() for cell in row if cell.strip()]
            
            if not row:
                continue
                
            luminance = None
            label = None
            
            for cell in row:
                try:
                    luminance = float(cell)
                    break
                except ValueError:
                    if not label:
                        label = cell
                        
            if luminance is not None:
                luminance_values.append(int(luminance))
                
                if label:
                    label = re.sub(r'[#\(\)]', '', label).strip()
                    point_labels.append(label)
                else:
                    point_labels.append(f"Point {idx}")
                    
        if not luminance_values:
            print(f"Error: No luminance values found in CSV: {csv_path}")
            return None, None
            
        print(f"Loaded {len(luminance_values)} calibration points from CSV")
        return luminance_values, point_labels
        
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        return None, None


def find_hdr_file(sensor_id):
    """
    Find HDR file for the given sensor ID.
    
    Checks 04_map_calibration_points_input first (priority),
    then falls back to 03_generate_hdr_output.
    
    Args:
        sensor_id (str): Sensor ID (e.g., "sensor11")
        
    Returns:
        tuple: (hdr_path, source_folder) or (None, None) if not found
    """
    hdr_filename = f"{sensor_id}_raw.hdr"
    
    priority_path = os.path.join(HDR_INPUT_FOLDER, hdr_filename)
    if os.path.exists(priority_path):
        print(f"✓ Found HDR file in 04_map_calibration_points_input: {hdr_filename}")
        return priority_path, "04_map_calibration_points_input"
        
    fallback_path = os.path.join(HDR_FALLBACK_FOLDER, hdr_filename)
    if os.path.exists(fallback_path):
        print(f"✓ Found HDR file in 03_generate_hdr_output: {hdr_filename}")
        return fallback_path, "03_generate_hdr_output"
        
    print(f"✗ HDR file not found in either location:")
    print(f"  - {priority_path}")
    print(f"  - {fallback_path}")
    return None, None


def validate_point_coordinates(x, y, width, height):
    """
    Validate that coordinates are within image bounds.
    
    Args:
        x (int): X coordinate
        y (int): Y coordinate
        width (int): Image width
        height (int): Image height
        
    Returns:
        bool: True if coordinates are valid, False otherwise
    """
    return 0 <= x < width and 0 <= y < height


def validate_luminance_value(luminance, point_id):
    """
    Validate that luminance value is reasonable.
    
    Args:
        luminance (float): Luminance value in cd/m²
        point_id (int): Point ID (0-9)
        
    Returns:
        bool: True if luminance is valid, False otherwise
    """
    if luminance <= 0 or luminance > 100000000:
        return False
    return True


def save_calibration_points(filepath, data):
    """
    Save calibration points to JSON file.
    
    Args:
        filepath (str): Path to output JSON file
        data (dict): Calibration data dictionary
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Saved calibration points to: {filepath}")


class CalibrationMapper:
    """
    Interactive calibration point mapper with OpenCV GUI.
    
    Allows user to click calibration points on an HDR image and
    automatically assigns luminance values in sequential order.
    """
    
    def __init__(self, hdr_path, luminance_values, point_labels):
        """
        Initialize the calibration mapper.
        
        Args:
            hdr_path (str): Path to HDR image file
            luminance_values (list): List of luminance values in cd/m²
            point_labels (list): List of point labels
        """
        self.hdr_path = hdr_path
        self.points = []
        self.current_point_index = 0
        self.luminance_values = luminance_values.copy()
        self.point_labels = point_labels.copy()
        self.sensor_id = self._extract_sensor_id(hdr_path)
        self.hdr_image = None
        self.display_image = None
        self.display_scale = 1.0
        self.image_width = 0
        self.image_height = 0
        self.magnifier_size = 150
        self.magnifier_zoom = 10
        self.hover_x = None
        self.hover_y = None
        
        self.all_points_marked_printed = False
        
    def _extract_sensor_id(self, hdr_path):
        """Extract sensor ID from HDR filename."""
        match = re.search(r'(sensor\d{2})', hdr_path)
        if match:
            return match.group(1)
        return "sensor11"
        
    def add_point(self, x, y):
        """
        Add a calibration point.
        
        Args:
            x (int): X coordinate
            y (int): Y coordinate
            
        Returns:
            bool: True if point was added, False otherwise
        """
        if self.current_point_index >= len(self.luminance_values):
            print("All points already added!")
            return False
            
        point_data = {
            "id": self.current_point_index,
            "x": int(x),
            "y": int(y),
            "luminance": self.luminance_values[self.current_point_index],
            "label": self.point_labels[self.current_point_index]
        }
        
        self.points.append(point_data)
        self.current_point_index += 1
        
        print(f"Added {point_data['label']}: ({x}, {y}) = {point_data['luminance']} cd/m²")
        return True
        
    def undo_last_point(self):
        """
        Remove the last added point.
        
        Returns:
            bool: True if point was removed, False if no points to remove
        """
        if len(self.points) == 0:
            print("No points to undo!")
            return False
            
        removed_point = self.points.pop()
        self.current_point_index -= 1
        self.all_points_marked_printed = False
        
        print(f"Removed {removed_point['label']}")
        return True
        
    def remove_point_at_position(self, x, y, radius=10):
        """
        Remove a point if clicked near its location.
        
        Args:
            x (int): X coordinate in original image space
            y (int): Y coordinate in original image space
            radius (int): Click radius in pixels
            
        Returns:
            bool: True if point was removed, False otherwise
        """
        for i, point in enumerate(self.points):
            px, py = point["x"], point["y"]
            distance = ((x - px)**2 + (y - py)**2)**0.5
            
            if distance <= radius:
                removed = self.points.pop(i)
                if removed["id"] < self.current_point_index:
                    self.current_point_index = removed["id"]
                self.all_points_marked_printed = False 
                print(f"Removed {removed['label']} at ({px}, {py})")
                return True
                
        return False
        
    def get_output_data(self):
        """
        Generate output data dictionary for JSON export.
        
        Returns:
            dict: Calibration data in JSON format
        """
        return {
            "sensor_id": self.sensor_id,
            "hdr_file": self.hdr_path,
            "points": self.points
        }
        
    def load_hdr_image(self):
        """
        Load HDR image and prepare for display.
        
        Returns:
            bool: True if successful, False otherwise
        """
        self.hdr_image = cv2.imread(self.hdr_path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
        
        if self.hdr_image is None:
            print(f"Error: Could not load HDR image: {self.hdr_path}")
            return False
            
        self.image_height, self.image_width = self.hdr_image.shape[:2]
        print(f"Loaded HDR image: {self.image_width}x{self.image_height}")
        
        self._prepare_display_image()
        
        return True
        
    def _prepare_display_image(self):
        """Apply tone mapping and scaling for display."""

        if len(self.hdr_image.shape) == 3:
            hdr_gray = np.mean(self.hdr_image, axis=2)
        else:
            hdr_gray = self.hdr_image
            
        disp = np.log(hdr_gray + 1e-3)
        disp = cv2.normalize(disp, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        disp = cv2.cvtColor(disp, cv2.COLOR_GRAY2BGR)
        
        h, w = disp.shape[:2]
        self.display_scale = min(MAX_DISPLAY_WIDTH / w, MAX_DISPLAY_HEIGHT / h, 1.0)
        
        new_w = int(w * self.display_scale)
        new_h = int(h * self.display_scale)
        self.display_image = cv2.resize(disp, (new_w, new_h))
        
        print(f"Display size: {new_w}x{new_h} (scale: {self.display_scale:.3f})")
        
    def _redraw_interface(self):
        """Redraw the interface with all current points."""
        if len(self.hdr_image.shape) == 3:
            hdr_gray = np.mean(self.hdr_image, axis=2)
        else:
            hdr_gray = self.hdr_image
            
        disp = np.log(hdr_gray + 1e-3)
        disp = cv2.normalize(disp, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        disp = cv2.cvtColor(disp, cv2.COLOR_GRAY2BGR)
        
        h, w = disp.shape[:2]
        new_w = int(w * self.display_scale)
        new_h = int(h * self.display_scale)
        temp_disp = cv2.resize(disp, (new_w, new_h))
        
        if self.hover_x is not None and self.hover_y is not None:
            temp_disp = self._draw_magnifier(temp_disp, disp)
        
        for point in self.points:
            draw_x = int(point["x"] * self.display_scale)
            draw_y = int(point["y"] * self.display_scale)
            
            cv2.circle(temp_disp, (draw_x, draw_y), 5, (0, 0, 255), -1)
            
            label_text = f"{point['id']}"
            cv2.putText(temp_disp, label_text, (draw_x + 8, draw_y - 8),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        if self.current_point_index < len(self.luminance_values):
            next_label = self.point_labels[self.current_point_index]
            next_luminance = self.luminance_values[self.current_point_index]
            status = f"Click: {next_label} ({next_luminance} cd/m2) [{self.current_point_index}/{len(self.luminance_values)}]"
        else:
            status = f"All points marked! Press 'q' to save. | Click point to deselect."
            
        cv2.putText(temp_disp, status, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        
        instructions = "Controls: Left-Click=Add/Remove | 'u'=Undo | 'n'=Skip | 'q'=Save&Quit | ESC=Quit"
        cv2.putText(temp_disp, instructions, (10, new_h - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        cv2.imshow("Calibration Mapper", temp_disp)
    
    def _draw_magnifier(self, display_image, full_resolution_image):
        """Draw magnifier zoom box in top right corner."""
        mag_size = self.magnifier_size
        img_h, img_w = display_image.shape[:2]
        
        mag_x = img_w - mag_size - 5
        mag_y = 0  
        
        zoom_half = self.magnifier_zoom
        x_min = max(0, self.hover_x - zoom_half)
        x_max = min(full_resolution_image.shape[1], self.hover_x + zoom_half)
        y_min = max(0, self.hover_y - zoom_half)
        y_max = min(full_resolution_image.shape[0], self.hover_y + zoom_half)
        
        zoomed_region = full_resolution_image[y_min:y_max, x_min:x_max]
        
        if zoomed_region.size == 0:
            return display_image
        
        zoomed_resized = cv2.resize(zoomed_region, (mag_size, mag_size), interpolation=cv2.INTER_NEAREST)
        
        cv2.rectangle(display_image, (mag_x-2, mag_y-2), (mag_x+mag_size+2, mag_y+mag_size+2), (255, 255, 255), 2)
        
        display_image[mag_y:mag_y+mag_size, mag_x:mag_x+mag_size] = zoomed_resized
        
        center_x = mag_x + mag_size // 2
        center_y = mag_y + mag_size // 2
        cv2.line(display_image, (center_x, mag_y), (center_x, mag_y+mag_size), (0, 0, 255), 1)
        cv2.line(display_image, (mag_x, center_y), (mag_x+mag_size, center_y), (0, 0, 255), 1)
        
        coord_text = f"[{self.hover_x}, {self.hover_y}]"
        cv2.putText(display_image, coord_text, (mag_x, mag_y - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return display_image
        
    def _onclick_callback(self, event, x, y, flags, param):
        """Mouse callback handler for click and motion events."""
        orig_x = int(x / self.display_scale)
        orig_y = int(y / self.display_scale)
        
        if validate_point_coordinates(orig_x, orig_y, self.image_width, self.image_height):
            self.hover_x = orig_x
            self.hover_y = orig_y
            if event == cv2.EVENT_MOUSEMOVE:
                self._redraw_interface()
        
        if event == cv2.EVENT_LBUTTONDOWN:
            if not validate_point_coordinates(orig_x, orig_y, self.image_width, self.image_height):
                print(f"Click outside image bounds: ({orig_x}, {orig_y})")
                return
            
            if self.remove_point_at_position(orig_x, orig_y, radius=15):
                self._redraw_interface()

            elif self.add_point(orig_x, orig_y):
                self._redraw_interface()
                
    def run(self):
        """
        Run the interactive calibration mapper.
        
        Returns:
            bool: True if successful and points saved, False otherwise
        """
        if not self.load_hdr_image():
            return False
            
        cv2.namedWindow("Calibration Mapper", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Calibration Mapper", MAX_DISPLAY_WIDTH, MAX_DISPLAY_HEIGHT)
        cv2.setMouseCallback("Calibration Mapper", self._onclick_callback)
        
        print("\n" + "="*80)
        print("CALIBRATION POINT MAPPER - INSTRUCTIONS")
        print("="*80)
        print("Click on the image to add calibration points in order:")
        for i, (label, lum) in enumerate(zip(self.point_labels, self.luminance_values)):
            print(f"  {i}. {label}: {lum} cd/m²")
        print("\nControls:")
        print("  - Left Click: Add calibration point")
        print("  - 'u': Undo last point")
        print("  - 'n': Skip current point")
        print("  - 'q': Save and quit")
        print("  - ESC: Quit without saving")
        print("="*80 + "\n")
        
        self._redraw_interface()
        
        saved = False
        while True:
            key = cv2.waitKey(20) & 0xFF
            
            if key == ord('u'):
                if self.undo_last_point():
                    self._redraw_interface()
                    
            elif key == ord('n'):
                if self.current_point_index < len(self.luminance_values):
                    print(f"Skipped {self.point_labels[self.current_point_index]}")
                    self.current_point_index += 1
                    self.all_points_marked_printed = False  
                    self._redraw_interface()
                    
            elif key == ord('q'):
                if len(self.points) > 0:
                    output_path = os.path.join(OUTPUT_FOLDER, f"{self.sensor_id}_calibration_points.json")
                    output_data = self.get_output_data()
                    save_calibration_points(output_path, output_data)
                    print(f"\nSaved {len(self.points)} calibration points.")
                    saved = True
                else:
                    print("No points to save!")
                break
                
            elif key == 27:  
                print("Quit without saving.")
                break
                
            if self.current_point_index >= len(self.luminance_values) and not self.all_points_marked_printed:
                print("\nAll points marked! Press 'q' to save or ESC to quit.")
                self.all_points_marked_printed = True
                    
        cv2.destroyAllWindows()
        return saved


def main():
    """Main entry point for the calibration mapper."""
    print("\n" + "="*80)
    print("CALIBRATION POINT MAPPER - INITIALIZATION")
    print("="*80 + "\n")
    
    sensor_id = sys.argv[1] if len(sys.argv) > 1 else "sensor11"
    print(f"Sensor ID: {sensor_id}")
    
    csv_path = None
    if len(sys.argv) > 2:
        csv_path = sys.argv[2]
    else:
        csv_files = list(Path(INPUT_FOLDER).glob("*.csv"))
        if csv_files:
            print(f"\nFound {len(csv_files)} CSV file(s) in {INPUT_FOLDER}:")
            for i, csv_file in enumerate(csv_files, 1):
                print(f"  {i}. {csv_file.name}")
            csv_path = str(csv_files[0])
            print(f"\nUsing: {csv_files[0].name}")
        else:
            print(f"\n✗ No CSV files found in {INPUT_FOLDER}")
            print("Usage: python 04_map_cal_points.py <sensor_id> <csv_path>")
            return 1
    
    print(f"\nLoading calibration data from: {csv_path}")
    luminance_values, point_labels = load_calibration_csv(csv_path)
    
    if luminance_values is None or point_labels is None:
        return 1
        
    print(f"Calibration points:")
    for label, luminance in zip(point_labels, luminance_values):
        print(f"  - {label}: {luminance} cd/m²")
    
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    print("\nLooking for HDR file...")
    hdr_path, hdr_source = find_hdr_file(sensor_id)
    
    if hdr_path is None:
        print(f"\n✗ Error: HDR file not found for {sensor_id}")
        print("Please run Phase 3 (03_generate_hdr.py) first to generate the HDR image.")
        return 1
        
    print(f"\nStarting calibration mapper...\n")
    mapper = CalibrationMapper(hdr_path, luminance_values, point_labels)
    success = mapper.run()
    
    if success:
        print("\n" + "="*80)
        print("CALIBRATION MAPPING COMPLETE!")
        print("="*80)
        print(f"Output: {os.path.join(OUTPUT_FOLDER, f'{sensor_id}_calibration_points.json')}")
        return 0
    else:
        print("\nCalibration mapping cancelled or failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
