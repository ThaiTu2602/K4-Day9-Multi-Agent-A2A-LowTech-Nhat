"""Customer Agent: resolves customer identity and cross-order history.

Access: customers.csv, orders.csv (read-only, via OlistData). Does not
touch payment/delivery/product data — that is other agents' domain.
"""

from __future__ import annotations

from src.data_layer import OlistData


def investigate(data: OlistData, order: dict) -> dict:
    customer = data.get_customer(order["customer_id"])
    customer_unique_id = customer["customer_unique_id"] if customer else None

    related_order_ids: list[str] = []
    if customer_unique_id:
        related_order_ids = data.get_related_order_ids(customer_unique_id, exclude_order_id=order["order_id"])

    return {
        "customer_unique_id": customer_unique_id,
        "related_order_ids": related_order_ids,
        "repeat_customer": len(related_order_ids) > 0,
    }
