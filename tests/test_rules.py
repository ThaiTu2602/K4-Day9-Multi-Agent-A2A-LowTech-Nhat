"""Unit test cho rule engine EC_POLICY_V2.

Test dung fact book dung tay, khong cham vao CSV, de kiem tra rieng phan luat.
"""

from __future__ import annotations

import pytest

from src.policy import taxonomy
from src.policy.rules import build_actions, classify_primary, collect_secondary, decide


def base_facts(**overrides):
    facts = {
        "order_found": True,
        "order_status": "delivered",
        "item_count": 1,
        "seller_count": 1,
        "payment_count": 1,
        "related_order_count": 0,
        "distinct_category_count": 1,
        "payment_total_brl": 100.0,
        "freight_total_brl": 10.0,
        "item_total_brl": 90.0,
        "expected_total_brl": 100.0,
        "difference_brl": 0.0,
        "reconciled": True,
        "delivery_variance_hours": -10.0,
        "is_delivered_late": False,
        "has_late_handoff_seller": False,
        "late_handoff_seller_ids": [],
        "carrier_handoff_at": "2018-01-01 00:00:00",
        "has_delivery_timestamps": True,
    }
    facts.update(overrides)
    return facts


# --- thu tu uu tien --------------------------------------------------------


def test_canceled_thang_moi_luat_khac():
    facts = base_facts(
        order_status="canceled", is_delivered_late=True, has_late_handoff_seller=True
    )
    assert classify_primary(facts).issue == "canceled_order_paid"


def test_canceled_khong_tinh_khi_payment_bang_khong():
    facts = base_facts(order_status="canceled", payment_total_brl=0.0)
    assert classify_primary(facts).issue != "canceled_order_paid"


def test_late_delivery_thang_valid_split_payment():
    """Don giao tre CO 2 payment row thoa ca hai luat; luat 3 dung truoc nen thang."""
    facts = base_facts(
        is_delivered_late=True,
        has_late_handoff_seller=True,
        delivery_variance_hours=50.0,
        payment_count=2,
    )
    assert classify_primary(facts).issue == "late_delivery_seller"


def test_late_seller_va_late_logistics_phan_biet_boi_handoff():
    late = base_facts(is_delivered_late=True, delivery_variance_hours=50.0)
    assert classify_primary({**late, "has_late_handoff_seller": True}).issue == "late_delivery_seller"
    assert classify_primary({**late, "has_late_handoff_seller": False}).issue == "late_delivery_logistics"


def test_valid_split_payment_can_du_hai_dieu_kien():
    assert classify_primary(base_facts(payment_count=2)).issue == "valid_split_payment"
    assert classify_primary(base_facts(payment_count=1)).issue == "unsupported_late_claim"


def test_moi_primary_issue_deu_co_root_cause():
    for issue in taxonomy.PRIMARY_ISSUE_PRIORITY:
        assert issue in taxonomy.ROOT_CAUSE_BY_PRIMARY
        assert issue in taxonomy.PRIMARY_ACTION_BY_ISSUE


# --- secondary issue -------------------------------------------------------


def test_secondary_giu_dung_thu_tu_nghiep_vu():
    facts = base_facts(
        item_count=3, seller_count=2, payment_count=2, related_order_count=1,
        distinct_category_count=2,
    )
    assert collect_secondary(facts) == list(taxonomy.SECONDARY_ISSUE_ORDER)


def test_repeat_customer_kich_hoat_khi_co_dung_mot_don_khac():
    assert collect_secondary(base_facts(related_order_count=1)) == ["repeat_customer"]
    assert collect_secondary(base_facts(related_order_count=0)) == []


def test_secondary_rong_khi_khong_dieu_kien_nao_thoa():
    assert collect_secondary(base_facts()) == []


# --- action ----------------------------------------------------------------


def test_action_khop_vi_du_readme_muc_6():
    """README muc 6 la case late_delivery_seller co split_payment."""
    assert build_actions("late_delivery_seller", ["multi_item_order", "split_payment"]) == [
        "refund_freight",
        "review_seller_handoff",
        "verify_payment_allocation",
    ]


def test_khong_them_verify_payment_allocation_cho_valid_split_payment():
    actions = build_actions("valid_split_payment", ["split_payment"])
    assert "verify_payment_allocation" not in actions
    assert actions == ["explain_valid_split_payment"]


def test_full_refund_keo_theo_verify_refund_completion():
    assert build_actions("canceled_order_paid", []) == [
        "issue_full_refund",
        "verify_refund_completion",
    ]


def test_multi_seller_keo_theo_coordinate():
    actions = build_actions("late_delivery_logistics", ["multi_seller_order"])
    assert actions == ["refund_freight", "review_carrier_delay", "coordinate_multi_seller_case"]


def test_action_khong_bao_gio_vuot_nam():
    actions = build_actions("late_delivery_seller", list(taxonomy.SECONDARY_ISSUE_ORDER))
    assert len(actions) <= 5


# --- refund va trach nhiem -------------------------------------------------


def test_refund_va_trach_nhiem_theo_tung_luat():
    canceled = decide(base_facts(order_status="canceled"))
    assert canceled.recommended_refund_brl == 100.0
    assert canceled.responsible_parties == [
        {"party_type": "platform", "party_id": "OLIST_PLATFORM"}
    ]
    assert canceled.case_status == "action_required"

    logistics = decide(base_facts(is_delivered_late=True, delivery_variance_hours=5.0))
    assert logistics.recommended_refund_brl == 10.0  # tong freight, khong phai tong payment
    assert logistics.responsible_parties == [
        {"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}
    ]

    seller = decide(
        base_facts(
            is_delivered_late=True,
            delivery_variance_hours=5.0,
            has_late_handoff_seller=True,
            late_handoff_seller_ids=["s1", "s2"],
        )
    )
    assert seller.responsible_parties == [
        {"party_type": "seller", "party_id": "s1"},
        {"party_type": "seller", "party_id": "s2"},
    ]

    no_fault = decide(base_facts())
    assert no_fault.recommended_refund_brl == 0.0
    assert no_fault.responsible_parties == []
    assert no_fault.case_status == "no_action"


def test_case_status_luon_nhat_quan_voi_refund():
    for facts in (
        base_facts(order_status="canceled"),
        base_facts(order_status="unavailable"),
        base_facts(is_delivered_late=True, delivery_variance_hours=5.0),
        base_facts(payment_count=2),
        base_facts(),
    ):
        decision = decide(facts)
        expected = "action_required" if decision.recommended_refund_brl > 0 else "no_action"
        assert decision.case_status == expected


def test_confidence_luon_trong_khoang_hop_le():
    for facts in (base_facts(), base_facts(order_found=False, order_status=None)):
        assert 0.0 <= decide(facts).confidence <= 1.0


@pytest.mark.parametrize("issue", taxonomy.PRIMARY_ISSUE_PRIORITY)
def test_root_cause_code_nam_trong_danh_muc(issue):
    assert taxonomy.ROOT_CAUSE_BY_PRIMARY[issue] in taxonomy.ROOT_CAUSE_CODES
