# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Interactive ROI/Crop Selection Tool
# Allows user to define elliptical ROI for image cropping using OpenCV GUI.
# ==============================================================================

import cv2
import json
import os
import re
import sys
import numpy as np
from pathlib import Path
from typing import Dict, Optional

g_scale_factor = 1.0

class ROIManager:
    """Manages ROI parameters for multiple sensors with JSON persistence."""
    
    def __init__(self, json_path: Optional[str] = None):
        """
        Initialize ROI Manager.
        
        Args:
            json_path: Path to JSON file for saving/loading ROI parameters.
        """
        self.json_path = json_path
        self.roi_data: Dict[str, Dict[str, int]] = {}
        
        if self.json_path and os.path.exists(self.json_path):
            self.load()
    
    def set_roi(self, sensor_id: str, center_x: int, center_y: int, 
                radius_x: int, radius_y: int) -> None:
        """
        Set ROI parameters for a sensor.
        
        Args:
            sensor_id: Sensor identifier (e.g., "sensor11")
            center_x: X coordinate of ellipse center
            center_y: Y coordinate of ellipse center
            radius_x: Horizontal radius of ellipse
            radius_y: Vertical radius of ellipse
        """
        self.roi_data[sensor_id] = {
            "center_x": int(center_x),
            "center_y": int(center_y),
            "radius_x": int(radius_x),
            "radius_y": int(radius_y)
        }
    
    def get_roi(self, sensor_id: str) -> Dict[str, int]:
        """
        Get ROI parameters for a sensor.
        
        Args:
            sensor_id: Sensor identifier
            
        Returns:
            Dictionary with ROI parameters
        """
        if sensor_id not in self.roi_data:
            raise ValueError(f"No ROI data found for {sensor_id}")
        return self.roi_data[sensor_id]
    
    def save(self) -> None:
        """Save ROI parameters to JSON file."""
        if not self.json_path:
            raise ValueError("No JSON path specified")
        
        os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
        
        with open(self.json_path, 'w') as f:
            json.dump(self.roi_data, f, indent=2)
    
    def load(self) -> None:
        """Load ROI parameters from JSON file."""
        if not self.json_path:
            raise ValueError("No JSON path specified")
        
        if os.path.exists(self.json_path):
            with open(self.json_path, 'r') as f:
                self.roi_data = json.load(f)
    
    def apply_ellipse_mask(self, sensor_id: str, image: np.ndarray) -> np.ndarray:
        """
        Apply ellipse mask to image.
        
        Args:
            sensor_id: Sensor identifier
            image: Input image (numpy array)
            
        Returns:
            Masked image with pixels outside ellipse set to black
        """
        params = self.get_roi(sensor_id)
        center_x = params["center_x"]
        center_y = params["center_y"]
        radius_x = params["radius_x"]
        radius_y = params["radius_y"]
        
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        cv2.ellipse(mask, (center_x, center_y), (radius_x, radius_y), 
                   0, 0, 360, 255, -1)
        
        if len(image.shape) == 3:
            masked_image = cv2.bitwise_and(image, image, mask=mask)
        else:
            masked_image = cv2.bitwise_and(image, image, mask=mask)
        
        return masked_image
    
    def crop_to_bbox(self, sensor_id: str, image: np.ndarray) -> np.ndarray:
        """
        Crop image to ellipse bounding box.
        
        Args:
            sensor_id: Sensor identifier
            image: Input image (numpy array)
            
        Returns:
            Cropped image
        """
        params = self.get_roi(sensor_id)
        center_x = params["center_x"]
        center_y = params["center_y"]
        radius_x = params["radius_x"]
        radius_y = params["radius_y"]
        
        x1 = max(0, center_x - radius_x)
        y1 = max(0, center_y - radius_y)
        x2 = min(image.shape[1], center_x + radius_x)
        y2 = min(image.shape[0], center_y + radius_y)
        
        cropped_image = image[y1:y2, x1:x2]
        
        return cropped_image
    
    def apply_roi(self, sensor_id: str, image: np.ndarray) -> np.ndarray:
        """
        Apply full ROI processing: mask and crop.
        
        Args:
            sensor_id: Sensor identifier
            image: Input image (numpy array)
            
        Returns:
            Processed image with mask applied and cropped to bounding box
        """
        masked_image = self.apply_ellipse_mask(sensor_id, image)
        cropped_image = self.crop_to_bbox(sensor_id, masked_image)
        
        return cropped_image

