import pandas as pd
from typing import List, Dict, Any

class DeliveryAgent:
    def analyze(self, order_dict: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        delivered_at = order_dict.get('order_delivered_customer_date')
        if pd.isna(delivered_at) or not delivered_at:
            delivered_at = None

        estimated_delivery_at = order_dict.get('order_estimated_delivery_date')
        if pd.isna(estimated_delivery_at) or not estimated_delivery_at:
            estimated_delivery_at = None

        carrier_handoff_at = order_dict.get('order_delivered_carrier_date')
        if pd.isna(carrier_handoff_at) or not carrier_handoff_at:
            carrier_handoff_at = None

        # Delivery variance hours
        delivery_variance_hours = None
        if delivered_at and estimated_delivery_at:
            dt_del = pd.to_datetime(delivered_at)
            dt_est = pd.to_datetime(estimated_delivery_at)
            delivery_variance_hours = round((dt_del - dt_est).total_seconds() / 3600.0, 2)

        # Seller handoff analysis
        seller_handoff_analysis = []
        late_handoff_seller_ids = []

        # Group items by seller_id to get earliest shipping_limit_date for each seller
        seller_limits = {}
        for item in items:
            s_id = item.get('seller_id')
            limit_dt = item.get('shipping_limit_date')
            if pd.isna(limit_dt) or not limit_dt:
                continue
            if s_id not in seller_limits or limit_dt < seller_limits[s_id]:
                seller_limits[s_id] = limit_dt

        for s_id, limit_dt in seller_limits.items():
            handoff_var_hours = None
            is_late = False
            if carrier_handoff_at and limit_dt:
                dt_carrier = pd.to_datetime(carrier_handoff_at)
                dt_limit = pd.to_datetime(limit_dt)
                handoff_var_hours = round((dt_carrier - dt_limit).total_seconds() / 3600.0, 2)
                is_late = handoff_var_hours > 0

            seller_handoff_analysis.append({
                "seller_id": s_id,
                "shipping_limit_at": str(limit_dt),
                "handoff_variance_hours": handoff_var_hours,
                "late_handoff": is_late
            })

            if is_late and s_id not in late_handoff_seller_ids:
                late_handoff_seller_ids.append(s_id)

        # Limit seller_handoff_analysis to max 3 sellers according to schema limit
        seller_handoff_analysis = seller_handoff_analysis[:3]
        late_handoff_seller_ids = late_handoff_seller_ids[:3]

        return {
            "delivered_at": str(delivered_at) if delivered_at else None,
            "estimated_delivery_at": str(estimated_delivery_at) if estimated_delivery_at else None,
            "carrier_handoff_at": str(carrier_handoff_at) if carrier_handoff_at else None,
            "delivery_variance_hours": delivery_variance_hours,
            "seller_handoff_analysis": seller_handoff_analysis,
            "late_handoff_seller_ids": late_handoff_seller_ids
        }
