from typing import List, Dict, Any

class PaymentAgent:
    def analyze(self, items: List[Dict[str, Any]], payments: List[Dict[str, Any]]) -> Dict[str, Any]:
        payment_total_brl = round(sum(float(p.get('payment_value', 0.0)) for p in payments), 2)
        
        # Preserve original CSV appearance order for payment types
        payment_types = list(dict.fromkeys(p.get('payment_type') for p in payments if p.get('payment_type')))

        if not items:
            return {
                "currency": "BRL",
                "item_total_brl": 0.0,
                "freight_total_brl": 0.0,
                "expected_total_brl": None,
                "payment_total_brl": payment_total_brl,
                "difference_brl": None,
                "reconciled": None,
                "payment_types": payment_types
            }

        item_total_brl = round(sum(float(i.get('price', 0.0)) for i in items), 2)
        freight_total_brl = round(sum(float(i.get('freight_value', 0.0)) for i in items), 2)
        expected_total_brl = round(item_total_brl + freight_total_brl, 2)
        difference_brl = round(payment_total_brl - expected_total_brl, 2)
        reconciled = abs(difference_brl) <= 0.10

        return {
            "currency": "BRL",
            "item_total_brl": item_total_brl,
            "freight_total_brl": freight_total_brl,
            "expected_total_brl": expected_total_brl,
            "payment_total_brl": payment_total_brl,
            "difference_brl": difference_brl,
            "reconciled": reconciled,
            "payment_types": payment_types
        }
