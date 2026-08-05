"""Tool cua Delivery Agent. Bang duoc doc: orders (cot ngay), order_items.

Kiem chung cong thuc bang chinh vi du o README muc 6:
  delivered 2018-03-31 15:23:33 - estimated 2018-03-28 00:00:00
      = 3 ngay 15h23m33s = 87.3925 h -> 87.39   khop README
  carrier 2018-03-15 21:33:51 - shipping_limit 2018-03-15 20:31:15
      = 1h02m36s = 1.0433 h -> 1.04             khop README
"""

from __future__ import annotations

from datetime import datetime

from src.contracts import Fact
from src.loader import OrderBundle, _fmt_ts
from src.numeric import hours_between
from src.policy import limits


def get_delivery_timestamps(bundle: OrderBundle) -> list[Fact]:
    """Ba moc thoi gian va delivery variance.

    delivery_variance_hours = order_delivered_customer_date - order_estimated_delivery_date
      > 0  giao TRE hon cam ket
      <= 0 giao dung hoac som hon cam ket
      None thieu moc -> khong duoc suy dien la giao dung han

    14/50 case (canceled + unavailable) khong co order_delivered_customer_date.
    """
    src = [f"order:{bundle.order_id}"]
    order = bundle.order

    delivered_at: datetime | None = order.delivered_customer_at if order else None
    estimated_at: datetime | None = order.estimated_delivery_at if order else None
    carrier_at: datetime | None = order.delivered_carrier_at if order else None

    variance = hours_between(delivered_at, estimated_at)

    return [
        Fact("delivered_at", _fmt_ts(delivered_at), src),
        Fact("estimated_delivery_at", _fmt_ts(estimated_at), src),
        Fact("carrier_handoff_at", _fmt_ts(carrier_at), src),
        Fact("delivery_variance_hours", variance, src),
        # Dieu kien "giao sau estimated date" cua hai luat late_delivery_*.
        Fact("is_delivered_late", bool(variance is not None and variance > 0), src),
        Fact("has_delivery_timestamps", delivered_at is not None and estimated_at is not None, src),
    ]


def analyze_seller_handoff(bundle: OrderBundle) -> list[Fact]:
    """Handoff variance cho tung seller.

    handoff_variance_hours = order_delivered_carrier_date - shipping_limit_date SOM NHAT
                             cua rieng seller do

    Vi sao "som nhat cua tung seller": schema o README muc 6 dat shipping_limit_at
    BEN TRONG mang seller_handoff_analysis, moi phan tu mot seller. Mot seller co
    the co nhieu item voi shipping_limit khac nhau -> lay moc som nhat, tuc la han
    chot nghiem ngat nhat ma seller do phai dat.

    Khong co carrier date (13/14 case non-delivered) -> variance null, late_handoff
    false. Khong duoc coi seller la vi pham khi khong co bang chung ban giao.
    """
    src = [f"order:{bundle.order_id}"]
    order = bundle.order
    carrier_at: datetime | None = order.delivered_carrier_at if order else None

    # Han chot som nhat cua tung seller, giu thu tu xuat hien lan dau trong items.
    earliest_limit: dict[str, datetime | None] = {}
    for item in bundle.items:
        current = earliest_limit.get(item.seller_id, "unset")
        if current == "unset":
            earliest_limit[item.seller_id] = item.shipping_limit_at
        elif item.shipping_limit_at is not None and (
            current is None or item.shipping_limit_at < current
        ):
            earliest_limit[item.seller_id] = item.shipping_limit_at

    analysis: list[dict] = []
    late_seller_ids: list[str] = []
    for seller_id in bundle.seller_ids_in_order():
        limit_at = earliest_limit.get(seller_id)
        variance = hours_between(carrier_at, limit_at)
        late = bool(variance is not None and variance > 0)
        if late:
            late_seller_ids.append(seller_id)
        analysis.append(
            {
                "seller_id": seller_id,
                "shipping_limit_at": _fmt_ts(limit_at),
                "handoff_variance_hours": variance,
                "late_handoff": late,
            }
        )

    seller_sources = [f"seller:{sid}" for sid in bundle.seller_ids_in_order()]
    item_sources = [f"item:{item.item_key}" for item in bundle.items]

    return [
        Fact("seller_handoff_analysis", analysis, src + item_sources + seller_sources),
        Fact(
            "late_handoff_seller_ids",
            limits.cap(late_seller_ids, limits.MAX_SELLER_IDS),
            src + [f"seller:{sid}" for sid in late_seller_ids],
        ),
        # Dieu kien phan biet late_delivery_seller voi late_delivery_logistics.
        Fact("has_late_handoff_seller", len(late_seller_ids) > 0, src),
    ]


__all__ = ["get_delivery_timestamps", "analyze_seller_handoff"]
