import json
from typing import Dict, Any, List
from src.config import get_groq_client, MODEL_NAME

class PolicyAgent:
    def __init__(self):
        try:
            self.client = get_groq_client()
        except Exception as e:
            print(f"Warning: Groq client init failed: {e}. Falling back to rule-based confidence.")
            self.client = None

    def evaluate(self, order_dict: Dict[str, Any], delivery_res: Dict[str, Any], payment_res: Dict[str, Any], customer_res: Dict[str, Any], items: List[Dict[str, Any]], categories: List[str]) -> Dict[str, Any]:
        order_status = order_dict.get('order_status', '')
        delivery_var = delivery_res.get('delivery_variance_hours')
        late_sellers = delivery_res.get('late_handoff_seller_ids', [])
        num_payments = payment_res.get('num_payments', 0)
        reconciled = payment_res.get('reconciled')
        payment_total = payment_res.get('payment_total_brl', 0.0)
        freight_total = payment_res.get('freight_total_brl', 0.0)

        # Primary issue evaluation in exact priority order
        primary_issue = None
        cause_code = None
        responsible_parties = []
        refund_brl = 0.0
        main_action = None

        if order_status == 'canceled' and payment_total > 0:
            primary_issue = "canceled_order_paid"
            cause_code = "ORDER_CANCELED_AFTER_PAYMENT"
            responsible_parties = [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]
            refund_brl = payment_total
            main_action = "issue_full_refund"

        elif order_status == 'unavailable' and payment_total > 0:
            primary_issue = "unavailable_order_paid"
            cause_code = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
            responsible_parties = [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]
            refund_brl = payment_total
            main_action = "issue_full_refund"

        elif delivery_var is not None and delivery_var > 0 and len(late_sellers) > 0:
            primary_issue = "late_delivery_seller"
            cause_code = "SELLER_HANDOFF_AFTER_LIMIT"
            responsible_parties = [{"party_type": "seller", "party_id": s} for s in late_sellers]
            refund_brl = freight_total
            main_action = "refund_freight"

        elif delivery_var is not None and delivery_var > 0 and len(late_sellers) == 0:
            primary_issue = "late_delivery_logistics"
            cause_code = "CARRIER_DELIVERED_AFTER_ESTIMATE"
            responsible_parties = [{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}]
            refund_brl = freight_total
            main_action = "refund_freight"

        elif num_payments >= 2 and reconciled is True:
            primary_issue = "valid_split_payment"
            cause_code = "MULTIPLE_PAYMENTS_RECONCILED"
            responsible_parties = []
            refund_brl = 0.0
            main_action = "explain_valid_split_payment"

        else:
            primary_issue = "unsupported_late_claim"
            cause_code = "DELIVERY_WITHIN_ESTIMATE"
            responsible_parties = []
            refund_brl = 0.0
            main_action = "reject_late_refund"

        # Secondary issues evaluation (Strict Priority Sequence)
        secondary_issues = []
        seller_ids = list(set(i.get('seller_id') for i in items if i.get('seller_id')))
        cat_names = list(set(categories))

        if len(items) >= 2:
            secondary_issues.append("multi_item_order")
        if len(seller_ids) >= 2:
            secondary_issues.append("multi_seller_order")
        if num_payments >= 2:
            secondary_issues.append("split_payment")
        if customer_res.get('is_repeat_customer'):
            secondary_issues.append("repeat_customer")
        if len(cat_names) >= 2:
            secondary_issues.append("multiple_categories")

        # Additional resolution actions strictly according to EC_POLICY_V2 rules
        actions = [main_action]
        
        # 1. Seller or carrier delay review
        if len(late_sellers) > 0:
            actions.append("review_seller_handoff")
        elif delivery_var is not None and delivery_var > 0:
            actions.append("review_carrier_delay")

        # 2. Refund completion verification ONLY for full refunds
        if main_action == "issue_full_refund":
            actions.append("verify_refund_completion")

        # 3. Multi-seller coordination
        if "multi_seller_order" in secondary_issues:
            actions.append("coordinate_multi_seller_case")

        # 4. Payment allocation verification for split payments (except valid_split_payment)
        if "split_payment" in secondary_issues and primary_issue != "valid_split_payment":
            actions.append("verify_payment_allocation")

        # Enforce action limit (max 5)
        actions = actions[:5]

        # Case status
        case_status = "action_required" if refund_brl > 0 else "no_action"

        # Confidence calculation via Groq LLM or rule
        confidence = 0.95
        if self.client:
            try:
                prompt = f"""You are an expert dispute resolution auditor for Olist e-commerce.
Primary Issue: {primary_issue}
Cause Code: {cause_code}
Delivery Variance Hours: {delivery_var}
Refund: {refund_brl} BRL
Reconciled: {reconciled}
Order Status: {order_status}

Output JSON format: {{"confidence": 0.95, "reason": "..."}}"""
                resp = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=100
                )
                txt = resp.choices[0].message.content
                parsed = json.loads(txt[txt.find('{'):txt.rfind('}')+1])
                conf = float(parsed.get('confidence', 0.95))
                confidence = max(0.80, min(1.0, conf))
            except Exception as e:
                pass

        return {
            "primary_issue": primary_issue,
            "secondary_issues": secondary_issues,
            "case_status": case_status,
            "confidence": round(confidence, 2),
            "cause_code": cause_code,
            "responsible_parties": responsible_parties,
            "recommended_refund_brl": round(refund_brl, 2),
            "resolution_actions": actions
        }
