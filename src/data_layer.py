"""Loads the 9 Olist CSV files and exposes indexed, dict-based lookups.

All IDs are kept as plain strings (dtype=str) so joins never suffer from
pandas' float/int coercion on things that look numeric but are opaque hashes.
Timestamps are parsed to pandas.Timestamp for arithmetic but the original
CSV string format is preserved via `fmt_ts` for output.
"""

from __future__ import annotations

import os
from collections import defaultdict

import pandas as pd

TS_FORMAT = "%Y-%m-%d %H:%M:%S"

_ORDER_TS_COLS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


def fmt_ts(value) -> str | None:
    """Format a parsed timestamp back to the CSV's 'YYYY-MM-DD HH:MM:SS' string, or None."""
    if value is None or pd.isna(value):
        return None
    return value.strftime(TS_FORMAT)


class OlistData:
    def __init__(self, data_dir: str):
        def read(name, **kwargs):
            return pd.read_csv(os.path.join(data_dir, name), dtype=str, keep_default_na=True, **kwargs)

        orders = read("olist_orders_dataset.csv")
        for col in _ORDER_TS_COLS:
            orders[col] = pd.to_datetime(orders[col], errors="coerce")
        self._orders = orders.set_index("order_id", drop=False).to_dict(orient="index")

        customers = read("olist_customers_dataset.csv")
        self._customers = customers.set_index("customer_id", drop=False).to_dict(orient="index")

        self._orders_by_customer_id: dict[str, str] = {}
        for order_id, row in self._orders.items():
            self._orders_by_customer_id[row["customer_id"]] = order_id

        self._customer_ids_by_unique_id: dict[str, list[str]] = defaultdict(list)
        for cust_id, row in self._customers.items():
            self._customer_ids_by_unique_id[row["customer_unique_id"]].append(cust_id)

        items = read("olist_order_items_dataset.csv")
        items["shipping_limit_date"] = pd.to_datetime(items["shipping_limit_date"], errors="coerce")
        items["price"] = items["price"].astype(float)
        items["freight_value"] = items["freight_value"].astype(float)
        items = items.sort_values(["order_id", "order_item_id"], key=lambda s: s if s.name != "order_item_id" else s.astype(int))
        self._items_by_order: dict[str, list[dict]] = defaultdict(list)
        for row in items.to_dict(orient="records"):
            self._items_by_order[row["order_id"]].append(row)

        payments = read("olist_order_payments_dataset.csv")
        payments["payment_value"] = payments["payment_value"].astype(float)
        payments["payment_sequential"] = payments["payment_sequential"].astype(int)
        payments = payments.sort_values(["order_id", "payment_sequential"])
        self._payments_by_order: dict[str, list[dict]] = defaultdict(list)
        for row in payments.to_dict(orient="records"):
            self._payments_by_order[row["order_id"]].append(row)

        sellers = read("olist_sellers_dataset.csv")
        self._sellers = sellers.set_index("seller_id", drop=False).to_dict(orient="index")

        products = read("olist_products_dataset.csv")
        self._products = products.set_index("product_id", drop=False).to_dict(orient="index")

        cat = read("product_category_name_translation.csv")
        cat.columns = [c.strip().lstrip("﻿") for c in cat.columns]
        self._category_en = dict(zip(cat["product_category_name"], cat["product_category_name_english"]))

    # -- lookups -------------------------------------------------------

    def get_order(self, order_id: str) -> dict | None:
        return self._orders.get(order_id)

    def get_customer(self, customer_id: str) -> dict | None:
        return self._customers.get(customer_id)

    def get_items(self, order_id: str) -> list[dict]:
        return self._items_by_order.get(order_id, [])

    def get_payments(self, order_id: str) -> list[dict]:
        return self._payments_by_order.get(order_id, [])

    def get_seller(self, seller_id: str) -> dict | None:
        return self._sellers.get(seller_id)

    def get_product(self, product_id: str) -> dict | None:
        return self._products.get(product_id)

    def get_category_english(self, category_name: str | None) -> str | None:
        if not category_name or pd.isna(category_name):
            return None
        return self._category_en.get(category_name, category_name)

    def get_related_order_ids(self, customer_unique_id: str, exclude_order_id: str) -> list[str]:
        related = []
        for cust_id in self._customer_ids_by_unique_id.get(customer_unique_id, []):
            order_id = self._orders_by_customer_id.get(cust_id)
            if order_id and order_id != exclude_order_id:
                related.append(order_id)
        related.sort(key=lambda oid: (self._orders[oid]["order_purchase_timestamp"] is pd.NaT, self._orders[oid]["order_purchase_timestamp"]))
        return related
