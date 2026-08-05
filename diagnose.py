"""
Diagnostic script — phan tich trace.jsonl de tim:
  1. Per-case: agent nao co dau hieu bat thuong
  2. Cross-case: thong ke tong hop 50 case
Chay: python diagnose.py
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

TRACE_PATH = Path("logging/trace.jsonl")


def load_trace() -> list[dict]:
    cases = []
    with open(TRACE_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def flag_case(c: dict) -> list[str]:
    flags = []
    ag = c["agents"]
    sm = c["summary"]
    primary = sm["primary_issue"]
    confidence = sm["confidence"]

    # --- Agent 2: Customer ---
    cust = ag.get("customer", {})
    if cust.get("status") != "ok":
        flags.append("CUSTOMER: order/customer not found in CSV")

    # --- Agent 3: Order+Product ---
    op = ag.get("order_product", {})
    if op.get("status") == "no_items":
        flags.append("ORDER_PRODUCT: no item rows (unavailable order)")

    # --- Agent 4: Payment ---
    pay = ag.get("payment", {})
    num_pay = pay.get("num_payments", 0)
    reconciled = pay.get("reconciled")
    pay_total = pay.get("payment_total", 0)

    if reconciled is None and op.get("status") != "no_items":
        flags.append("PAYMENT: reconciled is null despite having items")
    if pay_total == 0:
        flags.append("PAYMENT: payment_total=0")

    # --- Agent 5: Delivery ---
    deliv = ag.get("delivery", {})
    dv = deliv.get("delivery_variance_hours")

    if dv is None and primary in ("late_delivery_seller", "late_delivery_logistics", "unsupported_late_claim"):
        flags.append(f"DELIVERY: variance=null but primary={primary}")

    if dv is not None and 0 < dv < 24:
        flags.append(f"DELIVERY: borderline late delivery ({dv}h < 24h)")

    # --- Agent 6: Policy ---
    if confidence < 0.90:
        flags.append(f"POLICY: confidence low ({confidence})")

    return flags


def analyze():
    cases = load_trace()

    print("=" * 70)
    print(f" DIAGNOSTIC REPORT -- {len(cases)} cases")
    print("=" * 70)

    agent_flag_counts = defaultdict(int)
    flagged_cases = []

    for c in cases:
        flags = flag_case(c)
        if flags:
            flagged_cases.append((c["case_id"], c["summary"]["primary_issue"], flags))
            for f in flags:
                agent = f.split(":")[0]
                agent_flag_counts[agent] += 1

    print(f"\n{'-'*70}")
    print(f" PER-CASE WARNINGS ({len(flagged_cases)}/{len(cases)} cases flagged)")
    print(f"{'-'*70}")

    for case_id, primary, flags in flagged_cases:
        print(f"\n  [{case_id}] primary={primary}")
        for f in flags:
            print(f"    [!] {f}")

    print(f"\n{'-'*70}")
    print(" CROSS-CASE STATISTICS")
    print(f"{'-'*70}")

    primary_dist = defaultdict(int)
    for c in cases:
        primary_dist[c["summary"]["primary_issue"]] += 1
    print("\n  Primary issue distribution:")
    for issue, cnt in sorted(primary_dist.items(), key=lambda x: -x[1]):
        print(f"    {issue:<32} {cnt:>3}")

    print(f"\n{'-'*70}")
    print(" AGENT FLAG SUMMARY")
    print(f"{'-'*70}")
    agents_order = ["CUSTOMER", "ORDER_PRODUCT", "PAYMENT", "DELIVERY", "POLICY"]
    for agent in agents_order:
        cnt = agent_flag_counts.get(agent, 0)
        print(f"  {agent:<20} flags={cnt:>2}")

    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    analyze()
