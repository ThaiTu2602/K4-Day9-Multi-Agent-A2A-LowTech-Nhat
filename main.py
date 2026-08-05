import argparse
import os
import sys
from pathlib import Path
from src.config import INPUT_DIR, TRACE_FILE, TRACE_FILE_LOGGING, METADATA_FILE, METADATA_FILE_LOGGING
from src.coordinator import Coordinator

def main():
    parser = argparse.ArgumentParser(description="Multi-Agent E-commerce Dispute Resolution System")
    parser.add_argument("--single", type=str, help="Process a single case ID (e.g. EC_001)", default=None)
    args = parser.parse_args()

    # Reset trace files if running full batch
    if not args.single:
        if TRACE_FILE.exists():
            TRACE_FILE.unlink()
        if TRACE_FILE_LOGGING.exists():
            TRACE_FILE_LOGGING.unlink()
        print(f"Initialized fresh trace files at {TRACE_FILE} and {TRACE_FILE_LOGGING}")

    # Ensure metadata.json is synced to logging/metadata.json
    if METADATA_FILE.exists():
        import shutil
        shutil.copy(METADATA_FILE, METADATA_FILE_LOGGING)


    coordinator = Coordinator()

    if args.single:
        case_file = INPUT_DIR / f"{args.single}.json"
        if not case_file.exists():
            print(f"Error: Case file {case_file} does not exist!")
            sys.exit(1)
        print(f"--- Running Test Case: {args.single} ---")
        coordinator.process_case(case_file)
        print(f"--- Completed Test Case: {args.single} ---")
    else:
        case_files = sorted(list(INPUT_DIR.glob("EC_*.json")))
        print(f"Found {len(case_files)} cases in {INPUT_DIR}. Starting Multi-Agent Pipeline...")
        for idx, case_file in enumerate(case_files, 1):
            print(f"[{idx}/{len(case_files)}] Processing {case_file.name}...")
            try:
                coordinator.process_case(case_file)
            except Exception as e:
                print(f"Error processing {case_file.name}: {e}")

        print(f"=== ALL {len(case_files)} CASES PROCESSED SUCCESSFULLY ===")

if __name__ == "__main__":
    main()
