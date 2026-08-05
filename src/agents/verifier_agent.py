"""Verifier Agent: last line of defense before a case is written to disk.

Checks (all deterministic, no LLM): every evidence ID is well-formed AND
resolvable against the raw CSVs (a false-positive evidence ID is a hard
gate per README section 5), array caps from README section 6 are
respected, no-item orders have null reconciliation fields, and
case_status/confidence are within the allowed domain.
"""

from __future__ import annotations

import re

from src.data_layer import OlistData
from src.schema import CAPS

_EVIDENCE_RE = re.compile(
    r"^(order:(?P<order>[^:]+)"
    r"|item:(?P<item_order>[^:]+):(?P<item_seq>\d+)"
    r"|payment:(?P<pay_order>[^:]+):(?P<pay_seq>\d+)"
    r"|seller:(?P<seller>[^:]+)"
    r"|policy:(?P<policy>[A-Z_]+))$"
)

KNOWN_ROOT_CAUSES = {
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
}


def _verify_evidence(evidence_ids: list[str], data: OlistData, order_id: str) -> list[str]:
    issues = []
    for eid in evidence_ids:
        m = _EVIDENCE_RE.match(eid)
        if not m:
            issues.append(f"malformed evidence id: {eid}")
            continue
        if m.group("order") and m.group("order") != order_id:
            issues.append(f"evidence references wrong order: {eid}")
        elif m.group("item_order"):
            if m.group("item_order") != order_id:
                issues.append(f"evidence references wrong order: {eid}")
            items = {str(it["order_item_id"]) for it in data.get_items(order_id)}
            if m.group("item_seq") not in items:
                issues.append(f"item id not found in data: {eid}")
        elif m.group("pay_order"):
            if m.group("pay_order") != order_id:
                issues.append(f"evidence references wrong order: {eid}")
            seqs = {str(p["payment_sequential"]) for p in data.get_payments(order_id)}
            if m.group("pay_seq") not in seqs:
                issues.append(f"payment id not found in data: {eid}")
        elif m.group("seller"):
            if data.get_seller(m.group("seller")) is None:
                issues.append(f"seller id not found in data: {eid}")
        elif m.group("policy"):
            if m.group("policy") not in KNOWN_ROOT_CAUSES:
                issues.append(f"unknown root cause code: {eid}")
    return issues


def verify(output: dict, data: OlistData) -> tuple[bool, list[str]]:
    issues: list[str] = []
    order_id = output["affected_entities"]["order_ids"][0] if output["affected_entities"]["order_ids"] else None

    if order_id:
        issues += _verify_evidence(output["evidence_ids"], data, order_id)

    for field, cap in [
        ("affected_entities.order_ids", CAPS["order_ids"]),
        ("affected_entities.item_ids", CAPS["item_ids"]),
        ("affected_entities.seller_ids", CAPS["seller_ids"]),
        ("affected_entities.payment_ids", CAPS["payment_ids"]),
    ]:
        section, key = field.split(".")
        if len(output[section][key]) > cap:
            issues.append(f"{field} exceeds cap {cap}")

    if len(output["customer_context"]["related_order_ids"]) > CAPS["related_order_ids"]:
        issues.append("related_order_ids exceeds cap")
    if len(output["product_context"]["product_ids"]) > CAPS["product_ids"]:
        issues.append("product_ids exceeds cap")
    if len(output["product_context"]["category_names"]) > CAPS["category_names"]:
        issues.append("category_names exceeds cap")
    if len(output["root_cause_analysis"]["ranked_causes"]) > CAPS["ranked_causes"]:
        issues.append("ranked_causes exceeds cap")
    if len(output["root_cause_analysis"]["responsible_parties"]) > CAPS["responsible_parties"]:
        issues.append("responsible_parties exceeds cap")
    if len(output["evidence_ids"]) > CAPS["evidence_ids"]:
        issues.append("evidence_ids exceeds cap")
    if len(output["resolution_actions"]) > CAPS["resolution_actions"]:
        issues.append("resolution_actions exceeds cap")

    conf = output["case_assessment"]["confidence"]
    if not (0.0 <= conf <= 1.0):
        issues.append(f"confidence out of range: {conf}")

    if output["case_assessment"]["case_status"] not in ("action_required", "no_action"):
        issues.append(f"invalid case_status: {output['case_assessment']['case_status']}")

    pr = output["payment_reconciliation"]
    has_items = len(output["affected_entities"]["item_ids"]) > 0
    if not has_items:
        for f in ("expected_total_brl", "difference_brl", "reconciled"):
            if pr[f] is not None:
                issues.append(f"{f} should be null when order has no items")

    return len(issues) == 0, issues
