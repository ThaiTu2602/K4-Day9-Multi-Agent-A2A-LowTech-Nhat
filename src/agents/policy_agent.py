"""Policy Agent: applies EC_POLICY_V2 deterministically to the evidence
bundle handed off by the Customer, Order & Product, Payment and Delivery
agents. Pure rule code on purpose -- refund amounts and taxonomy decisions
must be reproducible and must never depend on an LLM sample.

Priority order and formulas follow README section 4 verbatim. Two design
decisions the README leaves implicit are documented inline below:

1. Which secondary issue triggers which *extra* resolution action. The
   README only fixes the *order* extra actions appear in
   (review_seller_handoff/review_carrier_delay, verify_refund_completion,
   coordinate_multi_seller_case, verify_payment_allocation) and says
   verify_payment_allocation is skipped when the primary issue already is
   valid_split_payment. We map: review_seller_handoff/review_carrier_delay
   <- primary issue itself; verify_refund_completion <- full-order refund
   primaries (canceled/unavailable, since those need refund-completion
   follow-up); coordinate_multi_seller_case <- multi_seller_order secondary
   issue; verify_payment_allocation <- split_payment secondary issue
   (except when primary is valid_split_payment, per the explicit rule).
2. Orders with a delivered_customer_date but missing/late data needed to
   confidently pick a rule fall back to unsupported_late_claim with a
   lowered confidence score, rather than raising, since the pipeline must
   produce an output for all 50 cases.
"""

from __future__ import annotations

RESPONSIBLE_PARTY_CAP = 3
ROOT_CAUSE_BY_PRIMARY = {
    "canceled_order_paid": "ORDER_CANCELED_AFTER_PAYMENT",
    "unavailable_order_paid": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "late_delivery_seller": "SELLER_HANDOFF_AFTER_LIMIT",
    "late_delivery_logistics": "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "valid_split_payment": "MULTIPLE_PAYMENTS_RECONCILED",
    "unsupported_late_claim": "DELIVERY_WITHIN_ESTIMATE",
}
ACTION_BY_PRIMARY = {
    "canceled_order_paid": "issue_full_refund",
    "unavailable_order_paid": "issue_full_refund",
    "late_delivery_seller": "refund_freight",
    "late_delivery_logistics": "refund_freight",
    "valid_split_payment": "explain_valid_split_payment",
    "unsupported_late_claim": "reject_late_refund",
}
ACTION_REQUIRED_PRIMARIES = {
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
}


def _pick_primary(order: dict, op: dict, pay: dict, deliv: dict) -> tuple[str, list[tuple[str, str]], float, bool]:
    """Returns (primary_issue, responsible_parties, refund_brl, is_fallback)."""
    status = order["order_status"]
    payment_total = pay["payment_total_brl"] or 0.0
    freight_total = pay["freight_total_brl"]

    if status == "canceled" and payment_total > 0:
        return "canceled_order_paid", [("platform", "OLIST_PLATFORM")], payment_total, False

    if status == "unavailable" and payment_total > 0:
        return "unavailable_order_paid", [("platform", "OLIST_PLATFORM")], payment_total, False

    if deliv["is_late"] and freight_total is not None:
        if deliv["late_handoff_seller_ids"]:
            parties = [("seller", sid) for sid in deliv["late_handoff_seller_ids"][:RESPONSIBLE_PARTY_CAP]]
            return "late_delivery_seller", parties, freight_total, False
        return "late_delivery_logistics", [("logistics_provider", "LOGISTICS_PROVIDER")], freight_total, False

    if pay["reconciled"] is True and len(pay["payments"]) >= 2:
        return "valid_split_payment", [], 0.0, False

    if not deliv["is_late"] and pay["reconciled"] is True:
        return "unsupported_late_claim", [], 0.0, False

    return "unsupported_late_claim", [], 0.0, True


def _secondary_issues(op: dict, pay: dict, cust: dict) -> list[str]:
    issues = []
    if op["multi_item_order"]:
        issues.append("multi_item_order")
    if op["multi_seller_order"]:
        issues.append("multi_seller_order")
    if pay["split_payment"]:
        issues.append("split_payment")
    if cust["repeat_customer"]:
        issues.append("repeat_customer")
    if op["multiple_categories"]:
        issues.append("multiple_categories")
    return issues


def _actions(primary: str, secondary_issues: list[str]) -> list[str]:
    actions = [ACTION_BY_PRIMARY[primary]]

    if primary == "late_delivery_seller":
        actions.append("review_seller_handoff")
    elif primary == "late_delivery_logistics":
        actions.append("review_carrier_delay")

    if primary in ("canceled_order_paid", "unavailable_order_paid"):
        actions.append("verify_refund_completion")

    if "multi_seller_order" in secondary_issues:
        actions.append("coordinate_multi_seller_case")

    if "split_payment" in secondary_issues and primary != "valid_split_payment":
        actions.append("verify_payment_allocation")

    return actions[:5]


def _confidence(primary: str, is_fallback: bool, op: dict, pay: dict, cust: dict) -> float:
    score = 0.95
    if is_fallback:
        score -= 0.35
    if not op["items"]:
        score -= 0.15
    if pay["reconciled"] is None:
        score -= 0.05
    if cust["customer_unique_id"] is None:
        score -= 0.1
    return round(max(0.4, min(0.98, score)), 2)


def decide(order: dict, op: dict, pay: dict, deliv: dict, cust: dict) -> dict:
    primary, responsible, refund, is_fallback = _pick_primary(order, op, pay, deliv)
    secondary_issues = _secondary_issues(op, pay, cust)
    root_cause = ROOT_CAUSE_BY_PRIMARY[primary]
    actions = _actions(primary, secondary_issues)
    case_status = "action_required" if primary in ACTION_REQUIRED_PRIMARIES else "no_action"
    confidence = _confidence(primary, is_fallback, op, pay, cust)

    return {
        "primary_issue": primary,
        "secondary_issues": secondary_issues,
        "case_status": case_status,
        "confidence": confidence,
        "root_cause_code": root_cause,
        "responsible_parties": [{"party_type": t, "party_id": i} for t, i in responsible],
        "recommended_refund_brl": round(refund, 2),
        "resolution_actions": actions,
    }
