"""
Agent 4 — PaymentAgent
Nhiệm vụ: Tổng hợp payment rows và đối soát với item + freight.
Công thức:
    expected_total_brl = sum(price) + sum(freight_value)
    difference_brl     = sum(payment_value) - expected_total_brl
    reconciled         = abs(difference_brl) <= 0.10
Input:    order_id
Output:   payment_reconciliation dict + raw values (dùng cho Policy Agent)
MODEL: rule-based (0B parameters)
"""
from __future__ import annotations
import pandas as pd
from core.data_loader import DataStore


def _fmt(val) -> float | None:
    """Round về 2 decimal, trả None nếu NaN."""
    if val is None or (isinstance(val, float) and val != val):
        return None
    return round(float(val), 2)


class PaymentAgent:
    name = "payment_agent"

    def __init__(self, store: DataStore):
        self.store = store

    def run(self, order_id: str) -> dict:
        """
        Trả về:
        {
            "payment_reconciliation": { ... },
            "_payment_total": float,   # dùng bởi PolicyAgent
            "_num_payments": int,
            "_reconciled": bool | None,
        }
        """
        items: pd.DataFrame = self.store.get_items(order_id)
        payments: pd.DataFrame = self.store.get_payments(order_id)

        # ── Payment totals ────────────────────────────────────────────────────
        if payments.empty:
            payment_total = 0.0
            payment_types: list[str] = []
        else:
            payment_total = _fmt(payments["payment_value"].sum())
            payment_types = list(
                dict.fromkeys(payments["payment_type"].astype(str).tolist())
            )

        num_payments = len(payments)

        # ── Item/freight totals (null khi không có item) ───────────────────
        if items.empty:
            item_total = 0.0
            freight_total = 0.0
            expected_total = None
            difference = None
            reconciled = None
        else:
            item_total = _fmt(items["price"].sum())
            freight_total = _fmt(items["freight_value"].sum())
            expected_total = _fmt(item_total + freight_total)
            difference = _fmt(payment_total - expected_total)
            reconciled = bool(abs(difference) <= 0.10)

        return {
            "payment_reconciliation": {
                "currency": "BRL",
                "item_total_brl": item_total,
                "freight_total_brl": freight_total,
                "expected_total_brl": expected_total,
                "payment_total_brl": payment_total,
                "difference_brl": difference,
                "reconciled": reconciled,
                "payment_types": payment_types,
            },
            # ── Internal values cho PolicyAgent ───────────────────────────
            "_payment_total": payment_total,
            "_num_payments": num_payments,
            "_reconciled": reconciled,
            "_freight_total": freight_total,
            "_trace": {
                "status": "ok",
                "num_payments": num_payments,
                "payment_total": payment_total,
                "reconciled": reconciled,
            },
        }
