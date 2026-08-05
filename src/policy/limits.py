"""Tran do dai mang theo README muc 6.

Vuot tran la hard gate -> case 0 diem. Cat o day mot lan, dung cho ca tool,
assembler va verifier de khong co cho nao quen.
"""

from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")

MAX_ORDER_IDS = 5
MAX_ITEM_IDS = 5
MAX_SELLER_IDS = 3
MAX_PAYMENT_IDS = 5
MAX_RELATED_ORDER_IDS = 5
MAX_PRODUCT_IDS = 5
MAX_CATEGORY_NAMES = 5
MAX_ROOT_CAUSES = 3
MAX_RESPONSIBLE_PARTIES = 3
MAX_EVIDENCE_IDS = 20
MAX_RESOLUTION_ACTIONS = 5

# Ten field -> tran, dung cho Verifier duyet mot luot.
FIELD_LIMITS: dict[str, int] = {
    "affected_entities.order_ids": MAX_ORDER_IDS,
    "affected_entities.item_ids": MAX_ITEM_IDS,
    "affected_entities.seller_ids": MAX_SELLER_IDS,
    "affected_entities.payment_ids": MAX_PAYMENT_IDS,
    "customer_context.related_order_ids": MAX_RELATED_ORDER_IDS,
    "product_context.product_ids": MAX_PRODUCT_IDS,
    "product_context.category_names": MAX_CATEGORY_NAMES,
    "root_cause_analysis.ranked_causes": MAX_ROOT_CAUSES,
    "root_cause_analysis.responsible_parties": MAX_RESPONSIBLE_PARTIES,
    "evidence_ids": MAX_EVIDENCE_IDS,
    "resolution_actions": MAX_RESOLUTION_ACTIONS,
}


def cap(values: Sequence[T], limit: int) -> list[T]:
    """Cat con `limit` phan tu dau, giu nguyen thu tu nguon."""
    return list(values[:limit])


def dedup(values: Sequence[T]) -> list[T]:
    """Bo trung, giu thu tu xuat hien lan dau."""
    out: list[T] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def dedup_cap(values: Sequence[T], limit: int) -> list[T]:
    return cap(dedup(values), limit)


__all__ = [
    "MAX_ORDER_IDS",
    "MAX_ITEM_IDS",
    "MAX_SELLER_IDS",
    "MAX_PAYMENT_IDS",
    "MAX_RELATED_ORDER_IDS",
    "MAX_PRODUCT_IDS",
    "MAX_CATEGORY_NAMES",
    "MAX_ROOT_CAUSES",
    "MAX_RESPONSIBLE_PARTIES",
    "MAX_EVIDENCE_IDS",
    "MAX_RESOLUTION_ACTIONS",
    "FIELD_LIMITS",
    "cap",
    "dedup",
    "dedup_cap",
]
