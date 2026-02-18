# ==============================================================================
# Project: Spatial-Spectral Sensing System
# Paper:   Enabling scalable, human-centric daylight assessment: A validated open-source sensing system for spatial-spectral monitoring in buildings
# Author:  Tobias Kristiansen / NMBU Building Physics
# License: GNU General Public License v3.0
#
# Description:
# Validate HDR calibration: Validates calibrated HDR accuracy, generates falsecolor visualization
# CCreates validation report
# ==============================================================================

import numpy as np
import cv2
import json
import matplotlib
matplotlib.use('Agg')  
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from pathlib import Path
from typing import List, Dict, Any, Tuple
import sys
from datetime import datetime


def compute_luminance(rgb: np.ndarray) -> np.ndarray:
    """
    Convert RGB to luminance using ITU-R BT.709 coefficients.
    
    Args:
        rgb: BGR image array (OpenCV format) with shape (H, W, 3)
    
    Returns:
        Luminance array with shape (H, W)
    """
    luminance = 0.2126 * rgb[:, :, 2] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 0]
    return luminance


def extract_hdr_values_at_points(hdr: np.ndarray, points: List[Dict[str, Any]], 
                                 region_size: int = 5) -> List[float]:
    """
    Extract HDR luminance values at calibration points.
    
    Args:
        hdr: HDR image array (H, W, 3) in BGR format
        points: List of calibration points with 'x', 'y' coordinates
        region_size: Size of sampling region (must be odd)
    
    Returns:
        List of HDR luminance values at each point
    """
    if region_size % 2 == 0:
        region_size += 1
    
    half_size = region_size // 2
    height, width = hdr.shape[:2]
    hdr_values = []
    
    for point in points:
        x, y = point['x'], point['y']
        
        y_min = max(0, y - half_size)
        y_max = min(height, y + half_size + 1)
        x_min = max(0, x - half_size)
        x_max = min(width, x + half_size + 1)
        
        region = hdr[y_min:y_max, x_min:x_max, :]
        luminance = compute_luminance(region)
        hdr_value = np.mean(luminance)
        hdr_values.append(float(hdr_value))
    
    return hdr_values


