"""Tool cua Customer Agent. Bang duoc doc: customers, orders."""

from __future__ import annotations

from src.contracts import Fact
from src.loader import OrderBundle
from src.policy import limits


def get_customer_identity(bundle: OrderBundle) -> list[Fact]:
    """Xac dinh khach hang dung sau order dang khieu nai.

    orders.customer_id la ID cua MOT don, khong phai cua nguoi mua.
    Muon nhan dien cung mot nguoi qua nhieu don phai dung customer_unique_id.
    """
    order_src = [f"order:{bundle.order_id}"]
    if not bundle.found or bundle.customer is None:
        return [
            Fact("customer_unique_id", None, order_src),
            Fact("customer_id", None, order_src),
        ]
    return [
        Fact("customer_unique_id", bundle.customer.customer_unique_id, order_src),
        Fact("customer_id", bundle.customer.customer_id, order_src),
    ]


def get_customer_order_history(bundle: OrderBundle) -> list[Fact]:
    """Cac order khac cua cung customer_unique_id.

    README muc 3: order lich su KHONG duoc dua vao affected_entities, chi xuat hien
    o customer_context.related_order_ids. Order dang khieu nai da bi loai tu loader.
    """
    order_src = [f"order:{bundle.order_id}"]
    related = list(bundle.related_order_ids)
    return [
        Fact(
            "related_order_ids",
            limits.cap(related, limits.MAX_RELATED_ORDER_IDS),
            order_src,
        ),
        Fact("related_order_count", len(related), order_src),
        # Secondary issue #4: repeat_customer.
        Fact("is_repeat_customer", len(related) > 0, order_src),
    ]


__all__ = ["get_customer_identity", "get_customer_order_history"]
