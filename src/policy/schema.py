"""Hard gate: 12 nhom kiem tra chay truoc khi ghi file.

De bai noi "Case bi hard gate nhan 0 diem". Cho mat diem nhieu nhat khong phai
suy luan sai ma la sai format, sai null, ID khong ton tai hay vuot tran mang.
Toan bo nhung thu do bi chan tai day.

Verifier Agent goi module nay. Ket qua cua no la QUYET DINH, con phan LLM cua
Verifier chi bo sung nhan xet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from src.loader import TIMESTAMP_FORMAT, OlistStore
from src.policy import limits, taxonomy

TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

EVIDENCE_PATTERNS = {
    "order": re.compile(r"^order:([0-9a-f]{32})$"),
    "item": re.compile(r"^item:([0-9a-f]{32}):(\d+)$"),
    "payment": re.compile(r"^payment:([0-9a-f]{32}):(\d+)$"),
    "seller": re.compile(r"^seller:([0-9a-f]{32})$"),
    "policy": re.compile(r"^policy:([A-Z_]+)$"),
}


@dataclass
class Violation:
    gate: str
    field_path: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.gate}] {self.field_path}: {self.detail}"


class _Checker:
    def __init__(self, doc: dict, case_id: str, order_id: str, store: OlistStore) -> None:
        self.doc = doc
        self.case_id = case_id
        self.order_id = order_id
        self.store = store
        self.v: list[Violation] = []

    def fail(self, gate: str, path: str, detail: str) -> None:
        self.v.append(Violation(gate, path, detail))

    # -- helper --------------------------------------------------------------

    def get(self, path: str) -> Any:
        node: Any = self.doc
        for part in path.split("."):
            if not isinstance(node, dict):
                return None
            node = node.get(part)
        return node

    def _is_2dp(self, value: float) -> bool:
        try:
            exponent = Decimal(str(value)).as_tuple().exponent
        except InvalidOperation:
            return False
        return isinstance(exponent, int) and exponent >= -2

    # -- G1: case_id ---------------------------------------------------------

    def gate_case_id(self) -> None:
        if self.doc.get("case_id") != self.case_id:
            self.fail("G1_case_id", "case_id", f"ky vong '{self.case_id}', nhan '{self.doc.get('case_id')}'")

    # -- G2: cau truc va kieu du lieu ----------------------------------------

    def gate_structure(self) -> None:
        required: dict[str, type | tuple[type, ...]] = {
            "case_assessment": dict,
            "case_assessment.primary_issue": str,
            "case_assessment.secondary_issues": list,
            "case_assessment.case_status": str,
            "case_assessment.confidence": (int, float),
            "affected_entities": dict,
            "affected_entities.order_ids": list,
            "affected_entities.item_ids": list,
            "affected_entities.seller_ids": list,
            "affected_entities.payment_ids": list,
            "customer_context": dict,
            "customer_context.related_order_ids": list,
            "product_context": dict,
            "product_context.product_ids": list,
            "product_context.category_names": list,
            "delivery_analysis": dict,
            "delivery_analysis.seller_handoff_analysis": list,
            "delivery_analysis.late_handoff_seller_ids": list,
            "payment_reconciliation": dict,
            "payment_reconciliation.currency": str,
            "payment_reconciliation.payment_types": list,
            "root_cause_analysis": dict,
            "root_cause_analysis.ranked_causes": list,
            "root_cause_analysis.responsible_parties": list,
            "evidence_ids": list,
            "financial_resolution": dict,
            "financial_resolution.currency": str,
            "financial_resolution.recommended_refund_brl": (int, float),
            "resolution_actions": list,
        }
        for path, expected in required.items():
            value = self.get(path)
            if value is None:
                self.fail("G2_structure", path, "thieu key bat buoc")
            elif not isinstance(value, expected):
                self.fail(
                    "G2_structure", path, f"sai kieu, ky vong {expected}, nhan {type(value).__name__}"
                )

        # customer_unique_id duoc phep null nhung key phai ton tai.
        if "customer_unique_id" not in (self.doc.get("customer_context") or {}):
            self.fail("G2_structure", "customer_context.customer_unique_id", "thieu key bat buoc")

    # -- G3 + G4: evidence dung dinh dang VA ton tai that --------------------

    def gate_evidence(self) -> None:
        for evidence_id in self.doc.get("evidence_ids") or []:
            if not isinstance(evidence_id, str):
                self.fail("G3_evidence_format", "evidence_ids", f"khong phai chuoi: {evidence_id!r}")
                continue

            kind = evidence_id.split(":", 1)[0]
            pattern = EVIDENCE_PATTERNS.get(kind)
            if pattern is None:
                self.fail("G3_evidence_format", "evidence_ids", f"tien to la: {evidence_id}")
                continue

            match = pattern.match(evidence_id)
            if match is None:
                self.fail("G3_evidence_format", "evidence_ids", f"sai dinh dang: {evidence_id}")
                continue

            if kind == "order":
                if match.group(1) not in self.store.orders:
                    self.fail("G4_evidence_exists", "evidence_ids", f"order khong co trong CSV: {evidence_id}")
            elif kind == "item":
                rows = self.store.items_by_order.get(match.group(1), [])
                if not any(r.order_item_id == int(match.group(2)) for r in rows):
                    self.fail("G4_evidence_exists", "evidence_ids", f"item khong co trong CSV: {evidence_id}")
            elif kind == "payment":
                rows = self.store.payments_by_order.get(match.group(1), [])
                if not any(r.payment_sequential == int(match.group(2)) for r in rows):
                    self.fail("G4_evidence_exists", "evidence_ids", f"payment khong co trong CSV: {evidence_id}")
            elif kind == "seller":
                if match.group(1) not in self.store.sellers:
                    self.fail("G4_evidence_exists", "evidence_ids", f"seller khong co trong CSV: {evidence_id}")
            elif kind == "policy":
                if match.group(1) not in taxonomy.ROOT_CAUSE_CODES:
                    self.fail("G4_evidence_exists", "evidence_ids", f"root cause code la: {evidence_id}")

    # -- G5: moi ID trong output truy nguoc duoc ve CSV ----------------------

    def gate_entity_ids(self) -> None:
        for oid in self.get("affected_entities.order_ids") or []:
            if oid not in self.store.orders:
                self.fail("G5_entity_exists", "affected_entities.order_ids", f"order la: {oid}")

        for item_key in self.get("affected_entities.item_ids") or []:
            parts = str(item_key).split(":")
            ok = len(parts) == 2 and any(
                r.order_item_id == int(parts[1])
                for r in self.store.items_by_order.get(parts[0], [])
                if parts[1].isdigit()
            )
            if not ok:
                self.fail("G5_entity_exists", "affected_entities.item_ids", f"item la: {item_key}")

        for pay_key in self.get("affected_entities.payment_ids") or []:
            parts = str(pay_key).split(":")
            ok = len(parts) == 2 and any(
                r.payment_sequential == int(parts[1])
                for r in self.store.payments_by_order.get(parts[0], [])
                if parts[1].isdigit()
            )
            if not ok:
                self.fail("G5_entity_exists", "affected_entities.payment_ids", f"payment la: {pay_key}")

        for sid in self.get("affected_entities.seller_ids") or []:
            if sid not in self.store.sellers:
                self.fail("G5_entity_exists", "affected_entities.seller_ids", f"seller la: {sid}")

        for sid in self.get("delivery_analysis.late_handoff_seller_ids") or []:
            if sid not in self.store.sellers:
                self.fail("G5_entity_exists", "delivery_analysis.late_handoff_seller_ids", f"seller la: {sid}")

        for pid in self.get("product_context.product_ids") or []:
            if pid not in self.store.products:
                self.fail("G5_entity_exists", "product_context.product_ids", f"product la: {pid}")

        for oid in self.get("customer_context.related_order_ids") or []:
            if oid not in self.store.orders:
                self.fail("G5_entity_exists", "customer_context.related_order_ids", f"order la: {oid}")

    # -- G6: tran do dai mang ------------------------------------------------

    def gate_limits(self) -> None:
        for path, limit in limits.FIELD_LIMITS.items():
            value = self.get(path)
            if isinstance(value, list) and len(value) > limit:
                self.fail("G6_array_limit", path, f"co {len(value)} phan tu, tran la {limit}")

    # -- G7: confidence trong [0, 1] -----------------------------------------

    def gate_confidence(self) -> None:
        confidence = self.get("case_assessment.confidence")
        if isinstance(confidence, (int, float)) and not 0.0 <= float(confidence) <= 1.0:
            self.fail("G7_confidence_range", "case_assessment.confidence", f"ngoai [0,1]: {confidence}")

    # -- G8: dinh dang timestamp ---------------------------------------------

    def gate_timestamps(self) -> None:
        for field_name in ("delivered_at", "estimated_delivery_at", "carrier_handoff_at"):
            value = self.get(f"delivery_analysis.{field_name}")
            if value is None:
                continue
            if not isinstance(value, str) or not TIMESTAMP_RE.match(value):
                self.fail(
                    "G8_timestamp_format",
                    f"delivery_analysis.{field_name}",
                    f"phai la '{TIMESTAMP_FORMAT}' hoac null, nhan {value!r}",
                )

        for idx, entry in enumerate(self.get("delivery_analysis.seller_handoff_analysis") or []):
            value = (entry or {}).get("shipping_limit_at")
            if value is None:
                continue
            if not isinstance(value, str) or not TIMESTAMP_RE.match(value):
                self.fail(
                    "G8_timestamp_format",
                    f"delivery_analysis.seller_handoff_analysis[{idx}].shipping_limit_at",
                    f"sai dinh dang: {value!r}",
                )

    # -- G9: quy tac null ----------------------------------------------------

    def gate_null_rules(self) -> None:
        bundle_items = self.store.items_by_order.get(self.order_id, [])
        recon = self.doc.get("payment_reconciliation") or {}

        if not bundle_items:
            # README muc 4: order khong co item row.
            for field_name in ("expected_total_brl", "difference_brl", "reconciled"):
                if recon.get(field_name) is not None:
                    self.fail(
                        "G9_null_rule",
                        f"payment_reconciliation.{field_name}",
                        f"order khong co item row -> phai la null, nhan {recon.get(field_name)!r}",
                    )
            empty_paths = [
                "affected_entities.item_ids",
                "affected_entities.seller_ids",
                "product_context.product_ids",
                "product_context.category_names",
                "delivery_analysis.seller_handoff_analysis",
            ]
            for path in empty_paths:
                value = self.get(path)
                if isinstance(value, list) and value:
                    self.fail("G9_null_rule", path, "order khong co item row -> phai la mang rong")
        else:
            for field_name in ("expected_total_brl", "difference_brl"):
                if recon.get(field_name) is None:
                    self.fail(
                        "G9_null_rule",
                        f"payment_reconciliation.{field_name}",
                        "order co item row -> khong duoc null",
                    )
            if recon.get("reconciled") is None:
                self.fail("G9_null_rule", "payment_reconciliation.reconciled", "order co item row -> khong duoc null")

        # Khong co ngay giao thuc te -> delivery_variance_hours phai null.
        order = self.store.orders.get(self.order_id)
        if order is not None and order.delivered_customer_at is None:
            if self.get("delivery_analysis.delivery_variance_hours") is not None:
                self.fail(
                    "G9_null_rule",
                    "delivery_analysis.delivery_variance_hours",
                    "khong co order_delivered_customer_date -> phai la null",
                )

    # -- G10: enum + nhat quan case_status -----------------------------------

    def gate_enums(self) -> None:
        primary = self.get("case_assessment.primary_issue")
        if primary not in taxonomy.PRIMARY_ISSUE_PRIORITY:
            self.fail("G10_enum", "case_assessment.primary_issue", f"ngoai danh muc: {primary!r}")

        secondary = self.get("case_assessment.secondary_issues") or []
        for name in secondary:
            if name not in taxonomy.SECONDARY_ISSUE_ORDER:
                self.fail("G10_enum", "case_assessment.secondary_issues", f"ngoai danh muc: {name!r}")
        expected_order = [n for n in taxonomy.SECONDARY_ISSUE_ORDER if n in secondary]
        if list(secondary) != expected_order:
            self.fail(
                "G10_enum",
                "case_assessment.secondary_issues",
                f"sai thu tu nghiep vu, ky vong {expected_order}, nhan {list(secondary)}",
            )

        status = self.get("case_assessment.case_status")
        if status not in taxonomy.CASE_STATUSES:
            self.fail("G10_enum", "case_assessment.case_status", f"ngoai danh muc: {status!r}")

        for action in self.get("resolution_actions") or []:
            if action not in taxonomy.ALL_ACTIONS:
                self.fail("G10_enum", "resolution_actions", f"ngoai danh muc: {action!r}")

        for cause in self.get("root_cause_analysis.ranked_causes") or []:
            if (cause or {}).get("cause_code") not in taxonomy.ROOT_CAUSE_CODES:
                self.fail("G10_enum", "root_cause_analysis.ranked_causes", f"cause code la: {cause!r}")

        refund = self.get("financial_resolution.recommended_refund_brl")
        if isinstance(refund, (int, float)) and status in taxonomy.CASE_STATUSES:
            expected_status = (
                taxonomy.STATUS_ACTION_REQUIRED if refund > 0 else taxonomy.STATUS_NO_ACTION
            )
            if status != expected_status:
                self.fail(
                    "G10_enum",
                    "case_assessment.case_status",
                    f"refund={refund} nen phai la '{expected_status}', nhan '{status}'",
                )

    # -- G11: related_order_ids khong chua chinh order dang khieu nai --------

    def gate_related_orders(self) -> None:
        related = self.get("customer_context.related_order_ids") or []
        if self.order_id in related:
            self.fail(
                "G11_related_orders",
                "customer_context.related_order_ids",
                "khong duoc chua claimed_order_id (README muc 3)",
            )
        if len(set(related)) != len(related):
            self.fail("G11_related_orders", "customer_context.related_order_ids", "co phan tu trung lap")

    # -- G12: lam tron 2 chu so ----------------------------------------------

    def gate_rounding(self) -> None:
        numeric_paths = [
            "delivery_analysis.delivery_variance_hours",
            "payment_reconciliation.item_total_brl",
            "payment_reconciliation.freight_total_brl",
            "payment_reconciliation.expected_total_brl",
            "payment_reconciliation.payment_total_brl",
            "payment_reconciliation.difference_brl",
            "financial_resolution.recommended_refund_brl",
        ]
        for path in numeric_paths:
            value = self.get(path)
            if isinstance(value, (int, float)) and not self._is_2dp(value):
                self.fail("G12_rounding", path, f"qua 2 chu so thap phan: {value!r}")

        for idx, entry in enumerate(self.get("delivery_analysis.seller_handoff_analysis") or []):
            value = (entry or {}).get("handoff_variance_hours")
            if isinstance(value, (int, float)) and not self._is_2dp(value):
                self.fail(
                    "G12_rounding",
                    f"delivery_analysis.seller_handoff_analysis[{idx}].handoff_variance_hours",
                    f"qua 2 chu so thap phan: {value!r}",
                )

    # -- chay het ------------------------------------------------------------

    def run(self) -> list[Violation]:
        self.gate_case_id()
        self.gate_structure()
        # Cac gate sau doc sau vao cau truc; chi chay khi cau truc con nguyen.
        if not any(x.gate == "G2_structure" for x in self.v):
            self.gate_evidence()
            self.gate_entity_ids()
            self.gate_limits()
            self.gate_confidence()
            self.gate_timestamps()
            self.gate_null_rules()
            self.gate_enums()
            self.gate_related_orders()
            self.gate_rounding()
        return self.v


def validate_output(doc: dict, case_id: str, order_id: str, store: OlistStore) -> list[Violation]:
    """Chay 12 nhom hard gate. Danh sach rong = duoc phep ghi file."""
    return _Checker(doc, case_id, order_id, store).run()


__all__ = ["Violation", "validate_output", "EVIDENCE_PATTERNS", "TIMESTAMP_RE"]
