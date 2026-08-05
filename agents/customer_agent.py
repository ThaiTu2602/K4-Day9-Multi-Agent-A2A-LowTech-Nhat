"""
Agent 2 — CustomerAgent
Nhiệm vụ: Xác định customer_unique_id và lịch sử order của khách.
Input:    order_id (claimed)
Output:   customer_context dict
MODEL: rule-based (0B parameters)
"""
from __future__ import annotations
from core.data_loader import DataStore


class CustomerAgent:
    name = "customer_agent"

    def __init__(self, store: DataStore):
        self.store = store

    def run(self, order_id: str) -> dict:
        """
        Trả về:
        {
            "customer_unique_id": str | None,
            "related_order_ids": list[str]   # tối đa 5, không kể order đang xét
        }
        """
        order = self.store.get_order(order_id)
        if order is None:
            return {
                "customer_unique_id": None,
                "related_order_ids": [],
                "_trace": {"status": "order_not_found"},
            }

        customer_id = order.get("customer_id")
        if not customer_id or customer_id != customer_id:  # NaN guard
            return {
                "customer_unique_id": None,
                "related_order_ids": [],
                "_trace": {"status": "customer_id_missing"},
            }

        unique_id = self.store.get_customer_unique_id(str(customer_id))
        if unique_id is None:
            return {
                "customer_unique_id": None,
                "related_order_ids": [],
                "_trace": {"status": "unique_id_not_found"},
            }

        related = self.store.get_related_order_ids(unique_id, order_id)

        return {
            "customer_unique_id": unique_id,
            "related_order_ids": related,
            "_trace": {
                "status": "ok",
                "customer_id": customer_id,
                "num_related_orders": len(related),
            },
        }
