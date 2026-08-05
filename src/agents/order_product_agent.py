"""Order & Product Agent: resolves items, sellers, products and categories
for the claimed order.

Access: order_items.csv, sellers.csv, products.csv,
product_category_name_translation.csv (read-only, via OlistData).
"""

from __future__ import annotations

from src.data_layer import OlistData
from src.utils import dedup_keep_order


def investigate(data: OlistData, order_id: str) -> dict:
    items = data.get_items(order_id)

    seller_ids = dedup_keep_order([it["seller_id"] for it in items])
    sellers = [data.get_seller(sid) for sid in seller_ids]
    sellers = [s for s in sellers if s is not None]

    product_ids = dedup_keep_order([it["product_id"] for it in items])
    products = [data.get_product(pid) for pid in product_ids]

    category_names = dedup_keep_order(
        [p.get("product_category_name") for p in products if p and p.get("product_category_name")]
    )

    return {
        "items": items,
        "seller_ids": seller_ids,
        "sellers": sellers,
        "product_ids": product_ids,
        "category_names": category_names,
        "multi_item_order": len(items) >= 2,
        "multi_seller_order": len(seller_ids) >= 2,
        "multiple_categories": len(category_names) >= 2,
    }
