"""Tool cua Payment Agent. Bang duoc doc: order_payments, order_items."""

from __future__ import annotations

from decimal import Decimal

from src import config
from src.contracts import Fact
from src.loader import OrderBundle
from src.numeric import dsum, is_reconciled, money
from src.policy import limits


def get_payment_rows(bundle: OrderBundle) -> list[Fact]:
    """Danh sach payment row.

    README muc 2: payment_value la so tien cua TUNG payment row, khong phai gia tri
    cua tung installment -> cong thang cac row, khong nhan voi payment_installments.
    """
    src = [f"order:{bundle.order_id}"]
    payment_ids = [p.payment_key for p in bundle.payments]
    payment_sources = [f"payment:{key}" for key in payment_ids]
    payment_types = limits.dedup([p.payment_type for p in bundle.payments])

    return [
        Fact("payment_count", len(bundle.payments), src),
        Fact(
            "payment_ids",
            limits.cap(payment_ids, limits.MAX_PAYMENT_IDS),
            src + payment_sources,
        ),
        Fact("payment_types", payment_types, src + payment_sources),
        Fact(
            "payment_total_brl",
            money(dsum(p.payment_value for p in bundle.payments)),
            src + payment_sources,
        ),
        # Secondary issue #3.
        Fact("is_split_payment", len(bundle.payments) >= 2, src),
    ]


def reconcile_payments(bundle: OrderBundle) -> list[Fact]:
    """Doi soat payment voi item + freight theo cong thuc README muc 4.

        expected_total_brl = sum(price) + sum(freight_value)
        difference_brl     = sum(payment_value) - expected_total_brl
        reconciled         = abs(difference_brl) <= 0.10

    Order khong co item row: expected / difference / reconciled = null.
    Luu y item_total_brl va freight_total_brl KHONG nam trong danh sach phai null
    cua README -> giu 0.0 (tong cua tap rong).
    """
    src = [f"order:{bundle.order_id}"]
    item_sources = [f"item:{item.item_key}" for item in bundle.items]
    payment_sources = [f"payment:{p.payment_key}" for p in bundle.payments]

    item_total = dsum(item.price for item in bundle.items)
    freight_total = dsum(item.freight_value for item in bundle.items)
    payment_total = dsum(p.payment_value for p in bundle.payments)

    if bundle.has_items:
        expected_total: Decimal | None = item_total + freight_total
        difference: Decimal | None = payment_total - expected_total
    else:
        expected_total = None
        difference = None

    return [
        Fact("currency", config.CURRENCY, src),
        Fact("item_total_brl", money(item_total), src + item_sources),
        Fact("freight_total_brl", money(freight_total), src + item_sources),
        Fact("expected_total_brl", money(expected_total), src + item_sources),
        Fact("payment_total_brl", money(payment_total), src + payment_sources),
        Fact("difference_brl", money(difference), src + item_sources + payment_sources),
        Fact("reconciled", is_reconciled(difference), src),
    ]


__all__ = ["get_payment_rows", "reconcile_payments"]
