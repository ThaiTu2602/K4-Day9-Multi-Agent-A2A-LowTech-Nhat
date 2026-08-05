"""Tool cua Order & Product Agent.

Bang duoc doc: orders, order_items, products, sellers, category_translation.
"""

from __future__ import annotations

from src.contracts import Fact
from src.loader import OrderBundle
from src.policy import limits


def get_order_header(bundle: OrderBundle) -> list[Fact]:
    """Trang thai don. Quyet dinh hai luat uu tien cao nhat cua EC_POLICY_V2."""
    src = [f"order:{bundle.order_id}"]
    if not bundle.found or bundle.order is None:
        return [
            Fact("order_found", False, src),
            Fact("order_status", None, src),
        ]
    return [
        Fact("order_found", True, src),
        Fact("order_status", bundle.order.order_status, src),
        Fact("order_ids", [bundle.order_id], src),
    ]


def get_order_items(bundle: OrderBundle) -> list[Fact]:
    """Item, seller va cac dau hieu secondary issue #1, #2.

    README muc 4: order khong co item row thi item/seller/product/category va
    seller handoff deu la mang rong. Khong duoc suy dien item khong ton tai.
    """
    src = [f"order:{bundle.order_id}"]
    item_ids = [item.item_key for item in bundle.items]
    seller_ids = bundle.seller_ids_in_order()

    item_sources = [f"item:{key}" for key in item_ids]
    seller_sources = [f"seller:{sid}" for sid in seller_ids]

    return [
        Fact("item_count", len(bundle.items), src),
        Fact("item_ids", limits.cap(item_ids, limits.MAX_ITEM_IDS), src + item_sources),
        Fact("seller_count", len(seller_ids), src),
        Fact(
            "seller_ids",
            limits.cap(seller_ids, limits.MAX_SELLER_IDS),
            src + seller_sources,
        ),
        # Secondary issue #1 va #2.
        Fact("is_multi_item_order", len(bundle.items) >= 2, src),
        Fact("is_multi_seller_order", len(seller_ids) >= 2, src),
    ]


def get_product_context(bundle: OrderBundle) -> list[Fact]:
    """Product va category.

    21/50 case co nhieu item tro ve cung mot product_id -> bat buoc dedup,
    neu khong `product_ids` se bi lap va sai o o cham 'Customer va product context'.
    """
    src = [f"order:{bundle.order_id}"]
    product_ids = bundle.product_ids_in_order()
    category_names = bundle.category_names_in_order()
    item_sources = [f"item:{item.item_key}" for item in bundle.items]

    return [
        Fact(
            "product_ids",
            limits.cap(product_ids, limits.MAX_PRODUCT_IDS),
            src + item_sources,
        ),
        Fact(
            "category_names",
            limits.cap(category_names, limits.MAX_CATEGORY_NAMES),
            src + item_sources,
        ),
        Fact("distinct_category_count", len(category_names), src),
        # Secondary issue #5.
        Fact("has_multiple_categories", len(category_names) >= 2, src),
    ]


__all__ = ["get_order_header", "get_order_items", "get_product_context"]
