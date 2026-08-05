"""Data pipeline: doc 9 CSV Olist -> index trong RAM -> OrderBundle cho tung case.

Ba quyet dinh ky thuat quan trong cua tang nay:

1. TIEN TINH BANG Decimal, KHONG DUNG float.
   sum([Decimal("194.00"), Decimal("18.27")]) = Decimal("212.27") chinh xac tuyet doi.
   Neu dung float se ra 212.26999999999998 va lam `difference_brl` lech khoi 0.0.
   Lam tron dung ROUND_HALF_UP, khong dung round() cua Python (round() la banker's
   rounding: round(2.675, 2) == 2.67, sai so voi ky vong nghiep vu).

2. THU TU MANG BAM THEO NGUON.
   README muc 6: "Cac array phai giu thu tu on dinh theo du lieu nguon".
   - items sap theo order_item_id tang dan
   - payments sap theo payment_sequential tang dan
   - related_order_ids theo dung thu tu dong xuat hien trong olist_orders_dataset.csv
   - seller/product/category theo thu tu xuat hien lan dau trong danh sach item

3. CHI NAP BANG THUC SU CAN.
   olist_geolocation_dataset.csv (61 MB) va olist_order_reviews_dataset.csv khong
   co truong nao trong output schema nen khong nap -> tiet kiem ~75 MB va vai giay
   khoi dong. Neu sau nay can, them vao _TABLES la du.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from src import config

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

_FILES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}


# ---------------------------------------------------------------------------
# Row types
# ---------------------------------------------------------------------------


def _parse_ts(raw: str | None) -> datetime | None:
    """CSV -> datetime. Chuoi rong / khoang trang -> None (README: giu nguyen null)."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    return datetime.strptime(raw, TIMESTAMP_FORMAT)


def _fmt_ts(value: datetime | None) -> str | None:
    """datetime -> chuoi dung dinh dang CSV goc, hoac None."""
    return value.strftime(TIMESTAMP_FORMAT) if value else None


@dataclass(frozen=True)
class OrderRow:
    order_id: str
    customer_id: str
    order_status: str
    purchase_at: datetime | None
    approved_at: datetime | None
    delivered_carrier_at: datetime | None
    delivered_customer_at: datetime | None
    estimated_delivery_at: datetime | None


@dataclass(frozen=True)
class ItemRow:
    order_id: str
    order_item_id: int
    product_id: str
    seller_id: str
    shipping_limit_at: datetime | None
    price: Decimal
    freight_value: Decimal

    @property
    def item_key(self) -> str:
        """Dinh dang ID item theo README muc 5: <order_id>:<order_item_id>."""
        return f"{self.order_id}:{self.order_item_id}"


@dataclass(frozen=True)
class PaymentRow:
    order_id: str
    payment_sequential: int
    payment_type: str
    payment_installments: int
    payment_value: Decimal

    @property
    def payment_key(self) -> str:
        """Dinh dang ID payment theo README muc 5: <order_id>:<payment_sequential>."""
        return f"{self.order_id}:{self.payment_sequential}"


@dataclass(frozen=True)
class CustomerRow:
    customer_id: str
    customer_unique_id: str
    zip_prefix: str
    city: str
    state: str


@dataclass(frozen=True)
class ProductRow:
    product_id: str
    category_name: str | None


@dataclass(frozen=True)
class SellerRow:
    seller_id: str
    zip_prefix: str
    city: str
    state: str


