"""
Restructure raw spectral CSV files into clean tabular format.

Each input CSV contains multiple measurement blocks. This script extracts:
  Modify Time, Device Name, Is Saturate, Integration Time(ms),
  Photopic Lux, Melanopic, CCT, and per-wavelength Spectrum values.

One output CSV is produced per input file, saved alongside the originals
with the prefix "restructured_".
"""

import csv
import os
import glob


SCALAR_FIELDS = [
    "Modify Time",
    "Device Name",
    "Is Saturate",
    "Integration Time(ms)",
    "Photopic Lux",
    "Melanopic",
    "CCT",
]


def parse_blocks(filepath):
    """Parse a raw CSV file into a list of measurement-block dicts."""
    blocks = []
    current = {}

    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or all(cell.strip() == "" for cell in row):
                if current:
                    blocks.append(current)
                    current = {}
                continue

            key = row[0].strip()
            values = [v.strip() for v in row[1:]]

            if key == "File Name":
                # Start of a new block; save any previous one first
                if current:
                    blocks.append(current)
                current = {}

            if key in ("Wavelength", "Spectrum"):
                current[key] = values
            elif values:
                current[key] = values[0] if len(values) == 1 else values[0]

    if current:
        blocks.append(current)

    return blocks


def build_wavelength_headers(blocks):
    """Return wavelength labels from the first block that has them."""
    for block in blocks:
        if "Wavelength" in block:
            return block["Wavelength"]
    return []


def restructure_file(input_path, output_path):
    blocks = parse_blocks(input_path)
    if not blocks:
        print(f"  No data found in {os.path.basename(input_path)}, skipping.")
        return

    wavelengths = build_wavelength_headers(blocks)
    spectrum_headers = [f"Spectrum_{wl}" for wl in wavelengths]
    headers = SCALAR_FIELDS + spectrum_headers

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for block in blocks:
            spectrum_values = block.get("Spectrum", [])
            # Pad or truncate to match wavelength count
            spectrum_values = (spectrum_values + [""] * len(wavelengths))[: len(wavelengths)]

            row = [block.get(field, "") for field in SCALAR_FIELDS] + spectrum_values
            writer.writerow(row)

    print(f"  Written {len(blocks)} rows -> {os.path.basename(output_path)}")


def main():
    folder = os.path.dirname(os.path.abspath(__file__))
    csv_files = glob.glob(os.path.join(folder, "*.csv"))

    # Exclude files we already produced
    input_files = [p for p in csv_files if not os.path.basename(p).startswith("restructured_")]

    if not input_files:
        print("No CSV files found to process.")
        return

    print(f"Processing {len(input_files)} file(s) in:\n  {folder}\n")
    for input_path in input_files:
        basename = os.path.basename(input_path)
        output_path = os.path.join(folder, f"restructured_{basename}")
        print(f"Processing: {basename}")
        restructure_file(input_path, output_path)

    print("\nDone.")


if __name__ == "__main__":
    main()
