"""
Agent 3 — OrderProductAgent
Nhiệm vụ: Trích xuất thông tin order items, sellers, products và category.
Input:    order_id
Output:   affected_entities, product_context, raw counts (dùng cho Policy Agent)
MODEL: rule-based (0B parameters)
"""
from __future__ import annotations
import pandas as pd
from core.data_loader import DataStore


class OrderProductAgent:
    name = "order_product_agent"

    def __init__(self, store: DataStore):
        self.store = store

    def run(self, order_id: str) -> dict:
        """
        Trả về:
        {
            "affected_entities": {
                "order_ids": list[str],     # luôn là [order_id]
                "item_ids":   list[str],    # format "<order_id>:<item_id>", tối đa 5
                "seller_ids": list[str],    # tối đa 3
                "payment_ids": list[str],   # format "<order_id>:<seq>", tối đa 5
            },
            "product_context": {
                "product_ids":    list[str],  # tối đa 5
                "category_names": list[str],  # tối đa 5, đã dịch sang EN
            },
            "_counts": {
                "num_items":    int,   # tổng item rows thực (dùng cho Policy)
                "num_sellers":  int,   # số seller khác nhau
                "num_categories": int, # số category khác nhau
            }
        }
        """
        items: pd.DataFrame = self.store.get_items(order_id)
        payments: pd.DataFrame = self.store.get_payments(order_id)

        # ── Nếu không có item ───────────────────────────────────────────────
        if items.empty:
            payment_ids = [
                f"{order_id}:{int(row.payment_sequential)}"
                for _, row in payments.iterrows()
            ][:5]
            return {
                "affected_entities": {
                    "order_ids": [order_id],
                    "item_ids": [],
                    "seller_ids": [],
                    "payment_ids": payment_ids,
                },
                "product_context": {"product_ids": [], "category_names": []},
                "_counts": {"num_items": 0, "num_sellers": 0, "num_categories": 0},
                "_trace": {"status": "no_items"},
            }

        # ── Item IDs ─────────────────────────────────────────────────────────
        item_ids = [
            f"{order_id}:{int(row.order_item_id)}" for _, row in items.iterrows()
        ][:5]

        # ── Seller IDs ───────────────────────────────────────────────────────
        seller_ids_all: list[str] = list(
            dict.fromkeys(items["seller_id"].astype(str).tolist())
        )  # dedup giữ thứ tự
        seller_ids = seller_ids_all[:3]

        # ── Payment IDs ──────────────────────────────────────────────────────
        payment_ids = [
            f"{order_id}:{int(row.payment_sequential)}"
            for _, row in payments.iterrows()
        ][:5]

        # ── Products & Categories ────────────────────────────────────────────
        product_ids_all: list[str] = list(
            dict.fromkeys(items["product_id"].astype(str).tolist())
        )
        product_ids = product_ids_all[:5]

        category_names_raw: list[str] = []
        seen_cats: set[str] = set()
        for pid in product_ids_all:
            product = self.store.get_product(pid)
            if product is None:
                continue
            cat_pt = product.get("product_category_name")
            if pd.isna(cat_pt) or cat_pt in seen_cats:
                continue
            seen_cats.add(cat_pt)
            category_names_raw.append(self.store.translate_category(str(cat_pt)))

        category_names = category_names_raw[:5]

        return {
            "affected_entities": {
                "order_ids": [order_id],
                "item_ids": item_ids,
                "seller_ids": seller_ids,
                "payment_ids": payment_ids,
            },
            "product_context": {
                "product_ids": product_ids,
                "category_names": category_names,
            },
            "_counts": {
                "num_items": len(items),
                "num_sellers": items["seller_id"].nunique(),
                "num_categories": len(seen_cats),
            },
            "_seller_ids_all": seller_ids_all,  # dùng cho DeliveryAgent
            "_trace": {
                "status": "ok",
                "num_items": len(items),
                "num_sellers": items["seller_id"].nunique(),
            },
        }
