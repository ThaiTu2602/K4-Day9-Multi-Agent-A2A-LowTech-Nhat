import os
import json
import zipfile
from pathlib import Path

def create_submission_zip():
    base_dir = Path(__file__).resolve().parent
    output_dir = base_dir / "output"
    zip_path = base_dir / "submission_output.zip"

    # Find all JSON files in output/
    json_files = sorted(list(output_dir.glob("EC_*.json")))
    
    print(f"Checking output files in {output_dir}...")
    if len(json_files) != 50:
        print(f"❌ WARNING: Found {len(json_files)} JSON files instead of exactly 50!")
        return

    # Check for non-json files
    non_json_files = [f.name for f in output_dir.glob("*") if not f.name.endswith(".json")]
    if non_json_files:
        print(f"⚠️ Found non-JSON files in output/: {non_json_files}. These will NOT be included in the zip.")

    # Create zip containing strictly the 50 JSON files
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for json_file in json_files:
            # Arcname ensures files are placed inside the zip root (or output/ folder)
            zipf.write(json_file, arcname=json_file.name)

    print(f"Submission zip successfully created at: {zip_path}")
    print(f"Zip contents count: {len(json_files)} files (EC_001.json to EC_050.json)")

if __name__ == "__main__":
    create_submission_zip()