# ---------------------------------------------------------------------------
# Bundle: toan bo du lieu lien quan toi mot order
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderBundle:
    """Anh chup bat bien cua mot order va moi thu noi vao no.

    Day la don vi du lieu duy nhat ma tang tool duoc phep doc. Agent khong bao gio
    cham truc tiep vao CSV.
    """

    order_id: str
    found: bool
    order: OrderRow | None
    items: tuple[ItemRow, ...]
    payments: tuple[PaymentRow, ...]
    customer: CustomerRow | None
    products: dict[str, ProductRow]
    sellers: dict[str, SellerRow]
    related_order_ids: tuple[str, ...]

    @property
    def has_items(self) -> bool:
        return len(self.items) > 0

    def seller_ids_in_order(self) -> list[str]:
        """Seller khac nhau, theo thu tu xuat hien lan dau trong danh sach item."""
        out: list[str] = []
        for item in self.items:
            if item.seller_id not in out:
                out.append(item.seller_id)
        return out

    def product_ids_in_order(self) -> list[str]:
        """Product khac nhau (21/50 case co item trung product -> bat buoc dedup)."""
        out: list[str] = []
        for item in self.items:
            if item.product_id not in out:
                out.append(item.product_id)
        return out

    def category_names_in_order(self) -> list[str]:
        """Category khac nhau, theo thu tu xuat hien lan dau. Bo qua category rong."""
        out: list[str] = []
        for pid in self.product_ids_in_order():
            product = self.products.get(pid)
            if product is None or not product.category_name:
                continue
            name = product.category_name
            if name not in out:
                out.append(name)
        return out


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class OlistStore:
    """Doc CSV mot lan, dung index, phuc vu tra cuu O(1) cho ca 50 case."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir or config.DATA_DIR)

        self.orders: dict[str, OrderRow] = {}
        self.items_by_order: dict[str, list[ItemRow]] = {}
        self.payments_by_order: dict[str, list[PaymentRow]] = {}
        self.customers: dict[str, CustomerRow] = {}
        self.products: dict[str, ProductRow] = {}
        self.sellers: dict[str, SellerRow] = {}
        self.category_pt_to_en: dict[str, str] = {}
        # customer_unique_id -> danh sach order_id theo dung thu tu dong trong CSV orders
        self.orders_by_customer_unique: dict[str, list[str]] = {}

        self._load()

    # -- doc file ----------------------------------------------------------

    def _rows(self, table: str):
        path = self.data_dir / _FILES[table]
        if not path.exists():
            raise FileNotFoundError(f"Thieu file du lieu: {path}")
        # utf-8-sig: product_category_name_translation.csv co BOM o dau file.
        with path.open(newline="", encoding="utf-8-sig") as handle:
            yield from csv.DictReader(handle)

    def _load(self) -> None:
        for row in self._rows("customers"):
            self.customers[row["customer_id"]] = CustomerRow(
                customer_id=row["customer_id"],
                customer_unique_id=row["customer_unique_id"],
                zip_prefix=row["customer_zip_code_prefix"],
                city=row["customer_city"],
                state=row["customer_state"],
            )

        for row in self._rows("products"):
            category = (row.get("product_category_name") or "").strip()
            self.products[row["product_id"]] = ProductRow(
                product_id=row["product_id"],
                category_name=category or None,
            )

        for row in self._rows("sellers"):
            self.sellers[row["seller_id"]] = SellerRow(
                seller_id=row["seller_id"],
                zip_prefix=row["seller_zip_code_prefix"],
                city=row["seller_city"],
                state=row["seller_state"],
            )

        for row in self._rows("category_translation"):
            self.category_pt_to_en[row["product_category_name"]] = row[
                "product_category_name_english"
            ]

        # Duyet orders theo dung thu tu dong -> orders_by_customer_unique giu thu tu nguon.
        for row in self._rows("orders"):
            order = OrderRow(
                order_id=row["order_id"],
                customer_id=row["customer_id"],
                order_status=row["order_status"],
                purchase_at=_parse_ts(row["order_purchase_timestamp"]),
                approved_at=_parse_ts(row["order_approved_at"]),
                delivered_carrier_at=_parse_ts(row["order_delivered_carrier_date"]),
                delivered_customer_at=_parse_ts(row["order_delivered_customer_date"]),
                estimated_delivery_at=_parse_ts(row["order_estimated_delivery_date"]),
            )
            self.orders[order.order_id] = order
            customer = self.customers.get(order.customer_id)
            if customer is not None:
                self.orders_by_customer_unique.setdefault(
                    customer.customer_unique_id, []
                ).append(order.order_id)

        for row in self._rows("order_items"):
            self.items_by_order.setdefault(row["order_id"], []).append(
                ItemRow(
                    order_id=row["order_id"],
                    order_item_id=int(row["order_item_id"]),
                    product_id=row["product_id"],
                    seller_id=row["seller_id"],
                    shipping_limit_at=_parse_ts(row["shipping_limit_date"]),
                    price=Decimal(row["price"]),
                    freight_value=Decimal(row["freight_value"]),
                )
            )

        for row in self._rows("order_payments"):
            self.payments_by_order.setdefault(row["order_id"], []).append(
                PaymentRow(
                    order_id=row["order_id"],
                    payment_sequential=int(row["payment_sequential"]),
                    payment_type=row["payment_type"],
                    payment_installments=int(row["payment_installments"]),
                    payment_value=Decimal(row["payment_value"]),
                )
            )

        # Chuan hoa thu tu mot lan tai day, de moi noi khac khong phai sap lai.
        for rows in self.items_by_order.values():
            rows.sort(key=lambda r: r.order_item_id)
        for rows in self.payments_by_order.values():
            rows.sort(key=lambda r: r.payment_sequential)

    # -- tra cuu -----------------------------------------------------------

    def category_display_name(self, raw_pt_name: str | None) -> str | None:
        """Ap config.CATEGORY_NAME_LANGUAGE ('pt' giu nguyen, 'en' join translation)."""
        if not raw_pt_name:
            return None
        if config.CATEGORY_NAME_LANGUAGE == "en":
            return self.category_pt_to_en.get(raw_pt_name, raw_pt_name)
        return raw_pt_name

    def build_bundle(self, order_id: str) -> OrderBundle:
        """Gom moi du lieu lien quan toi mot order thanh mot snapshot bat bien."""
        order = self.orders.get(order_id)
        if order is None:
            return OrderBundle(
                order_id=order_id,
                found=False,
                order=None,
                items=(),
                payments=(),
                customer=None,
                products={},
                sellers={},
                related_order_ids=(),
            )

        items = tuple(self.items_by_order.get(order_id, []))
        payments = tuple(self.payments_by_order.get(order_id, []))
        customer = self.customers.get(order.customer_id)

        products: dict[str, ProductRow] = {}
        for item in items:
            product = self.products.get(item.product_id)
            if product is not None:
                products[item.product_id] = ProductRow(
                    product_id=product.product_id,
                    category_name=self.category_display_name(product.category_name),
                )

        sellers = {
            item.seller_id: self.sellers[item.seller_id]
            for item in items
            if item.seller_id in self.sellers
        }

        related: tuple[str, ...] = ()
        if customer is not None:
            related = tuple(
                oid
                for oid in self.orders_by_customer_unique.get(customer.customer_unique_id, [])
                if oid != order_id
            )

        return OrderBundle(
            order_id=order_id,
            found=True,
            order=order,
            items=items,
            payments=payments,
            customer=customer,
            products=products,
            sellers=sellers,
            related_order_ids=related,
        )

    def stats(self) -> dict[str, int]:
        return {
            "orders": len(self.orders),
            "order_items": sum(len(v) for v in self.items_by_order.values()),
            "order_payments": sum(len(v) for v in self.payments_by_order.values()),
            "customers": len(self.customers),
            "products": len(self.products),
            "sellers": len(self.sellers),
            "category_translation": len(self.category_pt_to_en),
        }


@lru_cache(maxsize=1)
def get_store() -> OlistStore:
    """Singleton: 50 case dung chung mot ban index trong RAM."""
    return OlistStore()


__all__ = [
    "TIMESTAMP_FORMAT",
    "OrderBundle",
    "OrderRow",
    "ItemRow",
    "PaymentRow",
    "CustomerRow",
    "ProductRow",
    "SellerRow",
    "OlistStore",
    "get_store",
    "_fmt_ts",
    "_parse_ts",
]
