"""Test tren du lieu that: null handling, lam tron va 12 hard gate cho ca 50 case."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.loader import get_store
from src.numeric import hours_between, money
from src.policy import schema
from src.reference import build_reference_output, load_tickets

STORE = get_store()
TICKETS = load_tickets()
DOCS = {t.case_id: build_reference_output(t, STORE) for t in TICKETS}


# --- lam tron --------------------------------------------------------------


def test_money_lam_tron_nua_len_khong_phai_banker():
    """round() cua Python cho 2.67; nghiep vu can 2.68."""
    assert money(Decimal("2.675")) == 2.68
    assert money(Decimal("0.125")) == 0.13
    assert money(None) is None


def test_cong_tien_bang_decimal_khong_sinh_sai_so():
    assert money(Decimal("194.00") + Decimal("18.27")) == 212.27


def test_hours_between_khop_vi_du_readme():
    from datetime import datetime

    fmt = "%Y-%m-%d %H:%M:%S"
    delivered = datetime.strptime("2018-03-31 15:23:33", fmt)
    estimated = datetime.strptime("2018-03-28 00:00:00", fmt)
    assert hours_between(delivered, estimated) == 87.39

    carrier = datetime.strptime("2018-03-15 21:33:51", fmt)
    limit = datetime.strptime("2018-03-15 20:31:15", fmt)
    assert hours_between(carrier, limit) == 1.04

    assert hours_between(None, estimated) is None
    assert hours_between(delivered, None) is None


# --- bo 50 case ------------------------------------------------------------


def test_du_dung_nam_muoi_case():
    assert len(TICKETS) == 50
    assert [t.case_id for t in TICKETS] == [f"EC_{i:03d}" for i in range(1, 51)]


@pytest.mark.parametrize("case_id", sorted(DOCS))
def test_moi_case_qua_het_hard_gate(case_id):
    ticket = next(t for t in TICKETS if t.case_id == case_id)
    violations = schema.validate_output(DOCS[case_id], case_id, ticket.claimed_order_id, STORE)
    assert violations == [], "\n".join(str(v) for v in violations)


@pytest.mark.parametrize("case_id", sorted(DOCS))
def test_related_orders_khong_chua_don_dang_khieu_nai(case_id):
    ticket = next(t for t in TICKETS if t.case_id == case_id)
    assert ticket.claimed_order_id not in DOCS[case_id]["customer_context"]["related_order_ids"]


@pytest.mark.parametrize("case_id", sorted(DOCS))
def test_product_ids_khong_trung_lap(case_id):
    """21/50 case co nhieu item tro ve cung mot product -> phai dedup."""
    ids = DOCS[case_id]["product_context"]["product_ids"]
    assert len(ids) == len(set(ids))


def test_quy_tac_null_cho_order_khong_co_item_row():
    empty = [
        cid
        for cid, doc in DOCS.items()
        if not STORE.items_by_order.get(
            next(t.claimed_order_id for t in TICKETS if t.case_id == cid), []
        )
    ]
    assert empty, "Bo de phai co it nhat mot order khong co item row"
    for case_id in empty:
        recon = DOCS[case_id]["payment_reconciliation"]
        assert recon["expected_total_brl"] is None
        assert recon["difference_brl"] is None
        assert recon["reconciled"] is None
        assert DOCS[case_id]["affected_entities"]["item_ids"] == []
        assert DOCS[case_id]["affected_entities"]["seller_ids"] == []
        assert DOCS[case_id]["product_context"]["product_ids"] == []
        assert DOCS[case_id]["product_context"]["category_names"] == []
        assert DOCS[case_id]["delivery_analysis"]["seller_handoff_analysis"] == []


def test_quy_tac_null_cho_don_chua_giao():
    for ticket in TICKETS:
        order = STORE.orders[ticket.claimed_order_id]
        if order.delivered_customer_at is None:
            assert DOCS[ticket.case_id]["delivery_analysis"]["delivery_variance_hours"] is None


def test_ec_002_khop_tung_con_so_cua_vi_du_readme():
    """Vi du o README muc 6 chinh la EC_002. Day la ground truth doc lap."""
    doc = DOCS["EC_002"]
    delivery = doc["delivery_analysis"]
    assert delivery["delivered_at"] == "2018-03-31 15:23:33"
    assert delivery["estimated_delivery_at"] == "2018-03-28 00:00:00"
    assert delivery["carrier_handoff_at"] == "2018-03-15 21:33:51"
    assert delivery["delivery_variance_hours"] == 87.39
    assert delivery["seller_handoff_analysis"][0]["shipping_limit_at"] == "2018-03-15 20:31:15"
    assert delivery["seller_handoff_analysis"][0]["handoff_variance_hours"] == 1.04
    assert delivery["seller_handoff_analysis"][0]["late_handoff"] is True

    recon = doc["payment_reconciliation"]
    assert recon["item_total_brl"] == 194.0
    assert recon["freight_total_brl"] == 18.27
    assert recon["expected_total_brl"] == 212.27
    assert recon["payment_total_brl"] == 212.27
    assert recon["difference_brl"] == 0.0
    assert recon["reconciled"] is True
    assert recon["payment_types"] == ["credit_card", "voucher"]

    assert doc["case_assessment"]["primary_issue"] == "late_delivery_seller"
    assert doc["root_cause_analysis"]["ranked_causes"] == [
        {"cause_code": "SELLER_HANDOFF_AFTER_LIMIT", "rank": 1}
    ]
    assert doc["financial_resolution"]["recommended_refund_brl"] == 18.27
    assert doc["resolution_actions"] == [
        "refund_freight",
        "review_seller_handoff",
        "verify_payment_allocation",
    ]


# --- phan quyen ------------------------------------------------------------


def test_agent_khong_goi_duoc_tool_ngoai_quyen():
    from src.tools.registry import ToolAccessError, call_tool

    bundle = STORE.build_bundle(TICKETS[0].claimed_order_id)
    with pytest.raises(ToolAccessError):
        call_tool("policy_agent", "get_order_header", bundle)
    with pytest.raises(ToolAccessError):
        call_tool("customer_agent", "reconcile_payments", bundle)


def test_moi_model_deu_duoi_muoi_ty_tham_so():
    from src import config

    for model in config.MODEL_REGISTRY.values():
        assert model.parameter_size_b <= config.MAX_PARAMETER_SIZE_B
