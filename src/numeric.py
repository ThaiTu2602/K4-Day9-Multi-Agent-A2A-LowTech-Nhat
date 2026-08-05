"""Lam tron tien va gio. Tach rieng vi day la cho de mat diem nhat.

Hai cai bay trong Python:

1. round() la banker's rounding, khong phai lam tron nua len.
       round(2.675, 2) -> 2.67      (mong doi 2.68)
       round(0.125, 2) -> 0.12      (mong doi 0.13)
   README noi "lam tron 2 chu so thap phan" theo nghia thong thuong -> ROUND_HALF_UP.

2. Cong float sinh sai so tich luy.
       194.00 + 18.27 -> 212.27000000000001
   Cong bang Decimal thi chinh xac tuyet doi vi CSV luu so thap phan he 10.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from src import config

_MONEY_Q = Decimal(1).scaleb(-config.MONEY_DECIMALS)   # Decimal("0.01")
_HOURS_Q = Decimal(1).scaleb(-config.HOURS_DECIMALS)   # Decimal("0.01")

RECONCILE_TOLERANCE = Decimal(config.RECONCILE_TOLERANCE_BRL)


def dsum(values: Iterable[Decimal]) -> Decimal:
    """Tong Decimal. Tong rong = Decimal('0') chu khong phai int 0."""
    total = Decimal("0")
    for value in values:
        total += value
    return total


def money(value: Decimal | None) -> float | None:
    """Decimal -> float da lam tron 2 chu so, ROUND_HALF_UP. None giu nguyen None."""
    if value is None:
        return None
    return float(value.quantize(_MONEY_Q, rounding=ROUND_HALF_UP))


def hours_between(later, earlier) -> float | None:
    """(later - earlier) tinh bang gio, lam tron 2 chu so ROUND_HALF_UP.

    Tra None neu thieu mot trong hai moc thoi gian (README: giu null, khong doan).

    Timestamp trong Olist khong co microsecond nen total_seconds() luon la so nguyen
    -> chuyen sang Decimal khong mat do chinh xac truoc khi chia 3600.
    """
    if later is None or earlier is None:
        return None
    seconds = int((later - earlier).total_seconds())
    delta_hours = Decimal(seconds) / Decimal(3600)
    return float(delta_hours.quantize(_HOURS_Q, rounding=ROUND_HALF_UP))


def is_reconciled(difference: Decimal | None) -> bool | None:
    """abs(difference_brl) <= 0.10 BRL. None neu order khong co item row."""
    if difference is None:
        return None
    return abs(difference) <= RECONCILE_TOLERANCE


__all__ = ["dsum", "money", "hours_between", "is_reconciled", "RECONCILE_TOLERANCE"]
