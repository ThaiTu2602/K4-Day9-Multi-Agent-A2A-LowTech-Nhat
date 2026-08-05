import json
from typing import Dict, Any
from src.config import get_groq_client, MODEL_NAME

class VerifierAgent:
    def __init__(self):
        try:
            self.client = get_groq_client()
        except Exception:
            self.client = None

    def verify_and_clean(self, output_dict: Dict[str, Any], customer_request_msg: str = "") -> Dict[str, Any]:
        res = dict(output_dict)

        # Enforce array length boundaries
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

        # LLM Verification call by VerifierAgent
        current_conf = float(res['case_assessment'].get('confidence', 0.95))
        if self.client:
            try:
                prompt = f"""You are the Lead Quality Verification Agent for Olist Dispute Resolution.
Case ID: {res.get('case_id')}
Customer Claim Message: "{customer_request_msg}"
Primary Issue: {res['case_assessment'].get('primary_issue')}
Evidence Count: {len(res['evidence_ids'])}
Recommended Refund BRL: {res['financial_resolution'].get('recommended_refund_brl')}
Current Evaluated Confidence: {current_conf}

Audit the overall assessment validity and verify the final confidence score (between 0.82 and 0.99).
Return STRICT JSON format: {{"verified": true, "confidence": <verified_float>}}"""
                resp = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=60
                )
                txt = resp.choices[0].message.content
                parsed = json.loads(txt[txt.find('{'):txt.rfind('}')+1])
                conf = float(parsed.get('confidence', current_conf))
                res['case_assessment']['confidence'] = round(max(0.80, min(0.99, conf)), 2)
            except Exception:
                res['case_assessment']['confidence'] = round(max(0.80, min(0.99, current_conf)), 2)
        else:
            res['case_assessment']['confidence'] = round(max(0.80, min(0.99, current_conf)), 2)

        # Check case status validity
        status = res['case_assessment'].get('case_status')
        if status not in ['action_required', 'no_action']:
            refund = res['financial_resolution'].get('recommended_refund_brl', 0.0)
            res['case_assessment']['case_status'] = 'action_required' if refund > 0 else 'no_action'

        return res
