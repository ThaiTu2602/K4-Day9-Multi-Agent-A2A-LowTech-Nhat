"""Assembles the final per-case output dict per README section 6, applying
every array cap listed there. All decisions/numbers are taken as-is from
the upstream agents -- this module only shapes and truncates for the
output contract, it does not recompute anything.
"""

from __future__ import annotations

CAPS = {
    "order_ids": 5,
    "item_ids": 5,
    "seller_ids": 3,
    "payment_ids": 5,
    "related_order_ids": 5,
    "product_ids": 5,
    "category_names": 5,
    "ranked_causes": 3,
    "responsible_parties": 3,
    "evidence_ids": 20,
    "resolution_actions": 5,
}


def build_output(case_id: str, order_id: str, order: dict, op: dict, pay: dict, deliv: dict, cust: dict, decision: dict) -> dict:
    items = op["items"][: CAPS["item_ids"]]
    payments = pay["payments"][: CAPS["payment_ids"]]
    seller_ids_capped = op["seller_ids"][: CAPS["seller_ids"]]
    responsible_parties = decision["responsible_parties"][: CAPS["responsible_parties"]]

    evidence_ids = [f"order:{order_id}"]
    evidence_ids += [f"item:{order_id}:{it['order_item_id']}" for it in items]
    evidence_ids += [f"payment:{order_id}:{p['payment_sequential']}" for p in payments]
    responsible_seller_ids = [rp["party_id"] for rp in responsible_parties if rp["party_type"] == "seller"]
    evidence_ids += [f"seller:{sid}" for sid in responsible_seller_ids]
    evidence_ids += [f"policy:{decision['root_cause_code']}"]
    evidence_ids = evidence_ids[: CAPS["evidence_ids"]]

    return {
        "case_id": case_id,
        "case_assessment": {
            "primary_issue": decision["primary_issue"],
            "secondary_issues": decision["secondary_issues"],
            "case_status": decision["case_status"],
            "confidence": decision["confidence"],
        },
        "affected_entities": {
            "order_ids": [order_id][: CAPS["order_ids"]],
            "item_ids": [f"{order_id}:{it['order_item_id']}" for it in items],
            "seller_ids": seller_ids_capped,
            "payment_ids": [f"{order_id}:{p['payment_sequential']}" for p in payments],
        },
        "customer_context": {
            "customer_unique_id": cust["customer_unique_id"],
            "related_order_ids": cust["related_order_ids"][: CAPS["related_order_ids"]],
        },
        "product_context": {
            "product_ids": op["product_ids"][: CAPS["product_ids"]],
            "category_names": op["category_names"][: CAPS["category_names"]],
        },
        "delivery_analysis": {
            "delivered_at": deliv["delivered_at"],
            "estimated_delivery_at": deliv["estimated_delivery_at"],
            "carrier_handoff_at": deliv["carrier_handoff_at"],
            "delivery_variance_hours": deliv["delivery_variance_hours"],
            "seller_handoff_analysis": [
                {
                    "seller_id": s["seller_id"],
                    "shipping_limit_at": s["shipping_limit_at"],
                    "handoff_variance_hours": s["handoff_variance_hours"],
                    "late_handoff": s["late_handoff"],
                }
                for s in deliv["seller_handoff_analysis"]
                if s["seller_id"] in seller_ids_capped
            ],
            "late_handoff_seller_ids": [sid for sid in deliv["late_handoff_seller_ids"] if sid in seller_ids_capped],
        },
        "payment_reconciliation": {
            "currency": "BRL",
            "item_total_brl": pay["item_total_brl"],
            "freight_total_brl": pay["freight_total_brl"],
            "expected_total_brl": pay["expected_total_brl"],
            "payment_total_brl": pay["payment_total_brl"],
            "difference_brl": pay["difference_brl"],
            "reconciled": pay["reconciled"],
            "payment_types": pay["payment_types"],
        },
        "root_cause_analysis": {
            "ranked_causes": [{"cause_code": decision["root_cause_code"], "rank": 1}][: CAPS["ranked_causes"]],
            "responsible_parties": responsible_parties,
        },
        "evidence_ids": evidence_ids,
        "financial_resolution": {
            "currency": "BRL",
            "recommended_refund_brl": decision["recommended_refund_brl"],
        },
        "resolution_actions": decision["resolution_actions"][: CAPS["resolution_actions"]],
    }
