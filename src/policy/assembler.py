"""Dung file output cuoi cung tu fact book + ket luan cua Policy Agent.

Assembler khong tu nghi ra so lieu nao. Moi gia tri deu di thang tu fact (do tool
tinh) hoac tu PolicyDecision (do Policy Agent quyet, rule engine kiem chung).
"""

from __future__ import annotations

from typing import Any

from src import config
from src.contracts import PolicyDecision
from src.policy import limits
from src.policy.rules import FactBook

# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def build_evidence_ids(
    facts: FactBook, decision: PolicyDecision, order_id: str
) -> list[str]:
    """README muc 5.

    "Evidence cua case gom order, cac item, cac payment, seller chiu trach nhiem
     neu co va policy tuong ung."

    Chi 5 dang ID duoc phep, va phai dung duoc truc tiep tu du lieu:
        order:<order_id>
        item:<order_id>:<order_item_id>
        payment:<order_id>:<payment_sequential>
        seller:<seller_id>
        policy:<root_cause_code>

    Dung dung cac list DA CAT theo tran cua affected_entities de evidence khong bao
    gio tro toi mot ID ma chinh output khong khai bao.

    "seller chiu trach nhiem" = seller trong responsible_parties, khong phai moi
    seller cua don. Voi late_delivery_logistics hay canceled_order_paid thi khong
    co seller evidence nao.
    """
    evidence: list[str] = []

    if facts.get("order_found") is True:
        evidence.append(f"order:{order_id}")

    for item_key in limits.cap(_as_list(facts.get("item_ids")), limits.MAX_ITEM_IDS):
        evidence.append(f"item:{item_key}")

    for payment_key in limits.cap(_as_list(facts.get("payment_ids")), limits.MAX_PAYMENT_IDS):
        evidence.append(f"payment:{payment_key}")

    for party in decision.responsible_parties:
        if party.get("party_type") == "seller":
            evidence.append(f"seller:{party['party_id']}")

    evidence.append(f"policy:{decision.root_cause_code}")

    return limits.dedup_cap(evidence, limits.MAX_EVIDENCE_IDS)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _as_list(value: Any) -> list:
    return list(value) if isinstance(value, list) else []


def assemble_output(
    case_id: str, order_id: str, facts: FactBook, decision: PolicyDecision
) -> dict:
    """Dung dung schema README muc 6, dung thu tu key de file de doi chieu bang mat."""
    return {
        "case_id": case_id,
        "case_assessment": {
            "primary_issue": decision.primary_issue,
            "secondary_issues": list(decision.secondary_issues),
            "case_status": decision.case_status,
            "confidence": decision.confidence,
        },
        "affected_entities": {
            # README muc 3: KHONG dua order lich su vao day.
            "order_ids": limits.cap(_as_list(facts.get("order_ids")), limits.MAX_ORDER_IDS),
            "item_ids": limits.cap(_as_list(facts.get("item_ids")), limits.MAX_ITEM_IDS),
            "seller_ids": limits.cap(_as_list(facts.get("seller_ids")), limits.MAX_SELLER_IDS),
            "payment_ids": limits.cap(
                _as_list(facts.get("payment_ids")), limits.MAX_PAYMENT_IDS
            ),
        },
        "customer_context": {
            "customer_unique_id": facts.get("customer_unique_id"),
            "related_order_ids": limits.cap(
                _as_list(facts.get("related_order_ids")), limits.MAX_RELATED_ORDER_IDS
            ),
        },
        "product_context": {
            "product_ids": limits.cap(
                _as_list(facts.get("product_ids")), limits.MAX_PRODUCT_IDS
            ),
            "category_names": limits.cap(
                _as_list(facts.get("category_names")), limits.MAX_CATEGORY_NAMES
            ),
        },
        "delivery_analysis": {
            "delivered_at": facts.get("delivered_at"),
            "estimated_delivery_at": facts.get("estimated_delivery_at"),
            "carrier_handoff_at": facts.get("carrier_handoff_at"),
            "delivery_variance_hours": facts.get("delivery_variance_hours"),
            "seller_handoff_analysis": _as_list(facts.get("seller_handoff_analysis")),
            "late_handoff_seller_ids": limits.cap(
                _as_list(facts.get("late_handoff_seller_ids")), limits.MAX_SELLER_IDS
            ),
        },
        "payment_reconciliation": {
            "currency": facts.get("currency", config.CURRENCY),
            "item_total_brl": facts.get("item_total_brl"),
            "freight_total_brl": facts.get("freight_total_brl"),
            "expected_total_brl": facts.get("expected_total_brl"),
            "payment_total_brl": facts.get("payment_total_brl"),
            "difference_brl": facts.get("difference_brl"),
            "reconciled": facts.get("reconciled"),
            "payment_types": _as_list(facts.get("payment_types")),
        },
        "root_cause_analysis": {
            # Vi du o README muc 6 la mot case late_delivery_seller CO ca split
            # payment ma van chi liet ke dung mot cause -> mot cause, rank 1.
            "ranked_causes": limits.cap(
                [{"cause_code": decision.root_cause_code, "rank": 1}], limits.MAX_ROOT_CAUSES
            ),
            "responsible_parties": limits.cap(
                list(decision.responsible_parties), limits.MAX_RESPONSIBLE_PARTIES
            ),
        },
        "evidence_ids": build_evidence_ids(facts, decision, order_id),
        "financial_resolution": {
            "currency": config.CURRENCY,
            "recommended_refund_brl": decision.recommended_refund_brl,
        },
        "resolution_actions": limits.cap(
            list(decision.resolution_actions), limits.MAX_RESOLUTION_ACTIONS
        ),
    }


__all__ = ["assemble_output", "build_evidence_ids"]
