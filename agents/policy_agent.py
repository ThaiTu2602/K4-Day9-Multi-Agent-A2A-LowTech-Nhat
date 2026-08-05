"""
Agent 6 — PolicyAgent
Nhiệm vụ: Áp dụng EC_POLICY_V2 (ưu tiên đúng thứ tự) để xác định:
    - primary_issue, secondary_issues, case_status, confidence
    - root_cause_analysis (ranked_causes, responsible_parties)
    - financial_resolution (recommended_refund_brl)
    - resolution_actions (primary + supplementary, đúng thứ tự)
    - evidence_ids (chỉ ID có thể verify từ CSV)

Input:  kết quả từ 4 agents trước + order_status
Output: assessment, root_cause, financial, actions, evidence
MODEL: rule-based (0B parameters)
"""
from __future__ import annotations


# ── Primary issue table ───────────────────────────────────────────────────────
_PRIMARY_ACTION = {
    "canceled_order_paid": "issue_full_refund",
    "unavailable_order_paid": "issue_full_refund",
    "late_delivery_seller": "refund_freight",
    "late_delivery_logistics": "refund_freight",
    "valid_split_payment": "explain_valid_split_payment",
    "unsupported_late_claim": "reject_late_refund",
}

_PRIMARY_ROOT_CAUSE = {
    "canceled_order_paid": "ORDER_CANCELED_AFTER_PAYMENT",
    "unavailable_order_paid": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "late_delivery_seller": "SELLER_HANDOFF_AFTER_LIMIT",
    "late_delivery_logistics": "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "valid_split_payment": "MULTIPLE_PAYMENTS_RECONCILED",
    "unsupported_late_claim": "DELIVERY_WITHIN_ESTIMATE",
}

_RESPONSIBLE = {
    "canceled_order_paid": ("platform", "OLIST_PLATFORM"),
    "unavailable_order_paid": ("platform", "OLIST_PLATFORM"),
    "late_delivery_logistics": ("logistics_provider", "LOGISTICS_PROVIDER"),
}


