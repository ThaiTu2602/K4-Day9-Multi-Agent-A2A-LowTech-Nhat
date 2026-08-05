"""Rule engine EC_POLICY_V2.

Engine nay lam viec tren FACT BOOK -- dung tap fact ma Policy Agent nhin thay --
chu khong doc CSV. Nho vay, khi doi chieu de xuat cua Policy Agent voi engine,
hai ben dung chung dau vao va phep so sanh moi cong bang.

Trong he thong chay that, engine dong vai TRONG TAI: Policy Agent (LLM) de xuat
truoc, engine phan bien; lech thi tra nguoc cho agent sua. Xem src/agents/policy_agent.py.

Khong co case_id nao trong file nay. Toan bo dieu kien deu lay tu bang README muc 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.contracts import PolicyDecision
from src.policy import limits, taxonomy

FactBook = dict[str, Any]


# ---------------------------------------------------------------------------
# Doc fact an toan
# ---------------------------------------------------------------------------


def _num(facts: FactBook, key: str, default: float = 0.0) -> float:
    value = facts.get(key)
    return float(value) if isinstance(value, (int, float)) else default


def _flag(facts: FactBook, key: str) -> bool:
    return facts.get(key) is True


def _list(facts: FactBook, key: str) -> list:
    value = facts.get(key)
    return list(value) if isinstance(value, list) else []


# ---------------------------------------------------------------------------
# Primary issue
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrimaryVerdict:
    issue: str
    reason: str
    matched: bool


def classify_primary(facts: FactBook) -> PrimaryVerdict:
    """Ap 6 luat theo dung THU TU UU TIEN cua README muc 4. Luat dau tien thoa la thang.

    Thu tu quan trong hon dieu kien: mot don giao tre CO 2 payment row thoa ca
    late_delivery_* lan valid_split_payment, nhung late_delivery_* dung truoc nen
    thang. Duyet sai thu tu la sai ket qua du moi dieu kien deu dung.
    """
    status = facts.get("order_status")
    payment_total = _num(facts, "payment_total_brl")
    delivered_late = _flag(facts, "is_delivered_late")
    late_seller = _flag(facts, "has_late_handoff_seller")
    payment_count = int(_num(facts, "payment_count"))
    reconciled = facts.get("reconciled")
    variance = facts.get("delivery_variance_hours")

    # 1. canceled_order_paid
    if status == taxonomy.ORDER_STATUS_CANCELED and payment_total > 0:
        return PrimaryVerdict(
            "canceled_order_paid",
            f"order_status='{status}' va payment_total_brl={payment_total} > 0",
            True,
        )

    # 2. unavailable_order_paid
    if status == taxonomy.ORDER_STATUS_UNAVAILABLE and payment_total > 0:
        return PrimaryVerdict(
            "unavailable_order_paid",
            f"order_status='{status}' va payment_total_brl={payment_total} > 0",
            True,
        )

    # 3. late_delivery_seller
    if delivered_late and late_seller:
        return PrimaryVerdict(
            "late_delivery_seller",
            f"delivery_variance_hours={variance} > 0 va co seller ban giao sau shipping_limit_date",
            True,
        )

    # 4. late_delivery_logistics
    if delivered_late and not late_seller:
        return PrimaryVerdict(
            "late_delivery_logistics",
            f"delivery_variance_hours={variance} > 0 nhung khong seller nao ban giao muon",
            True,
        )

    # 5. valid_split_payment
    if payment_count >= 2 and reconciled is True:
        return PrimaryVerdict(
            "valid_split_payment",
            f"co {payment_count} payment row va tong payment khop item+freight trong sai so 0.10 BRL",
            True,
        )

    # 6. unsupported_late_claim
    if variance is not None and float(variance) <= 0 and reconciled is True:
        return PrimaryVerdict(
            "unsupported_late_claim",
            f"delivery_variance_hours={variance} <= 0 va payment khop",
            True,
        )

    # Khong luat nao thoa. Khong xay ra tren bo 50 case nhung phai xu ly tuong minh
    # thay vi im lang tra ket qua sai.
    return PrimaryVerdict(
        "unsupported_late_claim",
        "Khong dieu kien nao trong EC_POLICY_V2 thoa man; ha ve claim khong duoc chung minh",
        False,
    )


# ---------------------------------------------------------------------------
# Secondary issues
# ---------------------------------------------------------------------------


def collect_secondary(facts: FactBook) -> list[str]:
    """5 secondary issue, THEM THEO DUNG THU TU liet ke o README muc 4."""
    conditions = {
        "multi_item_order": int(_num(facts, "item_count")) >= 2,
        "multi_seller_order": int(_num(facts, "seller_count")) >= 2,
        "split_payment": int(_num(facts, "payment_count")) >= 2,
        "repeat_customer": int(_num(facts, "related_order_count")) > 0,
        "multiple_categories": int(_num(facts, "distinct_category_count")) >= 2,
    }
    # Duyet theo SECONDARY_ISSUE_ORDER chu khong theo thu tu dict.
    return [name for name in taxonomy.SECONDARY_ISSUE_ORDER if conditions[name]]


# ---------------------------------------------------------------------------
# Responsible party va refund
# ---------------------------------------------------------------------------


def resolve_responsible_parties(primary_issue: str, facts: FactBook) -> list[dict]:
    """Cot 'Responsible party' cua bang README muc 4."""
    if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
        return [
            {
                "party_type": taxonomy.PARTY_TYPE_PLATFORM,
                "party_id": taxonomy.PLATFORM_PARTY_ID,
            }
        ]

    if primary_issue == "late_delivery_seller":
        # "cac seller vi pham" -> chi seller ban giao sau shipping_limit_date,
        # khong phai moi seller cua don.
        late_ids = _list(facts, "late_handoff_seller_ids")
        parties = [
            {"party_type": taxonomy.PARTY_TYPE_SELLER, "party_id": sid} for sid in late_ids
        ]
        return limits.cap(parties, limits.MAX_RESPONSIBLE_PARTIES)

    if primary_issue == "late_delivery_logistics":
        return [
            {
                "party_type": taxonomy.PARTY_TYPE_LOGISTICS,
                "party_id": taxonomy.LOGISTICS_PARTY_ID,
            }
        ]

    # valid_split_payment va unsupported_late_claim: "Khong co" ben chiu trach nhiem.
    return []


def compute_refund(primary_issue: str, facts: FactBook) -> float:
    """Cot 'Refund' cua bang README muc 4.

    Tien lay thang tu fact da lam tron boi tang tool, khong tinh lai o day, de
    refund va payment_reconciliation khong bao gio lech nhau o chu so thap phan.
    """
    if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
        return _num(facts, "payment_total_brl")

    if primary_issue in ("late_delivery_seller", "late_delivery_logistics"):
        # "Tong freight" cua CA DON, khong phai freight cua rieng seller vi pham.
        return _num(facts, "freight_total_brl")

    return 0.0


def resolve_case_status(recommended_refund_brl: float) -> str:
    """README muc 6: action_required = can hoan tien, no_action = khong co khoan hoan."""
    return (
        taxonomy.STATUS_ACTION_REQUIRED
        if recommended_refund_brl > 0
        else taxonomy.STATUS_NO_ACTION
    )


# ---------------------------------------------------------------------------
# Resolution actions
# ---------------------------------------------------------------------------


def build_actions(primary_issue: str, secondary_issues: list[str]) -> list[str]:
    """Action chinh, roi action bo sung theo dung thu tu README muc 4.

    Doi chieu voi vi du o README muc 6:
      primary   = late_delivery_seller
      secondary = [multi_item_order, split_payment]
      ky vong   = [refund_freight, review_seller_handoff, verify_payment_allocation]

    Suy ra dieu kien kich hoat tung action bo sung:
      review_seller_handoff        <- primary la late_delivery_seller
      review_carrier_delay         <- primary la late_delivery_logistics
      verify_refund_completion     <- action chinh la issue_full_refund
                                      (vi du tren co refund 18.27 > 0 nhung KHONG co
                                       action nay, nen dieu kien khong the la refund>0)
      coordinate_multi_seller_case <- secondary co multi_seller_order
      verify_payment_allocation    <- secondary co split_payment VA primary khong phai
                                      valid_split_payment (README noi ro khong them vi
                                      action chinh da giai thich split payment)
    """
    primary_action = taxonomy.PRIMARY_ACTION_BY_ISSUE[primary_issue]
    actions = [primary_action]

    triggers = {
        "review_seller_handoff": primary_issue == "late_delivery_seller",
        "review_carrier_delay": primary_issue == "late_delivery_logistics",
        "verify_refund_completion": primary_action == "issue_full_refund",
        "coordinate_multi_seller_case": "multi_seller_order" in secondary_issues,
        "verify_payment_allocation": (
            "split_payment" in secondary_issues and primary_issue != "valid_split_payment"
        ),
    }

    for action in taxonomy.SUPPLEMENTARY_ACTION_ORDER:
        if triggers[action]:
            actions.append(action)

    return limits.cap(actions, limits.MAX_RESOLUTION_ACTIONS)


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

# Confidence khong phai so bia. No la ty le bang chung thuc su co, tren tong so
# bang chung ma luat dang ap CAN toi. Tong trong so = 1.00.
_CONFIDENCE_WEIGHTS = {
    "order_found": 0.20,
    "status_known": 0.10,
    "payment_evidence": 0.15,
    "item_reconciliation_consistent": 0.15,
    "delivery_evidence": 0.20,
    "handoff_evidence": 0.10,
    "rule_matched": 0.10,
}

# Tran 0.99: README muc 2 noi Olist khong co refund ledger, transaction ID hay
# tracking checkpoint -> khong bao gio co du bang chung de chac chan tuyet doi.
_CONFIDENCE_CEILING = 0.99
_CONFIDENCE_FLOOR = 0.05


def compute_confidence(primary_issue: str, facts: FactBook, rule_matched: bool) -> float:
    """Diem tin cay = tong trong so cac tin hieu bang chung dat duoc, kep trong [0.05, 0.99]."""
    needs_delivery = primary_issue in (
        "late_delivery_seller",
        "late_delivery_logistics",
        "unsupported_late_claim",
    )
    needs_handoff = primary_issue == "late_delivery_seller"
    has_items = int(_num(facts, "item_count")) > 0

    signals = {
        "order_found": _flag(facts, "order_found"),
        "status_known": bool(facts.get("order_status")),
        "payment_evidence": int(_num(facts, "payment_count")) > 0,
        # Co item thi phai doi soat khop; khong co item thi null la dung ky vong.
        "item_reconciliation_consistent": (
            facts.get("reconciled") is True if has_items else facts.get("reconciled") is None
        ),
        "delivery_evidence": (
            _flag(facts, "has_delivery_timestamps") if needs_delivery else True
        ),
        "handoff_evidence": (
            facts.get("carrier_handoff_at") is not None if needs_handoff else True
        ),
        "rule_matched": rule_matched,
    }

    score = sum(weight for key, weight in _CONFIDENCE_WEIGHTS.items() if signals[key])
    score = min(_CONFIDENCE_CEILING, max(_CONFIDENCE_FLOOR, score))
    return round(score, 2)


# ---------------------------------------------------------------------------
# Diem vao
# ---------------------------------------------------------------------------


def decide(facts: FactBook) -> PolicyDecision:
    """Ap toan bo EC_POLICY_V2 len mot fact book -> ket luan cho mot case."""
    verdict = classify_primary(facts)
    primary = verdict.issue
    secondary = collect_secondary(facts)
    refund = compute_refund(primary, facts)

    return PolicyDecision(
        primary_issue=primary,
        secondary_issues=secondary,
        root_cause_code=taxonomy.ROOT_CAUSE_BY_PRIMARY[primary],
        responsible_parties=resolve_responsible_parties(primary, facts),
        recommended_refund_brl=refund,
        resolution_actions=build_actions(primary, secondary),
        case_status=resolve_case_status(refund),
        confidence=compute_confidence(primary, facts, verdict.matched),
        rationale=verdict.reason,
    )


def diff_decisions(proposed: PolicyDecision, reference: PolicyDecision) -> list[str]:
    """Liet ke diem lech giua de xuat cua Policy Agent va ket qua rule engine.

    Danh sach rong = hai ben dong y. Danh sach khong rong duoc dua nguyen van vao
    prompt retry de agent tu sua, va duoc ghi vao trace.jsonl.
    """
    issues: list[str] = []
    if proposed.primary_issue != reference.primary_issue:
        issues.append(
            f"primary_issue: agent='{proposed.primary_issue}' vs rule='{reference.primary_issue}'"
        )
    if proposed.secondary_issues != reference.secondary_issues:
        issues.append(
            f"secondary_issues: agent={proposed.secondary_issues} vs rule={reference.secondary_issues}"
        )
    if proposed.root_cause_code != reference.root_cause_code:
        issues.append(
            f"root_cause_code: agent='{proposed.root_cause_code}' vs rule='{reference.root_cause_code}'"
        )
    if proposed.responsible_parties != reference.responsible_parties:
        issues.append(
            f"responsible_parties: agent={proposed.responsible_parties} "
            f"vs rule={reference.responsible_parties}"
        )
    if proposed.recommended_refund_brl != reference.recommended_refund_brl:
        issues.append(
            f"recommended_refund_brl: agent={proposed.recommended_refund_brl} "
            f"vs rule={reference.recommended_refund_brl}"
        )
    if proposed.resolution_actions != reference.resolution_actions:
        issues.append(
            f"resolution_actions: agent={proposed.resolution_actions} "
            f"vs rule={reference.resolution_actions}"
        )
    if proposed.case_status != reference.case_status:
        issues.append(
            f"case_status: agent='{proposed.case_status}' vs rule='{reference.case_status}'"
        )
    return issues


__all__ = [
    "FactBook",
    "PrimaryVerdict",
    "classify_primary",
    "collect_secondary",
    "resolve_responsible_parties",
    "compute_refund",
    "resolve_case_status",
    "build_actions",
    "compute_confidence",
    "decide",
    "diff_decisions",
]