def mouse_callback(event, x, y, flags, param_state):
    """
    Handles mouse events for drawing an ellipse.
    
    Args:
        event: OpenCV mouse event
        x: Mouse x coordinate
        y: Mouse y coordinate
        flags: Additional flags
        param_state: Dictionary containing ellipse parameters and drawing state
    """
    global g_scale_factor
    
    orig_x = int(x / g_scale_factor)
    orig_y = int(y / g_scale_factor)
    
    if event == cv2.EVENT_LBUTTONDOWN:
        param_state['drawing'] = True
        param_state['center_x'] = orig_x
        param_state['center_y'] = orig_y
        param_state['radius_x'] = 0
        param_state['radius_y'] = 0
    elif event == cv2.EVENT_MOUSEMOVE:
        if param_state['drawing']:
            param_state['radius_x'] = abs(orig_x - param_state['center_x'])
            param_state['radius_y'] = abs(orig_y - param_state['center_y'])
    elif event == cv2.EVENT_LBUTTONUP:
        param_state['drawing'] = False
        param_state['radius_x'] = abs(orig_x - param_state['center_x'])
        param_state['radius_y'] = abs(orig_y - param_state['center_y'])


def extract_sensor_id(filename: str) -> str:
    """
    Extract sensor ID from filename.
    
    Args:
        filename: Image filename (e.g., "20250130_154816_sensor11_exp10.jpeg")
        
    Returns:
        Sensor ID (e.g., "sensor11") or None if not found
    """
    match = re.search(r'(sensor\d{2})', filename, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def print_instructions():
    """Print usage instructions."""
    print("\n--- INSTRUCTIONS ---")
    print("  Mouse:      Click & Drag to define the ellipse's bounding box.")
    print("  Keyboard:   W,A,S,D to nudge center.")
    print("  Adjust Rx:  i (decrease), k (increase)")
    print("  Adjust Ry:  j (decrease), l (increase)")
    print("  Workflow:   'n' for Next, 'q' to Quit & Save.")
    print("  Display:    Current parameters shown on screen")
    print("-------------------------------------------------------")


def main():
    """Main interactive ROI selection workflow."""
    global g_scale_factor
    
    script_path = Path(__file__).parent
    input_folder = script_path / '01_define_roi_input'
    output_folder = script_path / '01_define_roi_output'
    json_path = output_folder / 'roi_params.json'
    
    os.makedirs(input_folder, exist_ok=True)
    os.makedirs(output_folder, exist_ok=True)
    
    roi_manager = ROIManager(json_path=str(json_path))
    
    print("=== Interactive ROI/Crop Selection Tool ===")
    
    if not os.path.isdir(input_folder):
        print(f"\nERROR: The '{input_folder}' directory was not found.")
        return
    
    image_files = [f for f in os.listdir(input_folder) 
                   if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    if not image_files:
        print(f"\nERROR: No images found in '{input_folder}'.")
        print("Please place your bracketed JPEG images in this folder and run again.")
        return
    
    print(f"Found {len(image_files)} images.")
    print_instructions()
    
    for filename in sorted(image_files):
        sensor_id = extract_sensor_id(filename)
        if not sensor_id:
            print(f"Skipping {filename}: no sensor ID found.")
            continue
        
        image_path = input_folder / filename
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"Skipping {filename}: could not read image.")
            continue
        
        print(f"\nNow defining ROI for: {filename} (Sensor: {sensor_id})")
        
        height, width, _ = image.shape
        window_name = f"Define ROI: {filename} (n=Next, q=Quit)"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        
        MAX_DISPLAY_WIDTH = 1200
        MAX_DISPLAY_HEIGHT = 900
        g_scale_factor = min(MAX_DISPLAY_WIDTH / width, 
                            MAX_DISPLAY_HEIGHT / height, 
                            1.0)
        
        display_width = int(width * g_scale_factor)
        display_height = int(height * g_scale_factor)
        cv2.resizeWindow(window_name, display_width, display_height)
        
        try:
            existing_params = roi_manager.get_roi(sensor_id)
            current_state = {
                'center_x': existing_params['center_x'],
                'center_y': existing_params['center_y'],
                'radius_x': existing_params['radius_x'],
                'radius_y': existing_params['radius_y'],
                'drawing': False
            }
            print(f"Loaded existing ROI parameters for {sensor_id}")
        except (ValueError, KeyError):
            current_state = {
                'center_x': int(width / 2),
                'center_y': int(height / 2),
                'radius_x': int(width / 4),
                'radius_y': int(height / 4),
                'drawing': False
            }
        
        cv2.setMouseCallback(window_name, mouse_callback, current_state)
        
        while True:
            display_image = image.copy()
            cx = current_state['center_x']
            cy = current_state['center_y']
            rx = current_state['radius_x']
            ry = current_state['radius_y']
            
            cv2.ellipse(display_image, (cx, cy), (rx, ry), 0, 0, 360, (0, 0, 255), 2)
            cv2.line(display_image, (cx - 15, cy), (cx + 15, cy), (0, 255, 0), 2)
            cv2.line(display_image, (cx, cy - 15), (cx, cy + 15), (0, 255, 0), 2)
            
            text_lines = [
                f"Sensor: {sensor_id}",
                f"Center: ({cx}, {cy})",
                f"Radius: ({rx}, {ry})",
                "Controls: WASD=center, IK=Rx, JL=Ry"
            ]
            
            box_padding = 10
            line_height = 35
            box_height = len(text_lines) * line_height + box_padding * 2
            box_width = 400
            
            overlay = display_image.copy()
            cv2.rectangle(overlay, (5, 5), (5 + box_width, 5 + box_height), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.7, display_image, 0.3, 0, display_image)
            
            text_y = 30
            cv2.putText(display_image, text_lines[0], (15, text_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            text_y += line_height
            cv2.putText(display_image, text_lines[1], (15, text_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            text_y += line_height
            cv2.putText(display_image, text_lines[2], (15, text_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            text_y += line_height
            cv2.putText(display_image, text_lines[3], (15, text_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 2)
            
            scaled_display = cv2.resize(display_image, (display_width, display_height))
            cv2.imshow(window_name, scaled_display)
            
            key = cv2.waitKey(20) & 0xFF
            
            if key != 255:
                if key == ord('w'):
                    current_state['center_y'] = max(0, current_state['center_y'] - 1)
                elif key == ord('s'):
                    current_state['center_y'] = min(height - 1, current_state['center_y'] + 1)
                elif key == ord('a'):
                    current_state['center_x'] = max(0, current_state['center_x'] - 1)
                elif key == ord('d'):
                    current_state['center_x'] = min(width - 1, current_state['center_x'] + 1)
                
                elif key == ord('j'):
                    current_state['radius_x'] = max(1, current_state['radius_x'] - 1)
                elif key == ord('l'):
                    current_state['radius_x'] = min(width // 2, current_state['radius_x'] + 1)
                elif key == ord('i'):
                    current_state['radius_y'] = max(1, current_state['radius_y'] - 1)
                elif key == ord('k'):
                    current_state['radius_y'] = min(height // 2, current_state['radius_y'] + 1)
                
                elif key == ord('n'):
                    roi_manager.set_roi(sensor_id, cx, cy, rx, ry)
                    print(f"Saved ROI for {sensor_id}: center=({cx},{cy}), radius=({rx},{ry})")
                    break
                
                elif key == ord('q'):
                    roi_manager.set_roi(sensor_id, cx, cy, rx, ry)
                    print(f"Saved ROI for {sensor_id}: center=({cx},{cy}), radius=({rx},{ry})")
                    print("\nQuitting...")
                    cv2.destroyAllWindows()
                    roi_manager.save()
                    print(f"ROI parameters saved to: {json_path}")
                    return
        
        cv2.destroyWindow(window_name)
    
    roi_manager.save()
    print(f"\n=== ROI Selection Complete ===")
    print(f"ROI parameters saved to: {json_path}")
    print(f"Total sensors processed: {len(roi_manager.roi_data)}")


if __name__ == "__main__":
    main()