class PolicyAgent:
    name = "policy_agent"

    def run(
        self,
        order_id: str,
        order_status: str | None,
        customer_result: dict,
        order_product_result: dict,
        payment_result: dict,
        delivery_result: dict,
    ) -> dict:
        # ── Unpack từ agents khác ────────────────────────────────────────────
        payment_total: float = payment_result["_payment_total"]
        num_payments: int = payment_result["_num_payments"]
        reconciled: bool | None = payment_result["_reconciled"]
        freight_total: float | None = payment_result["_freight_total"]

        is_late: bool = delivery_result["_is_late_delivery"]
        late_sellers: list[str] = delivery_result["_late_handoff_seller_ids"]

        counts: dict = order_product_result["_counts"]
        num_items: int = counts["num_items"]
        num_sellers: int = counts["num_sellers"]
        num_cats: int = counts["num_categories"]
        seller_ids_all: list[str] = order_product_result.get("_seller_ids_all", [])

        related_orders: list[str] = customer_result.get("related_order_ids", [])
        item_ids: list[str] = order_product_result["affected_entities"]["item_ids"]
        payment_ids: list[str] = order_product_result["affected_entities"][
            "payment_ids"
        ]

        # ── PRIMARY ISSUE (theo thứ tự ưu tiên) ─────────────────────────────
        status = (order_status or "").lower()

        if status == "canceled" and payment_total > 0:
            primary = "canceled_order_paid"
            refund = round(payment_total, 2)
        elif status == "unavailable" and payment_total > 0:
            primary = "unavailable_order_paid"
            refund = round(payment_total, 2)
        elif is_late and late_sellers:
            primary = "late_delivery_seller"
            refund = round(freight_total, 2) if freight_total is not None else 0.0
        elif is_late and not late_sellers:
            primary = "late_delivery_logistics"
            refund = round(freight_total, 2) if freight_total is not None else 0.0
        elif num_payments >= 2 and reconciled:
            primary = "valid_split_payment"
            refund = 0.0
        else:
            primary = "unsupported_late_claim"
            refund = 0.0

        case_status = "action_required" if refund > 0 else "no_action"

        # ── SECONDARY ISSUES (theo thứ tự nghiệp vụ) ────────────────────────
        secondary: list[str] = []
        if num_items >= 2:
            secondary.append("multi_item_order")
        if num_sellers >= 2:
            secondary.append("multi_seller_order")
        if num_payments >= 2:
            secondary.append("split_payment")
        if related_orders:  # có order khác → repeat_customer
            secondary.append("repeat_customer")
        if num_cats >= 2:
            secondary.append("multiple_categories")

        # ── CONFIDENCE & LLM EVALUATION ──────────────────────────────────────
        confidence = _calc_confidence(primary, order_status, delivery_result, payment_result)

        # Call LLM Agent 6 integration
        from core.llm_client import policy_llm_confidence_calibration
        llm_res = policy_llm_confidence_calibration(
            primary_issue=primary,
            context={
                "order_status": order_status,
                "delivery_variance_hours": delivery_result["delivery_analysis"].get("delivery_variance_hours"),
                "reconciled": payment_result.get("_reconciled"),
                "refund": refund
            }
        )
        if llm_res.get("llm_used") and "confidence" in llm_res:
            confidence = round(max(0.0, min(1.0, float(llm_res["confidence"]))), 2)

        # ── ROOT CAUSE ────────────────────────────────────────────────────────
        root_cause_code = _PRIMARY_ROOT_CAUSE[primary]
        ranked_causes = [{"cause_code": root_cause_code, "rank": 1}]

        responsible_parties: list[dict] = []
        if primary in _RESPONSIBLE:
            ptype, pid = _RESPONSIBLE[primary]
            responsible_parties.append({"party_type": ptype, "party_id": pid})
        elif primary == "late_delivery_seller":
            for sid in late_sellers[:3]:
                responsible_parties.append({"party_type": "seller", "party_id": sid})

        # ── EVIDENCE IDs ─────────────────────────────────────────────────────
        evidence: list[str] = []
        evidence.append(f"order:{order_id}")
        for iid in item_ids:  # "order_id:item_id" → "item:order_id:item_id"
            parts = iid.split(":")
            evidence.append(f"item:{parts[0]}:{parts[1]}")
        for pid in payment_ids:
            parts = pid.split(":")
            evidence.append(f"payment:{parts[0]}:{parts[1]}")
        if primary == "late_delivery_seller":
            for sid in late_sellers[:3]:
                evidence.append(f"seller:{sid}")
        evidence.append(f"policy:{root_cause_code}")
        evidence = evidence[:20]  # hard limit

        # ── RESOLUTION ACTIONS ────────────────────────────────────────────────
        actions: list[str] = [_PRIMARY_ACTION[primary]]

        if primary == "late_delivery_seller":
            actions.append("review_seller_handoff")
        elif primary == "late_delivery_logistics":
            actions.append("review_carrier_delay")

        if refund > 0:
            actions.append("verify_refund_completion")

        if "multi_seller_order" in secondary:
            actions.append("coordinate_multi_seller_case")

        # verify_payment_allocation: thêm khi split_payment nhưng primary KHÔNG phải valid_split_payment
        if "split_payment" in secondary and primary != "valid_split_payment":
            actions.append("verify_payment_allocation")

        actions = actions[:5]  # hard limit

        return {
            "case_assessment": {
                "primary_issue": primary,
                "secondary_issues": secondary,
                "case_status": case_status,
                "confidence": confidence,
            },
            "root_cause_analysis": {
                "ranked_causes": ranked_causes,
                "responsible_parties": responsible_parties,
            },
            "financial_resolution": {
                "currency": "BRL",
                "recommended_refund_brl": refund,
            },
            "resolution_actions": actions,
            "evidence_ids": evidence,
            "_trace": {
                "status": "ok",
                "primary": primary,
                "secondary": secondary,
                "refund": refund,
                "confidence": confidence,
                "llm_used": llm_res.get("llm_used", False)
            },
        }


def _calc_confidence(
    primary: str,
    order_status: str | None,
    delivery_result: dict,
    payment_result: dict,
) -> float:
    """
    Confidence dựa trên mức độ đầy đủ của dữ liệu:
    - Hủy/unavailable với payment rõ ràng → 0.98
    - Late delivery với timestamps đầy đủ → 0.95
    - Valid split payment đã reconcile → 0.90
    - Fallback → 0.80
    Giảm -0.05 nếu thiếu timestamps quan trọng.
    """
    base = {
        "canceled_order_paid": 0.98,
        "unavailable_order_paid": 0.98,
        "late_delivery_seller": 0.95,
        "late_delivery_logistics": 0.90,
        "valid_split_payment": 0.90,
        "unsupported_late_claim": 0.85,
    }.get(primary, 0.80)

    da = delivery_result.get("delivery_analysis", {})
    # Trừ điểm nếu thiếu dữ liệu
    if da.get("delivered_at") is None and primary in (
        "late_delivery_seller",
        "late_delivery_logistics",
        "unsupported_late_claim",
    ):
        base -= 0.05
    if payment_result.get("_reconciled") is None:
        base -= 0.05

    return round(max(0.0, min(1.0, base)), 2)
