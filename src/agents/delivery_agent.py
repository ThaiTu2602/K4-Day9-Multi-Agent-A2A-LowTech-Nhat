"""Delivery Agent: computes delivery variance and per-seller handoff variance.

Access: orders.csv timestamps (read-only) plus the item list handed off by
the Order & Product Agent (for each item's seller_id + shipping_limit_date).
"""

from __future__ import annotations

from collections import defaultdict

from src.data_layer import OlistData, fmt_ts
from src.utils import dedup_keep_order, hours_between


def investigate(data: OlistData, order: dict, items: list[dict]) -> dict:
    delivered_at = order["order_delivered_customer_date"]
    estimated_at = order["order_estimated_delivery_date"]
    carrier_handoff_at = order["order_delivered_carrier_date"]

    delivery_variance_hours = hours_between(delivered_at, estimated_at)
    is_late = delivery_variance_hours is not None and delivery_variance_hours > 0

    seller_handoff_analysis = []
    late_handoff_seller_ids = []

    if items:
        earliest_limit_by_seller: dict[str, object] = {}
        for it in items:
            sid = it["seller_id"]
            limit = it["shipping_limit_date"]
            if sid not in earliest_limit_by_seller or (
                limit is not None and (earliest_limit_by_seller[sid] is None or limit < earliest_limit_by_seller[sid])
            ):
                earliest_limit_by_seller[sid] = limit

        seller_order = dedup_keep_order([it["seller_id"] for it in items])
        for sid in seller_order:
            shipping_limit_at = earliest_limit_by_seller[sid]
            handoff_variance_hours = hours_between(carrier_handoff_at, shipping_limit_at)
            late_handoff = handoff_variance_hours is not None and handoff_variance_hours > 0
            seller_handoff_analysis.append(
                {
                    "seller_id": sid,
                    "shipping_limit_at": fmt_ts(shipping_limit_at),
                    "handoff_variance_hours": handoff_variance_hours,
                    "late_handoff": late_handoff,
                }
            )
            if late_handoff:
                late_handoff_seller_ids.append(sid)

    return {
        "delivered_at": fmt_ts(delivered_at),
        "estimated_delivery_at": fmt_ts(estimated_at),
        "carrier_handoff_at": fmt_ts(carrier_handoff_at),
        "delivery_variance_hours": delivery_variance_hours,
        "is_late": is_late,
        "seller_handoff_analysis": seller_handoff_analysis,
        "late_handoff_seller_ids": late_handoff_seller_ids,
    }
