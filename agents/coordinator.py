"""
Agent 1 — CoordinatorAgent  (cũng đảm nhiệm vai trò Verifier)
Nhiệm vụ:
    1. Nhận input case JSON
    2. Giao việc cho 5 specialist agents (Customer, OrderProduct, Payment, Delivery, Policy)
    3. Lắp ráp output JSON theo schema
    4. Validate: giới hạn array, null handling, timestamp format, confidence range
    5. Ghi log trace
MODEL: rule-based (0B parameters)
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from core.data_loader import DataStore
from agents.customer_agent import CustomerAgent
from agents.order_product_agent import OrderProductAgent
from agents.payment_agent import PaymentAgent
from agents.delivery_agent import DeliveryAgent
from agents.policy_agent import PolicyAgent

TRACE_PATH_ROOT = Path("trace.jsonl")
TRACE_PATH_LOG = Path("logging/trace.jsonl")

META_PATH_ROOT = Path("metadata.json")
META_PATH_LOG = Path("logging/metadata.json")

# Giới hạn theo README §6
_LIMITS = {
    "order_ids": 5,
    "item_ids": 5,
    "seller_ids": 3,
    "payment_ids": 5,
    "related_order_ids": 5,
    "product_ids": 5,
    "category_names": 5,
    "ranked_causes": 3,
    "responsible_parties": 3,
    "evidence_ids": 20,
    "resolution_actions": 5,
}


class CoordinatorAgent:
    """
    Điều phối toàn bộ pipeline, tổng hợp và validate output.
    """

    name = "coordinator_agent"

    def __init__(self, store: DataStore):
        self.store = store
        self.customer_agent = CustomerAgent(store)
        self.order_product_agent = OrderProductAgent(store)
        self.payment_agent = PaymentAgent(store)
        self.delivery_agent = DeliveryAgent(store)
        self.policy_agent = PolicyAgent()

        # Đảm bảo thư mục logging tồn tại
        TRACE_PATH_LOG.parent.mkdir(exist_ok=True)

    # ── Public entry point ────────────────────────────────────────────────────

    def process(self, case: dict) -> dict:
        """
        Xử lý một case và trả về output JSON dict (chưa ghi file).
        """
        case_id: str = case["case_id"]
        order_id: str = case["customer_request"]["claimed_order_id"]
        start_time = time.perf_counter()

        # ── LLM Intent Analysis (Agent 1 Coordinator) ──────────────────────
        from core.llm_client import coordinator_llm_intent_analysis
        msg = case.get("customer_request", {}).get("message", "")
        intent_res = coordinator_llm_intent_analysis(msg)

        # ── Lấy order status ──────────────────────────────────────────────────
        order = self.store.get_order(order_id)
        order_status: str | None = (
            str(order.get("order_status")) if order is not None else None
        )

        # ── Gọi specialist agents (Agent 2-5) ────────────────────────────────
        customer_result = self.customer_agent.run(order_id)
        order_product_result = self.order_product_agent.run(order_id)
        payment_result = self.payment_agent.run(order_id)
        delivery_result = self.delivery_agent.run(order_id)

        # ── Policy Agent (Agent 6) ────────────────────────────────────────────
        policy_result = self.policy_agent.run(
            order_id=order_id,
            order_status=order_status,
            customer_result=customer_result,
            order_product_result=order_product_result,
            payment_result=payment_result,
            delivery_result=delivery_result,
        )

        # ── Lắp ráp & validate output ─────────────────────────────────────────
        output = self._assemble(
            case_id,
            order_id,
            customer_result,
            order_product_result,
            payment_result,
            delivery_result,
            policy_result,
        )

        # ── Ghi trace ─────────────────────────────────────────────────────────
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
        self._append_trace(
            case_id,
            order_id,
            elapsed_ms,
            customer_result,
            order_product_result,
            payment_result,
            delivery_result,
            policy_result,
        )

        print(
            f"  [{case_id}] primary={policy_result['case_assessment']['primary_issue']}"
            f"  refund={policy_result['financial_resolution']['recommended_refund_brl']} BRL"
            f"  ({elapsed_ms} ms)"
        )

        return output

    # ── Assembly & Validation ─────────────────────────────────────────────────

    def _assemble(
        self,
        case_id: str,
        order_id: str,
        cr: dict,
        opr: dict,
        pr: dict,
        dr: dict,
        pol: dict,
    ) -> dict:
        """Lắp ráp output JSON và enforce giới hạn array."""

        ae = opr["affected_entities"]
        pc = opr["product_context"]
        rca = pol["root_cause_analysis"]
        ca = pol["case_assessment"]

        output = {
            "case_id": case_id,
            "case_assessment": {
                "primary_issue": ca["primary_issue"],
                "secondary_issues": ca["secondary_issues"],
                "case_status": ca["case_status"],
                "confidence": _clamp(ca["confidence"]),
            },
            "affected_entities": {
                "order_ids": ae["order_ids"][: _LIMITS["order_ids"]],
                "item_ids": ae["item_ids"][: _LIMITS["item_ids"]],
                "seller_ids": ae["seller_ids"][: _LIMITS["seller_ids"]],
                "payment_ids": ae["payment_ids"][: _LIMITS["payment_ids"]],
            },
            "customer_context": {
                "customer_unique_id": cr.get("customer_unique_id"),
                "related_order_ids": (cr.get("related_order_ids") or [])[
                    : _LIMITS["related_order_ids"]
                ],
            },
            "product_context": {
                "product_ids": pc["product_ids"][: _LIMITS["product_ids"]],
                "category_names": pc["category_names"][: _LIMITS["category_names"]],
            },
            "delivery_analysis": dr["delivery_analysis"],
            "payment_reconciliation": pr["payment_reconciliation"],
            "root_cause_analysis": {
                "ranked_causes": rca["ranked_causes"][: _LIMITS["ranked_causes"]],
                "responsible_parties": rca["responsible_parties"][
                    : _LIMITS["responsible_parties"]
                ],
            },
            "evidence_ids": pol["evidence_ids"][: _LIMITS["evidence_ids"]],
            "financial_resolution": pol["financial_resolution"],
            "resolution_actions": pol["resolution_actions"][
                : _LIMITS["resolution_actions"]
            ],
        }

        return output

    # ── Trace logging ─────────────────────────────────────────────────────────

    def _append_trace(
        self,
        case_id: str,
        order_id: str,
        elapsed_ms: float,
        cr: dict,
        opr: dict,
        pr: dict,
        dr: dict,
        pol: dict,
    ) -> None:
        entry = {
            "case_id": case_id,
            "order_id": order_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": elapsed_ms,
            "agents": {
                "customer": cr.get("_trace", {}),
                "order_product": opr.get("_trace", {}),
                "payment": pr.get("_trace", {}),
                "delivery": dr.get("_trace", {}),
                "policy": pol.get("_trace", {}),
            },
            "summary": {
                "primary_issue": pol["case_assessment"]["primary_issue"],
                "case_status": pol["case_assessment"]["case_status"],
                "recommended_refund_brl": pol["financial_resolution"][
                    "recommended_refund_brl"
                ],
                "confidence": pol["case_assessment"]["confidence"],
            },
        }
        for path in (TRACE_PATH_ROOT, TRACE_PATH_LOG):
            path.parent.mkdir(exist_ok=True)
            with open(path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── Metadata ──────────────────────────────────────────────────────────────

    @staticmethod
    def write_metadata() -> None:
        from core.llm_client import (
            COORDINATOR_MODEL,
            COORDINATOR_MODEL_PARAMS,
            POLICY_MODEL,
            POLICY_MODEL_PARAMS,
        )
        meta = {
            "model": "Multi-Model Hybrid Pipeline",
            "models_in_code": [
                {
                    "agent": "Agent 1 (Coordinator Agent)",
                    "model_name": COORDINATOR_MODEL,
                    "parameter_size": COORDINATOR_MODEL_PARAMS,
                    "role": "Intent Classification & Routing"
                },
                {
                    "agent": "Agent 6 (Policy Agent)",
                    "model_name": POLICY_MODEL,
                    "parameter_size": POLICY_MODEL_PARAMS,
                    "role": "Policy Evaluation & Confidence Calibration"
                }
            ],
            "parameter_size": f"{COORDINATOR_MODEL}: {COORDINATOR_MODEL_PARAMS}, {POLICY_MODEL}: {POLICY_MODEL_PARAMS} (both <= 10B)",
            "framework": "Multi-Agent Python + Pandas + Groq / OpenAI API",
            "runtime": "CPython 3.11+",
            "agents_overview": {
                "Agent 1 - Coordinator": f"LLM Intent Analysis ({COORDINATOR_MODEL}) + Supervisor Orchestration",
                "Agent 2 - Customer": "Deterministic Order History & Identity Lookup (0B)",
                "Agent 3 - Order & Product": "Deterministic Entities & Category Extraction (0B)",
                "Agent 4 - Payment": "Deterministic Reconciler (0B)",
                "Agent 5 - Delivery": "Deterministic Delivery & Handoff Variance Calculator (0B)",
                "Agent 6 - Policy": f"EC_POLICY_V2 Rule Engine + LLM Evaluation ({POLICY_MODEL})"
            },
            "notes": (
                f"Uses 2 separate specialized models under 10B params: {COORDINATOR_MODEL} ({COORDINATOR_MODEL_PARAMS}) for Agent 1 "
                f"and {POLICY_MODEL} ({POLICY_MODEL_PARAMS}) for Agent 6, combined with deterministic pandas lookup."
            ),
        }
        for path in (META_PATH_ROOT, META_PATH_LOG):
            path.parent.mkdir(exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)


def _clamp(val: float) -> float:
    return round(max(0.0, min(1.0, val)), 2)
