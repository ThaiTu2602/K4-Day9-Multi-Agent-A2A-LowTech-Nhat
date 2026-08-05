"""
main.py — Entry point của pipeline
Chạy toàn bộ 50 case từ input/ và ghi kết quả ra output/

Cách dùng:
    python main.py              # chạy tất cả 50 case
    python main.py EC_001       # chạy 1 case cụ thể
    python main.py EC_001 EC_005  # chạy nhiều case
"""
import json
import sys
import time
from pathlib import Path

from core.data_loader import DataStore
from agents.coordinator import CoordinatorAgent

INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")


def run(case_ids: list[str] | None = None) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    # ── Tải dữ liệu một lần ──────────────────────────────────────────────────
    store = DataStore()
    coordinator = CoordinatorAgent(store)
    CoordinatorAgent.write_metadata()

    # ── Xác định các file cần chạy ───────────────────────────────────────────
    if case_ids:
        input_files = sorted(
            INPUT_DIR / f"{cid}.json"
            for cid in case_ids
            if (INPUT_DIR / f"{cid}.json").exists()
        )
    else:
        input_files = sorted(INPUT_DIR.glob("EC_*.json"))

    if not input_files:
        print("Không tìm thấy input file nào.")
        return

    # ── Clear trace files (chỉ giữ lượt chạy mới nhất ở cả root và logging/) ─
    for tp in (Path("trace.jsonl"), Path("logging/trace.jsonl")):
        tp.parent.mkdir(exist_ok=True)
        tp.write_text("", encoding="utf-8")  # clear

    # ── Chạy pipeline ────────────────────────────────────────────────────────
    total_start = time.perf_counter()
    print(f"\n{'='*60}")
    print(f" E-Commerce Dispute Resolution Pipeline")
    print(f" Processing {len(input_files)} case(s)...")
    print(f"{'='*60}\n")

    success = 0
    errors = 0

    for input_file in input_files:
        try:
            with open(input_file, encoding="utf-8") as f:
                case = json.load(f)

            result = coordinator.process(case)

            output_file = OUTPUT_DIR / input_file.name
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            success += 1

        except Exception as exc:
            print(f"  [ERROR] {input_file.name}: {exc}")
            errors += 1

    elapsed = round(time.perf_counter() - total_start, 1)
    print(f"\n{'='*60}")
    print(f" Done: {success} succeeded, {errors} failed — {elapsed}s total")
    print(f" Output: {OUTPUT_DIR.resolve()}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    run(args if args else None)
