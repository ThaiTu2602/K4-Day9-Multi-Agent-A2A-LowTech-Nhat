from __future__ import annotations

import pandas as pd


def r2(x: float | None) -> float | None:
    """Round to 2 decimals, per README ('mọi phép tính tiền và số giờ được làm tròn 2 chữ số')."""
    if x is None or pd.isna(x):
        return None
    rounded = round(float(x), 2)
    return 0.0 if rounded == 0 else rounded


def hours_between(later, earlier) -> float | None:
    if later is None or earlier is None or pd.isna(later) or pd.isna(earlier):
        return None
    delta = later - earlier
    return r2(delta.total_seconds() / 3600.0)


def dedup_keep_order(items: list) -> list:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
