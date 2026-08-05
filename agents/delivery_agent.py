"""
Agent 5 — DeliveryAgent
Nhiệm vụ: Tính delivery variance và seller handoff variance.
Công thức (README §4):
    delivery_variance_hours  = order_delivered_customer_date - order_estimated_delivery_date
    handoff_variance_hours   = order_delivered_carrier_date  - min(shipping_limit_date) of seller
Input:    order_id, seller_ids_all (từ OrderProductAgent)
Output:   delivery_analysis dict + flags cho PolicyAgent
MODEL: rule-based (0B parameters)
"""
from __future__ import annotations
import pandas as pd
from core.data_loader import DataStore

TS_FMT = "%Y-%m-%d %H:%M:%S"


def _ts(val) -> str | None:
    """Chuyển Timestamp/NaT → string hoặc None."""
    if val is None or (hasattr(val, "isnull") and val.isnull()):
        return None
    if isinstance(val, str):
        return val
    try:
        if pd.isna(val):
            return None
        return val.strftime(TS_FMT)
    except Exception:
        return None


def _hours(delta) -> float | None:
    """Timedelta → hours, rounded 2dp."""
    try:
        if pd.isna(delta):
            return None
        return round(delta.total_seconds() / 3600, 2)
    except Exception:
        return None


class DeliveryAgent:
    name = "delivery_agent"

    def __init__(self, store: DataStore):
        self.store = store

    def run(self, order_id: str) -> dict:
        """
        Trả về:
        {
            "delivery_analysis": { ... },
            "_is_late_delivery": bool,
            "_late_handoff_seller_ids": list[str],
        }
        """
        order = self.store.get_order(order_id)
        items: pd.DataFrame = self.store.get_items(order_id)

        # ── Timestamps từ orders ─────────────────────────────────────────────
        if order is None:
            return {
                "delivery_analysis": {
                    "delivered_at": None,
                    "estimated_delivery_at": None,
                    "carrier_handoff_at": None,
                    "delivery_variance_hours": None,
                    "seller_handoff_analysis": [],
                    "late_handoff_seller_ids": [],
                },
                "_is_late_delivery": False,
                "_late_handoff_seller_ids": [],
                "_trace": {"status": "order_not_found"},
            }

        delivered_at_raw = order.get("order_delivered_customer_date")
        estimated_at_raw = order.get("order_estimated_delivery_date")
        carrier_at_raw = order.get("order_delivered_carrier_date")

        delivered_at = delivered_at_raw if not _is_nat(delivered_at_raw) else None
        estimated_at = estimated_at_raw if not _is_nat(estimated_at_raw) else None
        carrier_at = carrier_at_raw if not _is_nat(carrier_at_raw) else None

        # ── Delivery variance ────────────────────────────────────────────────
        if delivered_at is not None and estimated_at is not None:
            delivery_variance_hours = _hours(delivered_at - estimated_at)
        else:
            delivery_variance_hours = None

        is_late_delivery = (
            delivery_variance_hours is not None and delivery_variance_hours > 0
        )

        # ── Seller handoff analysis ──────────────────────────────────────────
        seller_handoff_analysis: list[dict] = []
        late_handoff_seller_ids: list[str] = []

        if not items.empty:
            # Nhóm theo seller_id, lấy earliest shipping_limit_date
            for seller_id, grp in items.groupby("seller_id", sort=False):
                limit_raw = grp["shipping_limit_date"].min()
                limit = limit_raw if not _is_nat(limit_raw) else None

                if limit is not None and carrier_at is not None:
                    hv = _hours(carrier_at - limit)
                    is_late = hv is not None and hv > 0
                else:
                    hv = None
                    is_late = False

                seller_handoff_analysis.append(
                    {
                        "seller_id": str(seller_id),
                        "shipping_limit_at": _ts(limit),
                        "handoff_variance_hours": hv,
                        "late_handoff": is_late,
                    }
                )
                if is_late:
                    late_handoff_seller_ids.append(str(seller_id))

        return {
            "delivery_analysis": {
                "delivered_at": _ts(delivered_at),
                "estimated_delivery_at": _ts(estimated_at),
                "carrier_handoff_at": _ts(carrier_at),
                "delivery_variance_hours": delivery_variance_hours,
                "seller_handoff_analysis": seller_handoff_analysis,
                "late_handoff_seller_ids": late_handoff_seller_ids,
            },
            "_is_late_delivery": is_late_delivery,
            "_late_handoff_seller_ids": late_handoff_seller_ids,
            "_trace": {
                "status": "ok",
                "delivery_variance_hours": delivery_variance_hours,
                "late_handoff_sellers": late_handoff_seller_ids,
            },
        }


def _is_nat(val) -> bool:
    """Kiểm tra NaT hoặc None."""
    if val is None:
        return True
    try:
        return bool(pd.isna(val))
    except Exception:
        return False
