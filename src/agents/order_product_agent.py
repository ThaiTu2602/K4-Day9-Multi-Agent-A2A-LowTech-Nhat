import pandas as pd
from typing import List, Dict, Any
from src.data_loader import DataLoader

class OrderProductAgent:
    def __init__(self, data_loader: DataLoader):
        self.data_loader = data_loader

    def analyze(self, order_id: str) -> Dict[str, Any]:
        items = self.data_loader.get_order_items(order_id)
        
        product_ids = []
        category_names = []
        seller_ids = []

        for item in items:
            p_id = item.get("product_id")
            s_id = item.get("seller_id")

            if p_id and p_id not in product_ids:
                product_ids.append(p_id)
                p_info = self.data_loader.get_product(p_id)
                if p_info:
                    c_name = p_info.get("product_category_name")
                    if not pd.isna(c_name) and c_name and c_name not in category_names:
                        category_names.append(str(c_name))

            if s_id and s_id not in seller_ids:
                seller_ids.append(s_id)

        # Preserve order and limit according to schema rules
        return {
            "items": items,
            "product_ids": product_ids[:5],
            "category_names": category_names[:5],
            "seller_ids": seller_ids[:3]
        }
