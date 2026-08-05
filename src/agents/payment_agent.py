"""Payment Agent: reconciles payment rows against item + freight totals.

Access: order_payments.csv (read-only), plus the item list handed off by
the Order & Product Agent (does not re-read order_items.csv itself).
"""

from __future__ import annotations

from src.data_layer import OlistData
from src.utils import dedup_keep_order, r2


def investigate(data: OlistData, order_id: str, items: list[dict]) -> dict:
    payments = data.get_payments(order_id)
    payment_total = r2(sum(p["payment_value"] for p in payments)) if payments else 0.0
    payment_types = dedup_keep_order([p["payment_type"] for p in payments])

    if not items:
        return {
            "payments": payments,
            "item_total_brl": None,
            "freight_total_brl": None,
            "expected_total_brl": None,
            "payment_total_brl": payment_total,
            "difference_brl": None,
            "reconciled": None,
            "payment_types": payment_types,
            "split_payment": len(payments) >= 2,
        }

    item_total = r2(sum(it["price"] for it in items))
    freight_total = r2(sum(it["freight_value"] for it in items))
    expected_total = r2(item_total + freight_total)
    difference = r2(payment_total - expected_total)
    reconciled = abs(difference) <= 0.10

    return {
        "payments": payments,
        "item_total_brl": item_total,
        "freight_total_brl": freight_total,
        "expected_total_brl": expected_total,
        "payment_total_brl": payment_total,
        "difference_brl": difference,
        "reconciled": reconciled,
        "payment_types": payment_types,
        "split_payment": len(payments) >= 2,
    }
