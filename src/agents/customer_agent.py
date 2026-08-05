from src.data_loader import DataLoader

class CustomerAgent:
    def __init__(self, data_loader: DataLoader):
        self.data_loader = data_loader

    def analyze(self, customer_id: str, claimed_order_id: str):
        customer_info = self.data_loader.get_customer_by_id(customer_id)
        if not customer_info:
            return {
                "customer_unique_id": None,
                "related_order_ids": [],
                "is_repeat_customer": False
            }

        customer_unique_id = customer_info['customer_unique_id']
        all_orders = self.data_loader.get_customer_orders(customer_unique_id)
        
        # Collect related order IDs (excluding claimed_order_id)
        related_order_ids = []
        for ord_row in all_orders:
            oid = ord_row['order_id']
            if oid != claimed_order_id:
                related_order_ids.append(oid)
        
        # Max 5 related order IDs according to schema limits
        related_order_ids = related_order_ids[:5]

        return {
            "customer_unique_id": customer_unique_id,
            "related_order_ids": related_order_ids,
            "is_repeat_customer": len(related_order_ids) > 0
        }
