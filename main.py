"""Runs all EC_*.json cases in input/ through the multi-agent pipeline and
writes output/EC_*.json, trace.jsonl and metadata.json at repo root.

Usage:
    py main.py                # all 50 cases
    py main.py EC_001         # single case, for quick iteration
"""

from __future__ import annotations

import json
import os
import sys
import time

import pandas as pd

from src.coordinator import process_case
from src.data_layer import OlistData
from src.llm_client import MODEL_NAME


def _json_default(obj):
    if isinstance(obj, pd.Timestamp):
        return None if pd.isna(obj) else obj.strftime("%Y-%m-%d %H:%M:%S")
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    return str(obj)

ROOT = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(ROOT, "input")
OUTPUT_DIR = os.path.join(ROOT, "output")
DATA_DIR = os.path.join(ROOT, "data")
TRACE_PATH = os.path.join(ROOT, "trace.jsonl")
METADATA_PATH = os.path.join(ROOT, "metadata.json")


class TraceWriter:
    def __init__(self, path: str):
        self._fh = open(path, "w", encoding="utf-8")

    def write_line(self, obj: dict) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False, default=_json_default) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def write_metadata(num_cases: int, elapsed_s: float) -> None:
    metadata = {
        "model": MODEL_NAME,
        "parameter_size": "8B",
        "provider": "Groq (cloud API, OpenAI-compatible endpoint)",
        "framework": "custom Python multi-agent pipeline (no agent framework dependency)",
        "runtime": {
            "python_version": sys.version.split()[0],
            "os": sys.platform,
        },
        "agents": [
            "customer_agent",
            "order_product_agent",
            "payment_agent",
            "delivery_agent",
            "policy_agent",
            "verifier_agent",
        ],
        "policy_version": "EC_POLICY_V2",
        "cases_processed": num_cases,
        "elapsed_seconds": round(elapsed_s, 2),
    }
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    only = sys.argv[1] if len(sys.argv) > 1 else None
    case_files = sorted(f for f in os.listdir(INPUT_DIR) if f.endswith(".json"))
    if only:
        case_files = [f for f in case_files if f.startswith(only)]

    print(f"Loading Olist CSVs from {DATA_DIR} ...")
    data = OlistData(DATA_DIR)

    trace = TraceWriter(TRACE_PATH)
    start = time.time()
    ok_count = 0
    fail_count = 0

    try:
        for fname in case_files:
            with open(os.path.join(INPUT_DIR, fname), "r", encoding="utf-8") as f:
                case_input = json.load(f)
            case_id = case_input["case_id"]
            try:
                output = process_case(case_input, data, trace)
            except Exception as exc:  # noqa: BLE001 - report and continue with next case
                print(f"[FAIL] {case_id}: {exc}")
                fail_count += 1
                continue

            out_path = os.path.join(OUTPUT_DIR, f"{case_id}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            ok_count += 1
            print(f"[OK]   {case_id}: {output['case_assessment']['primary_issue']}")
    finally:
        trace.close()

    elapsed = time.time() - start
    write_metadata(ok_count, elapsed)
    print(f"\nDone: {ok_count} ok, {fail_count} failed, {elapsed:.1f}s total.")


if __name__ == "__main__":
    main()
