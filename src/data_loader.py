import pandas as pd
from pathlib import Path
from src.config import DATA_DIR

class DataLoader:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DataLoader, cls).__new__(cls)
            cls._instance._load_data()
        return cls._instance

    def _load_data(self):
        print("Loading Olist CSV datasets into memory...")
        self.orders_df = pd.read_csv(DATA_DIR / "olist_orders_dataset.csv")
        self.customers_df = pd.read_csv(DATA_DIR / "olist_customers_dataset.csv")
        self.items_df = pd.read_csv(DATA_DIR / "olist_order_items_dataset.csv")
        self.payments_df = pd.read_csv(DATA_DIR / "olist_order_payments_dataset.csv")
        self.products_df = pd.read_csv(DATA_DIR / "olist_products_dataset.csv")
        self.translation_df = pd.read_csv(DATA_DIR / "product_category_name_translation.csv")
        self.sellers_df = pd.read_csv(DATA_DIR / "olist_sellers_dataset.csv")
        self.reviews_df = pd.read_csv(DATA_DIR / "olist_order_reviews_dataset.csv")
        
        # Create category translation map
        self.cat_map = dict(zip(self.translation_df['product_category_name'], self.translation_df['product_category_name_english']))
        
        print("Datasets successfully loaded into memory.")

    def get_order(self, order_id: str):
        match = self.orders_df[self.orders_df['order_id'] == order_id]
        if match.empty:
            return None
        return match.iloc[0].to_dict()

    def get_customer_by_id(self, customer_id: str):
        match = self.customers_df[self.customers_df['customer_id'] == customer_id]
        if match.empty:
            return None
        return match.iloc[0].to_dict()

    def get_customer_orders(self, customer_unique_id: str):
        cust_ids = self.customers_df[self.customers_df['customer_unique_id'] == customer_unique_id]['customer_id'].tolist()
        orders = self.orders_df[self.orders_df['customer_id'].isin(cust_ids)]
        return orders.to_dict(orient='records')

    def get_order_items(self, order_id: str):
        items = self.items_df[self.items_df['order_id'] == order_id]
        return items.to_dict(orient='records')

    def get_order_payments(self, order_id: str):
        payments = self.payments_df[self.payments_df['order_id'] == order_id]
        return payments.to_dict(orient='records')

    def get_product(self, product_id: str):
        match = self.products_df[self.products_df['product_id'] == product_id]
        if match.empty:
            return None
        prod = match.iloc[0].to_dict()
        cat_pt = prod.get('product_category_name')
        if cat_pt and cat_pt in self.cat_map:
            prod['category_name_english'] = self.cat_map[cat_pt]
        else:
            prod['category_name_english'] = cat_pt
        return prod
