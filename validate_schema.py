"""
Schema Validator for output/EC_*.json
Checks all 50 output files against README.md schema and constraints.
"""
import json
from pathlib import Path

VALID_PRIMARY = {
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
}

VALID_SECONDARY = [
    "multi_item_order",
    "multi_seller_order",
    "split_payment",
    "repeat_customer",
    "multiple_categories",
]

VALID_ROOT_CAUSES = {
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
}

VALID_ACTIONS = {
    "issue_full_refund",
    "refund_freight",
    "explain_valid_split_payment",
    "reject_late_refund",
    "review_seller_handoff",
    "review_carrier_delay",
    "verify_refund_completion",
    "coordinate_multi_seller_case",
    "verify_payment_allocation",
}

def validate_case(file_path: Path) -> list[str]:
    errors = []
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    # 1. Root keys
    expected_root_keys = [
        "case_id",
        "case_assessment",
        "affected_entities",
        "customer_context",
        "product_context",
        "delivery_analysis",
        "payment_reconciliation",
        "root_cause_analysis",
        "evidence_ids",
        "financial_resolution",
        "resolution_actions",
    ]
    for k in expected_root_keys:
        if k not in data:
            errors.append(f"Missing root key: {k}")

    if errors:
        return errors

    # 2. case_assessment
    ca = data["case_assessment"]
    if ca.get("primary_issue") not in VALID_PRIMARY:
        errors.append(f"Invalid primary_issue: {ca.get('primary_issue')}")

    for sec in ca.get("secondary_issues", []):
        if sec not in VALID_SECONDARY:
            errors.append(f"Invalid secondary_issue: {sec}")

    if ca.get("case_status") not in ("action_required", "no_action"):
        errors.append(f"Invalid case_status: {ca.get('case_status')}")

    conf = ca.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        errors.append(f"Invalid confidence: {conf}")

    # 3. affected_entities
    ae = data["affected_entities"]
    if len(ae.get("order_ids", [])) > 5:
        errors.append("order_ids > 5")
    if len(ae.get("item_ids", [])) > 5:
        errors.append("item_ids > 5")
    if len(ae.get("seller_ids", [])) > 3:
        errors.append("seller_ids > 3")
    if len(ae.get("payment_ids", [])) > 5:
        errors.append("payment_ids > 5")

    # 4. customer_context
    cc = data["customer_context"]
    if len(cc.get("related_order_ids", [])) > 5:
        errors.append("related_order_ids > 5")

    # 5. product_context
    pc = data["product_context"]
    if len(pc.get("product_ids", [])) > 5:
        errors.append("product_ids > 5")
    if len(pc.get("category_names", [])) > 5:
        errors.append("category_names > 5")

    # 6. root_cause_analysis
    rca = data["root_cause_analysis"]
    if len(rca.get("ranked_causes", [])) > 3:
        errors.append("ranked_causes > 3")
    if len(rca.get("responsible_parties", [])) > 3:
        errors.append("responsible_parties > 3")

    # 7. evidence_ids
    ev = data.get("evidence_ids", [])
    if len(ev) > 20:
        errors.append("evidence_ids > 20")
    for eid in ev:
        parts = eid.split(":")
        if parts[0] not in ("order", "item", "payment", "seller", "policy"):
            errors.append(f"Invalid evidence prefix: {eid}")

    # 8. financial_resolution
    fr = data["financial_resolution"]
    if fr.get("currency") != "BRL":
        errors.append(f"Invalid currency: {fr.get('currency')}")

    # 9. resolution_actions
    ra = data.get("resolution_actions", [])
    if len(ra) > 5:
        errors.append("resolution_actions > 5")
    for act in ra:
        if act not in VALID_ACTIONS:
            errors.append(f"Invalid action: {act}")

    return errors

def validate_all():
    output_dir = Path("output")
    files = sorted(output_dir.glob("EC_*.json"))
    if len(files) != 50:
        print(f"ERROR: Expected 50 files, found {len(files)}")
        return

    total_errors = 0
    for f in files:
        errs = validate_case(f)
        if errs:
            print(f"[{f.name}] ERRORS: {errs}")
            total_errors += len(errs)

    if total_errors == 0:
        print("SUCCESS: All 50 output files match the schema perfectly!")
    else:
        print(f"TOTAL ERRORS FOUND: {total_errors}")

if __name__ == "__main__":
    validate_all()
