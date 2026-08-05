import json
import time
from pathlib import Path
from typing import Dict, Any
from src.data_loader import DataLoader
from src.agents.customer_agent import CustomerAgent
from src.agents.order_product_agent import OrderProductAgent
from src.agents.delivery_agent import DeliveryAgent
from src.agents.payment_agent import PaymentAgent
from src.agents.policy_agent import PolicyAgent
from src.agents.verifier_agent import VerifierAgent
from src.config import OUTPUT_DIR, TRACE_FILE, TRACE_FILE_LOGGING

class Coordinator:
    def __init__(self):
        self.data_loader = DataLoader()
        self.customer_agent = CustomerAgent(self.data_loader)
        self.order_product_agent = OrderProductAgent(self.data_loader)
        self.delivery_agent = DeliveryAgent()
        self.payment_agent = PaymentAgent()
        self.policy_agent = PolicyAgent()
        self.verifier_agent = VerifierAgent()

    def process_case(self, case_file_path: Path) -> Dict[str, Any]:
        start_time = time.time()
        with open(case_file_path, "r", encoding="utf-8") as f:
            case_input = json.load(f)

        case_id = case_input["case_id"]
        customer_request = case_input.get("customer_request", {})
        claimed_order_id = customer_request.get("claimed_order_id", "")
        customer_request_msg = customer_request.get("message", "")
        trace_logs = []

        # Step 1: Coordinator initializes case
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "Coordinator",
            "event": "start_case",
            "details": f"Processing {case_id} for claimed order {claimed_order_id} with request: '{customer_request_msg[:50]}...'"
        })
        order_dict = self.data_loader.get_order(claimed_order_id)
        if not order_dict:
            raise ValueError(f"Order ID {claimed_order_id} not found in database!")

        customer_id = order_dict["customer_id"]

        # Step 2: Handoff to CustomerAgent
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "CustomerAgent",
            "event": "handoff_start",
            "details": f"Retrieving customer identity & purchase history for customer_id {customer_id}"
        })
        customer_res = self.customer_agent.analyze(customer_id, claimed_order_id)
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "CustomerAgent",
            "event": "handoff_complete",
            "result": customer_res,
            "details": f"Retrieved identity for customer_unique_id={customer_res['customer_unique_id']} ({len(customer_res['related_order_ids'])} previous orders)"
        })

        # Step 3: Handoff to OrderProductAgent
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "OrderProductAgent",
            "event": "handoff_start",
            "details": f"Retrieving items, products, and raw categories for order {claimed_order_id}"
        })
        order_product_res = self.order_product_agent.analyze(claimed_order_id)
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "OrderProductAgent",
            "event": "handoff_complete",
            "result": {
                "item_count": len(order_product_res["items"]),
                "product_ids": order_product_res["product_ids"],
                "category_names": order_product_res["category_names"]
            },
            "details": f"Retrieved {len(order_product_res['items'])} items across {len(order_product_res['category_names'])} categories: {order_product_res['category_names']}"
        })

        items = order_product_res["items"]
        product_ids = order_product_res["product_ids"]
        category_names = order_product_res["category_names"]
        seller_ids = order_product_res["seller_ids"]

        # Step 4: Payments retrieval
        payments = self.data_loader.get_order_payments(claimed_order_id)

        # Step 5: Handoff to DeliveryAgent
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "DeliveryAgent",
            "event": "handoff_start",
            "details": f"Calculating delivery variance & seller handoff metrics for order {claimed_order_id}"
        })
        delivery_res = self.delivery_agent.analyze(order_dict, items)
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "DeliveryAgent",
            "event": "handoff_complete",
            "result": delivery_res,
            "details": f"Calculated delivery variance {delivery_res.get('delivery_variance_hours')} hrs; {len(delivery_res.get('late_handoff_seller_ids', []))} late handoff sellers"
        })

        # Step 6: Handoff to PaymentAgent
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "PaymentAgent",
            "event": "handoff_start",
            "details": f"Reconciling {len(payments)} payment rows against item total + freight total"
        })
        payment_res = self.payment_agent.analyze(items, payments)
        payment_res["num_payments"] = len(payments)
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "PaymentAgent",
            "event": "handoff_complete",
            "result": payment_res,
            "details": f"Reconciled payment total {payment_res['payment_total_brl']} BRL against expected {payment_res['expected_total_brl']} BRL (diff: {payment_res['difference_brl']} BRL)"
        })

        # Step 7: Handoff to PolicyAgent
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "PolicyAgent",
            "event": "handoff_start",
            "details": "Evaluating EC_POLICY_V2 rules & Groq LLM reasoning with customer request context"
        })
        policy_res = self.policy_agent.evaluate(order_dict, delivery_res, payment_res, customer_res, items, category_names, customer_request_msg)
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "PolicyAgent",
            "event": "handoff_complete",
            "result": policy_res,
            "details": f"Evaluated primary_issue '{policy_res['primary_issue']}' with cause_code '{policy_res['cause_code']}' and dynamic confidence {policy_res['confidence']}"
        })

        # Build Entity IDs & Evidence IDs in strict schema order
        item_ids = [f"{claimed_order_id}:{it['order_item_id']}" for it in items]
        payment_ids = [f"{claimed_order_id}:{p['payment_sequential']}" for p in payments]

        evidence_ids = [f"order:{claimed_order_id}"]
        for it_id in item_ids:
            evidence_ids.append(f"item:{it_id}")
        for p_id in payment_ids:
            evidence_ids.append(f"payment:{p_id}")

        # Add seller evidence ONLY IF responsible seller exists in responsible_parties
        if policy_res['primary_issue'] == 'late_delivery_seller':
            for resp_p in policy_res['responsible_parties']:
                if resp_p['party_type'] == 'seller':
                    s_id = resp_p['party_id']
                    evidence_ids.append(f"seller:{s_id}")

        evidence_ids.append(f"policy:{policy_res['cause_code']}")

        # Assemble Output Object
        output_data = {
            "case_id": case_id,
            "case_assessment": {
                "primary_issue": policy_res["primary_issue"],
                "secondary_issues": policy_res["secondary_issues"],
                "case_status": policy_res["case_status"],
                "confidence": policy_res["confidence"]
            },
            "affected_entities": {
                "order_ids": [claimed_order_id],
                "item_ids": item_ids,
                "seller_ids": seller_ids,
                "payment_ids": payment_ids
            },
            "customer_context": {
                "customer_unique_id": customer_res["customer_unique_id"],
                "related_order_ids": customer_res["related_order_ids"]
            },
            "product_context": {
                "product_ids": product_ids,
                "category_names": category_names
            },
            "delivery_analysis": delivery_res,
            "payment_reconciliation": {
                "currency": payment_res["currency"],
                "item_total_brl": payment_res["item_total_brl"],
                "freight_total_brl": payment_res["freight_total_brl"],
                "expected_total_brl": payment_res["expected_total_brl"],
                "payment_total_brl": payment_res["payment_total_brl"],
                "difference_brl": payment_res["difference_brl"],
                "reconciled": payment_res["reconciled"],
                "payment_types": payment_res["payment_types"]
            },
            "root_cause_analysis": {
                "ranked_causes": [
                    {"cause_code": policy_res["cause_code"], "rank": 1}
                ],
                "responsible_parties": policy_res["responsible_parties"]
            },
            "evidence_ids": evidence_ids,
            "financial_resolution": {
                "currency": "BRL",
                "recommended_refund_brl": policy_res["recommended_refund_brl"]
            },
            "resolution_actions": policy_res["resolution_actions"]
        }

        # Step 8: Handoff to VerifierAgent
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "VerifierAgent",
            "event": "handoff_start",
            "details": "Verifying schema bounds and auditing confidence compliance"
        })
        verified_output = self.verifier_agent.verify_and_clean(output_data, customer_request_msg)
        trace_logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": "VerifierAgent",
            "event": "handoff_complete",
            "details": f"Audited schema compliance and verified final confidence score {verified_output['case_assessment']['confidence']}"
        })

        # Write output JSON file
        out_file_path = OUTPUT_DIR / f"{case_id}.json"
        with open(out_file_path, "w", encoding="utf-8") as f:
            json.dump(verified_output, f, indent=2, ensure_ascii=False)

        # Record Trace Entry (Sync to root & logging/)
        trace_entry = {
            "case_id": case_id,
            "claimed_order_id": claimed_order_id,
            "execution_time_seconds": round(time.time() - start_time, 3),
            "trace": trace_logs,
            "final_primary_issue": verified_output["case_assessment"]["primary_issue"],
            "final_refund_brl": verified_output["financial_resolution"]["recommended_refund_brl"]
        }

        with open(TRACE_FILE, "a", encoding="utf-8") as tf:
            tf.write(json.dumps(trace_entry, ensure_ascii=False) + "\n")

        with open(TRACE_FILE_LOGGING, "a", encoding="utf-8") as tfl:
            tfl.write(json.dumps(trace_entry, ensure_ascii=False) + "\n")

        print(f"Case {case_id} processed -> {out_file_path}")
        return verified_output
