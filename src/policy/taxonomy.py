"""Taxonomy EC_POLICY_V2 chep nguyen tu README muc 4.

Day la BANG LUAT cua de bai, khong phai dap an cua case. Khong co case_id nao
xuat hien trong file nay.
"""

from __future__ import annotations

# --- Primary issue, theo dung THU TU UU TIEN o bang README muc 4 ------------
# Thu tu cua tuple nay chinh la thu tu xet luat. Doi thu tu = doi ket qua.
PRIMARY_ISSUE_PRIORITY: tuple[str, ...] = (
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
)

# --- Secondary issue, theo dung THU TU LIET KE 1..5 o README muc 4 ----------
SECONDARY_ISSUE_ORDER: tuple[str, ...] = (
    "multi_item_order",
    "multi_seller_order",
    "split_payment",
    "repeat_customer",
    "multiple_categories",
)

# --- Root cause code (README muc 4) ----------------------------------------
ROOT_CAUSE_BY_PRIMARY: dict[str, str] = {
    "canceled_order_paid": "ORDER_CANCELED_AFTER_PAYMENT",
    "unavailable_order_paid": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "late_delivery_seller": "SELLER_HANDOFF_AFTER_LIMIT",
    "late_delivery_logistics": "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "valid_split_payment": "MULTIPLE_PAYMENTS_RECONCILED",
    "unsupported_late_claim": "DELIVERY_WITHIN_ESTIMATE",
}

ROOT_CAUSE_CODES: tuple[str, ...] = tuple(ROOT_CAUSE_BY_PRIMARY.values())

# --- Action chinh (cot Action cua bang README muc 4) ------------------------
PRIMARY_ACTION_BY_ISSUE: dict[str, str] = {
    "canceled_order_paid": "issue_full_refund",
    "unavailable_order_paid": "issue_full_refund",
    "late_delivery_seller": "refund_freight",
    "late_delivery_logistics": "refund_freight",
    "valid_split_payment": "explain_valid_split_payment",
    "unsupported_late_claim": "reject_late_refund",
}

# --- Action bo sung, theo dung THU TU o README muc 4 ------------------------
SUPPLEMENTARY_ACTION_ORDER: tuple[str, ...] = (
    "review_seller_handoff",
    "review_carrier_delay",
    "verify_refund_completion",
    "coordinate_multi_seller_case",
    "verify_payment_allocation",
)

# --- Ben chiu trach nhiem (cot Responsible party) ---------------------------
PARTY_TYPE_PLATFORM = "platform"
PARTY_TYPE_SELLER = "seller"
PARTY_TYPE_LOGISTICS = "logistics_provider"

PLATFORM_PARTY_ID = "OLIST_PLATFORM"
LOGISTICS_PARTY_ID = "LOGISTICS_PROVIDER"

# --- case_status (README muc 6) --------------------------------------------
STATUS_ACTION_REQUIRED = "action_required"   # can hoan tien
STATUS_NO_ACTION = "no_action"               # khong co khoan hoan

CASE_STATUSES: tuple[str, ...] = (STATUS_ACTION_REQUIRED, STATUS_NO_ACTION)

# --- order_status trong Olist duoc luat nhac toi ----------------------------
ORDER_STATUS_CANCELED = "canceled"
ORDER_STATUS_UNAVAILABLE = "unavailable"

ALL_ACTIONS: tuple[str, ...] = tuple(PRIMARY_ACTION_BY_ISSUE.values()) + SUPPLEMENTARY_ACTION_ORDER


__all__ = [
    "PRIMARY_ISSUE_PRIORITY",
    "SECONDARY_ISSUE_ORDER",
    "ROOT_CAUSE_BY_PRIMARY",
    "ROOT_CAUSE_CODES",
    "PRIMARY_ACTION_BY_ISSUE",
    "SUPPLEMENTARY_ACTION_ORDER",
    "PARTY_TYPE_PLATFORM",
    "PARTY_TYPE_SELLER",
    "PARTY_TYPE_LOGISTICS",
    "PLATFORM_PARTY_ID",
    "LOGISTICS_PARTY_ID",
    "STATUS_ACTION_REQUIRED",
    "STATUS_NO_ACTION",
    "CASE_STATUSES",
    "ORDER_STATUS_CANCELED",
    "ORDER_STATUS_UNAVAILABLE",
    "ALL_ACTIONS",
]