def validate_calibration_accuracy(calibration_report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate calibration accuracy by recomputing errors.
    
    Args:
        calibration_report: Calibration report from Phase 5
    
    Returns:
        Dictionary with validation results
    """
    points = calibration_report['calibration_points']
    
    errors_percent = []
    for point in points:
        measured = point['measured_luminance']
        calibrated = point['calibrated_hdr_value']
        error_pct = abs(calibrated - measured) / measured * 100.0
        errors_percent.append(error_pct)
    
    errors_array = np.array(errors_percent)
    
    validation = {
        "mean_error_percent": float(np.mean(errors_array)),
        "max_error_percent": float(np.max(errors_array)),
        "min_error_percent": float(np.min(errors_array)),
        "points_within_5_percent": int(np.sum(errors_array < 5.0)),
        "points_within_10_percent": int(np.sum(errors_array < 10.0)),
        "points_within_15_percent": int(np.sum(errors_array < 15.0)),
        "total_points": len(points)
    }
    
    return validation


def assess_calibration_quality(calibration_report: Dict[str, Any]) -> Tuple[str, str]:
    """
    Assess overall calibration quality based on validation results.
    
    Args:
        calibration_report: Calibration report from Phase 5
    
    Returns:
        Tuple of (quality_grade, description)
    """
    validation = calibration_report.get('validation', validate_calibration_accuracy(calibration_report))
    
    mean_error = validation['mean_error_percent']
    max_error = validation['max_error_percent']
    
    if mean_error < 5.0 and max_error < 10.0:
        return "EXCELLENT", "Outstanding calibration accuracy"
    elif mean_error < 10.0 and max_error < 20.0:
        return "GOOD", "Very good calibration suitable for most applications"
    elif mean_error < 15.0 and max_error < 30.0:
        return "FAIR", "Acceptable calibration for general use"
    else:
        return "POOR", "Calibration needs improvement"


def generate_falsecolor_matplotlib(hdr: np.ndarray, output_path: str, 
                                   log_scale: bool = True,
                                   calibration_points: List[Dict[str, Any]] = None) -> None:
    """
    Generate falsecolor luminance map using matplotlib.
    
    Args:
        hdr: HDR image array (can be path string or numpy array)
        output_path: Path to save PNG image
        log_scale: Use logarithmic scale for better dynamic range visualization
        calibration_points: Optional list of calibration points to overlay
    """
    if isinstance(hdr, str):
        hdr = cv2.imread(hdr, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
        if hdr is None:
            raise ValueError(f"Failed to load HDR from {hdr}")
    
    luminance = compute_luminance(hdr)
    
    if log_scale:
        lum_display = np.log10(luminance + 1e-6)
        label = 'log₁₀(Luminance) [cd/m²]'
    else:
        lum_display = luminance
        label = 'Luminance [cd/m²]'
    
    fig, ax = plt.subplots(figsize=(14, 10))
    im = ax.imshow(lum_display, cmap='jet', aspect='auto', interpolation='bilinear')
    
    if calibration_points:
        for point in calibration_points:
            x, y = point['x'], point['y']
            circle = Circle((x, y), radius=8, fill=False, 
                          edgecolor='white', linewidth=2.5)
            ax.add_patch(circle)
            ax.text(x, y - 15, point.get('label', f"P{point['id']}"),
                   color='white', fontsize=9, ha='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7))
    
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(label, rotation=270, labelpad=25, fontsize=12)
    
    ax.set_title('Calibrated HDR - Falsecolor Luminance Map', 
                fontsize=14, fontweight='bold', pad=20)
    ax.axis('off')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"Falsecolor image saved to: {output_path}")


def generate_statistics_plot(calibration_report: Dict[str, Any], output_path: str) -> None:
    """
    Generate calibration statistics visualization.
    
    Args:
        calibration_report: Calibration report from Phase 5
        output_path: Path to save PNG image
    """
    points = calibration_report['calibration_points']
    statistics = calibration_report['statistics']
    
    point_labels = [p.get('label', f"P{p['id']}") for p in points]
    errors = [p['error_percent'] for p in points]
    scale_factors = [p['scale_factor'] for p in points]
    measured_lum = [p['measured_luminance'] for p in points]
    calibrated_lum = [p['calibrated_hdr_value'] for p in points]
    
    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)
    
    ax1 = fig.add_subplot(gs[0, :])
    colors = ['green' if e < 10 else 'yellow' if e < 20 else 'red' for e in errors]
    bars = ax1.bar(point_labels, errors, color=colors, alpha=0.7, edgecolor='black')
    ax1.axhline(y=10, color='orange', linestyle='--', linewidth=2, label='10% threshold')
    ax1.axhline(y=5, color='green', linestyle='--', linewidth=2, label='5% threshold')
    ax1.set_xlabel('Calibration Point', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Error (%)', fontsize=11, fontweight='bold')
    ax1.set_title('Calibration Error by Point', fontsize=13, fontweight='bold')
    ax1.legend(loc='upper right')
    ax1.grid(axis='y', alpha=0.3)
    
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.scatter(range(len(scale_factors)), scale_factors, s=100, alpha=0.6, edgecolors='black')
    ax2.axhline(y=statistics['median'], color='red', linestyle='--', 
               linewidth=2, label=f"Median: {statistics['median']:.1f}")
    ax2.set_xlabel('Point Index', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Scale Factor (cd/m²/unit)', fontsize=11, fontweight='bold')
    ax2.set_title('Scale Factor Distribution', fontsize=13, fontweight='bold')
    ax2.legend()
    ax2.grid(alpha=0.3)
    
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.hist(errors, bins=8, color='steelblue', alpha=0.7, edgecolor='black')
    ax3.axvline(x=np.mean(errors), color='red', linestyle='--', 
               linewidth=2, label=f"Mean: {np.mean(errors):.1f}%")
    ax3.set_xlabel('Error (%)', fontsize=11, fontweight='bold')
    ax3.set_ylabel('Frequency', fontsize=11, fontweight='bold')
    ax3.set_title('Error Distribution', fontsize=13, fontweight='bold')
    ax3.legend()
    ax3.grid(axis='y', alpha=0.3)
    
    ax4 = fig.add_subplot(gs[2, :])
    x_pos = np.arange(len(point_labels))
    width = 0.35
    ax4.bar(x_pos - width/2, measured_lum, width, label='Measured', 
           color='blue', alpha=0.7, edgecolor='black')
    ax4.bar(x_pos + width/2, calibrated_lum, width, label='Calibrated', 
           color='orange', alpha=0.7, edgecolor='black')
    ax4.set_xlabel('Calibration Point', fontsize=11, fontweight='bold')
    ax4.set_ylabel('Luminance (cd/m²)', fontsize=11, fontweight='bold')
    ax4.set_title('Measured vs Calibrated Luminance', fontsize=13, fontweight='bold')
    ax4.set_xticks(x_pos)
    ax4.set_xticklabels(point_labels)
    ax4.legend()
    ax4.grid(axis='y', alpha=0.3)
    
    fig.suptitle('HDR Calibration Statistics', fontsize=16, fontweight='bold', y=0.995)
    
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"Statistics plot saved to: {output_path}")


def create_validation_report(calibration_report: Dict[str, Any], output_path: str) -> None:
    """
    Create comprehensive validation report in Markdown format.
    
    Args:
        calibration_report: Calibration report from Phase 5
        output_path: Path to save Markdown file
    """
    sensor_id = calibration_report['sensor_id']
    points = calibration_report['calibration_points']
    statistics = calibration_report['statistics']
    validation = calibration_report.get('validation', validate_calibration_accuracy(calibration_report))
    
    quality, quality_desc = assess_calibration_quality(calibration_report)
    
    report_lines = []
    report_lines.append("# HDR Calibration Validation Report")
    report_lines.append("")
    report_lines.append(f"**Sensor:** {sensor_id}")
    report_lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}")
    report_lines.append(f"**Calibration Method:** Global scale factor (median of {len(points)} points)")
    report_lines.append("")
    
    report_lines.append("## Calibration Summary")
    report_lines.append("")
    report_lines.append(f"- **Median Scale Factor:** {statistics['median']:.2f} cd/m²/unit")
    report_lines.append(f"- **Mean Scale Factor:** {statistics['mean']:.2f} cd/m²/unit")
    report_lines.append(f"- **Scale Factor Std Dev:** {statistics['std_dev']:.2f} cd/m²/unit")
    report_lines.append(f"- **Mean Calibration Error:** {validation['mean_error_percent']:.2f}%")
    report_lines.append(f"- **Max Calibration Error:** {validation['max_error_percent']:.2f}%")
    report_lines.append(f"- **Min Calibration Error:** {validation['min_error_percent']:.2f}%")
    report_lines.append(f"- **Calibration Quality:** **{quality}** - {quality_desc}")
    report_lines.append("")
    
    report_lines.append("## Point-by-Point Validation")
    report_lines.append("")
    report_lines.append("| Point | Location | Measured (cd/m²) | Calibrated (cd/m²) | Error (%) | Status |")
    report_lines.append("|-------|----------|------------------|--------------------|-----------|--------|")
    
    for point in points:
        label = point.get('label', f"Point {point['id']}")
        measured = point['measured_luminance']
        calibrated = point['calibrated_hdr_value']
        error = point['error_percent']
        
        if error < 5.0:
            status = "[OK] EXCELLENT"
        elif error < 10.0:
            status = "[OK] GOOD"
        elif error < 20.0:
            status = "[WARNING] FAIR"
        else:
            status = "[ERROR] POOR"
        
        report_lines.append(f"| {point['id']} | {label} | {measured:.1f} | {calibrated:.2f} | {error:.1f} | {status} |")
    
    report_lines.append("")
    
    report_lines.append("## Quality Assessment")
    report_lines.append("")
    
    center_points = points[:int(len(points)*0.6)]
    edge_points = points[int(len(points)*0.6):]
    
    center_errors = [p['error_percent'] for p in center_points]
    edge_errors = [p['error_percent'] for p in edge_points] if edge_points else [0]
    
    center_mean = np.mean(center_errors)
    edge_mean = np.mean(edge_errors)
    
    def quality_label(error):
        if error < 10:
            return "EXCELLENT"
        elif error < 20:
            return "GOOD"
        else:
            return "FAIR"
    
    report_lines.append(f"- **Center Region (Points 0-{len(center_points)-1}):** {quality_label(center_mean)} ({center_mean:.1f}% avg error)")
    if edge_points:
        report_lines.append(f"- **Edge Region (Points {len(center_points)}-{len(points)-1}):** {quality_label(edge_mean)} ({edge_mean:.1f}% avg error)")
    report_lines.append(f"- **Overall Quality:** {quality}")
    report_lines.append(f"- **Points within 5% error:** {validation['points_within_5_percent']}/{len(points)}")
    report_lines.append(f"- **Points within 10% error:** {validation['points_within_10_percent']}/{len(points)}")
    report_lines.append("")
    
    report_lines.append("## Recommendations")
    report_lines.append("")
    
    if quality == "EXCELLENT":
        report_lines.append("- [OK] Calibration is excellent - ready for production use")
        report_lines.append("- No further adjustments needed")
    elif quality == "GOOD":
        report_lines.append("- [OK] Calibration is good for most applications")
        report_lines.append("- Consider refining calibration points for critical applications")
    elif quality == "FAIR":
        report_lines.append("- Calibration successful for center region")
        if edge_mean > center_mean * 1.5:
            report_lines.append("- Edge errors indicate optical vignetting effects")
            report_lines.append("- Consider vignetting correction for improved accuracy")
        report_lines.append("- Acceptable for general HDR imaging")
    else:
        report_lines.append("- [WARNING] Calibration needs improvement")
        report_lines.append("- Review calibration point selection")
        report_lines.append("- Check HDR generation quality")
        report_lines.append("- Verify measurement accuracy")
    
    report_lines.append("")
    
    if statistics.get('outliers'):
        report_lines.append("## Outlier Analysis")
        report_lines.append("")
        report_lines.append(f"Detected {len(statistics['outliers'])} outlier(s):")
        report_lines.append("")
        for outlier in statistics['outliers']:
            point = points[outlier['index']]
            report_lines.append(f"- **Point {outlier['index']}** ({point.get('label', 'Unknown')}): "
                              f"Scale factor {outlier['scale_factor']:.2f} "
                              f"({outlier['deviation_sigma']:.1f} sigma from median)")
        report_lines.append("")
        report_lines.append("Outliers may indicate:")
        report_lines.append("- Edge vignetting effects")
        report_lines.append("- Lens artifacts")
        report_lines.append("- Measurement errors")
        report_lines.append("")
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    print(f"Validation report saved to: {output_path}")


def main():
    """Main execution function for validation."""
    sensor_id = sys.argv[1] if len(sys.argv) > 1 else "sensor11"
    
    workspace = Path(__file__).parent
    calibration_report_path = workspace / "01_apply_calibration_output" / f"{sensor_id}_calibration_report.json"
    calibrated_hdr_path = workspace / "01_apply_calibration_output" / f"{sensor_id}_calibrated.hdr"
    calibration_points_path = workspace / "01_apply_calibration_input" / f"{sensor_id}_calibration_points.json"
    
    output_dir = workspace / "02_validate_output"
    falsecolor_path = output_dir / f"{sensor_id}_falsecolor.png"
    statistics_path = output_dir / f"{sensor_id}_calibration_stats.png"
    validation_report_path = output_dir / f"{sensor_id}_validation_report.md"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("VALIDATION, VISUALIZATION, AND REPORTING")
    print("=" * 70)
    
    print("\n[1/5] Loading calibration report...")
    if not calibration_report_path.exists():
        print(f"ERROR: Calibration report not found at {calibration_report_path}")
        print("Please run Phase 5 first.")
        sys.exit(1)
    
    with open(calibration_report_path) as f:
        calibration_report = json.load(f)
    
    print(f"  [OK] Loaded report for {calibration_report['sensor_id']}")
    
    print("\n[2/5] Validating calibration accuracy...")
    validation = validate_calibration_accuracy(calibration_report)
    quality, quality_desc = assess_calibration_quality(calibration_report)
    
    print(f"  Mean error: {validation['mean_error_percent']:.2f}%")
    print(f"  Max error: {validation['max_error_percent']:.2f}%")
    print(f"  Min error: {validation['min_error_percent']:.2f}%")
    print(f"  Points within 5%: {validation['points_within_5_percent']}/{validation['total_points']}")
    print(f"  Points within 10%: {validation['points_within_10_percent']}/{validation['total_points']}")
    print(f"  Overall quality: {quality} - {quality_desc}")
    
    print("\n[3/5] Generating falsecolor luminance map...")
    if not calibrated_hdr_path.exists():
        print(f"ERROR: Calibrated HDR not found at {calibrated_hdr_path}")
        sys.exit(1)
    
    calibrated_hdr = cv2.imread(str(calibrated_hdr_path), cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
    if calibrated_hdr is None:
        print(f"ERROR: Failed to load calibrated HDR")
        sys.exit(1)
    
    with open(calibration_points_path) as f:
        calibration_points_data = json.load(f)
    
    generate_falsecolor_matplotlib(
        calibrated_hdr,
        str(falsecolor_path),
        log_scale=True,
        calibration_points=calibration_points_data['points']
    )
    
    print("\n[4/5] Generating calibration statistics plot...")
    generate_statistics_plot(calibration_report, str(statistics_path))
    
    print("\n[5/5] Creating validation report...")
    create_validation_report(calibration_report, str(validation_report_path))
    
    print("\n" + "=" * 70)
    print("VALIDATION COMPLETE!")
    print("=" * 70)
    print("\nOutputs:")
    print(f"  • Falsecolor map: {falsecolor_path.name}")
    print(f"  • Statistics plot: {statistics_path.name}")
    print(f"  • Validation report: {validation_report_path.name}")
    print(f"\nValidation Results:")
    print(f"  • Calibration quality: {quality}")
    print(f"  • Mean error: {validation['mean_error_percent']:.2f}%")
    print(f"  • Accurate points (+/-10%): {validation['points_within_10_percent']}/{validation['total_points']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
