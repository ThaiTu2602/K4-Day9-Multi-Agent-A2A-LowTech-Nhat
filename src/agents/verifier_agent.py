from typing import Dict, Any

class VerifierAgent:
    def verify_and_clean(self, output_dict: Dict[str, Any]) -> Dict[str, Any]:
        # Copy to avoid mutating in place
        res = dict(output_dict)

        # Validate limits
        res['affected_entities']['order_ids'] = res['affected_entities'].get('order_ids', [])[:5]
        res['affected_entities']['item_ids'] = res['affected_entities'].get('item_ids', [])[:5]
        res['affected_entities']['seller_ids'] = res['affected_entities'].get('seller_ids', [])[:3]
        res['affected_entities']['payment_ids'] = res['affected_entities'].get('payment_ids', [])[:5]

        res['customer_context']['related_order_ids'] = res['customer_context'].get('related_order_ids', [])[:5]
        res['product_context']['product_ids'] = res['product_context'].get('product_ids', [])[:5]
        res['product_context']['category_names'] = res['product_context'].get('category_names', [])[:5]

        res['delivery_analysis']['seller_handoff_analysis'] = res['delivery_analysis'].get('seller_handoff_analysis', [])[:3]
        res['delivery_analysis']['late_handoff_seller_ids'] = res['delivery_analysis'].get('late_handoff_seller_ids', [])[:3]

        res['root_cause_analysis']['ranked_causes'] = res['root_cause_analysis'].get('ranked_causes', [])[:3]
        res['root_cause_analysis']['responsible_parties'] = res['root_cause_analysis'].get('responsible_parties', [])[:3]

        res['evidence_ids'] = res.get('evidence_ids', [])[:20]
        res['resolution_actions'] = res.get('resolution_actions', [])[:5]

        # Check confidence range
        conf = float(res['case_assessment'].get('confidence', 0.95))
        res['case_assessment']['confidence'] = round(max(0.0, min(1.0, conf)), 2)

        # Check case status validity
        status = res['case_assessment'].get('case_status')
        if status not in ['action_required', 'no_action']:
            refund = res['financial_resolution'].get('recommended_refund_brl', 0.0)
            res['case_assessment']['case_status'] = 'action_required' if refund > 0 else 'no_action'

        return res
