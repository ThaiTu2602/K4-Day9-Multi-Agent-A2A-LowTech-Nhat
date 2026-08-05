"""
DataStore — tải toàn bộ 9 file CSV Olist một lần và cung cấp
các cấu trúc lookup nhanh cho tất cả agents.

MODEL: rule-based (0B parameters)
"""
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


class DataStore:
    """Singleton-like data store được khởi tạo một lần, chia sẻ cho mọi agent."""

    def __init__(self):
        print("[DataStore] Loading CSV datasets...")

        # ── Raw DataFrames ──────────────────────────────────────────────────
        self.orders = pd.read_csv(
            DATA_DIR / "olist_orders_dataset.csv",
            parse_dates=[
                "order_purchase_timestamp",
                "order_approved_at",
                "order_delivered_carrier_date",
                "order_delivered_customer_date",
                "order_estimated_delivery_date",
            ],
        )
        self.customers = pd.read_csv(DATA_DIR / "olist_customers_dataset.csv")
        self.order_items = pd.read_csv(
            DATA_DIR / "olist_order_items_dataset.csv",
            parse_dates=["shipping_limit_date"],
        )
        self.order_payments = pd.read_csv(
            DATA_DIR / "olist_order_payments_dataset.csv"
        )
        self.products = pd.read_csv(DATA_DIR / "olist_products_dataset.csv")
        self.sellers = pd.read_csv(DATA_DIR / "olist_sellers_dataset.csv")
        self.category_translation = pd.read_csv(
            DATA_DIR / "product_category_name_translation.csv"
        )

        # ── Pre-built indexes ───────────────────────────────────────────────
        self._build_indexes()
        print("[DataStore] All datasets loaded and indexed.")

    def _build_indexes(self):
        """Tạo dict/map để O(1) lookup thay vì O(n) filtering."""

        # orders: order_id → row (Series)
        self._orders_idx = self.orders.set_index("order_id")

        # customers: customer_id → row
        self._customers_by_cid = self.customers.set_index("customer_id")

        # customer_unique_id → list of customer_id
        self._unique_to_cids: dict[str, list[str]] = (
            self.customers.groupby("customer_unique_id")["customer_id"]
            .apply(list)
            .to_dict()
        )

        # customer_id → customer_unique_id
        self._cid_to_unique: dict[str, str] = dict(
            zip(self.customers["customer_id"], self.customers["customer_unique_id"])
        )

        # order_id → DataFrame of items
        self._items_by_order: dict[str, pd.DataFrame] = dict(
            tuple(self.order_items.groupby("order_id"))
        )

        # order_id → DataFrame of payments
        self._payments_by_order: dict[str, pd.DataFrame] = dict(
            tuple(self.order_payments.groupby("order_id"))
        )

        # product_id → row
        self._products_idx = self.products.set_index("product_id")

        # category name PT → EN
        self._category_map: dict[str, str] = dict(
            zip(
                self.category_translation["product_category_name"],
                self.category_translation["product_category_name_english"],
            )
        )

        # customer_id → list[order_id]
        self._cid_to_order_ids: dict[str, list[str]] = (
            self.orders.groupby("customer_id")["order_id"]
            .apply(list)
            .to_dict()
        )

    # ── Public helpers ──────────────────────────────────────────────────────

    def get_order(self, order_id: str) -> pd.Series | None:
        """Trả về Series của order hoặc None nếu không tồn tại."""
        if order_id in self._orders_idx.index:
            return self._orders_idx.loc[order_id]
        return None

    def get_items(self, order_id: str) -> pd.DataFrame:
        """Trả về DataFrame items của order (có thể rỗng)."""
        return self._items_by_order.get(order_id, pd.DataFrame())

    def get_payments(self, order_id: str) -> pd.DataFrame:
        """Trả về DataFrame payments của order (có thể rỗng)."""
        return self._payments_by_order.get(order_id, pd.DataFrame())

    def get_customer_unique_id(self, customer_id: str) -> str | None:
        return self._cid_to_unique.get(customer_id)

    def get_related_order_ids(
        self, customer_unique_id: str, exclude_order_id: str
    ) -> list[str]:
        """Các order_id khác cùng customer_unique_id (tối đa 5)."""
        cids = self._unique_to_cids.get(customer_unique_id, [])
        related = []
        for cid in cids:
            for oid in self._cid_to_order_ids.get(cid, []):
                if oid != exclude_order_id and oid not in related:
                    related.append(oid)
        return related[:5]

    def get_product(self, product_id: str) -> pd.Series | None:
        if product_id in self._products_idx.index:
            return self._products_idx.loc[product_id]
        return None

    def translate_category(self, pt_name: str) -> str:
        """Dịch category name từ Portuguese → English."""
        return self._category_map.get(pt_name, pt_name)
