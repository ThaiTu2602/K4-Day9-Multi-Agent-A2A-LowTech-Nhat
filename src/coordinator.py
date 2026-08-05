"""Coordinator: runs one case through the agent pipeline and writes an
A2A-style trace line per handoff.

Numbers and taxonomy decisions come only from the deterministic agent
modules (customer/order_product/payment/delivery/policy/verifier). The
Groq-hosted model (llama-3.1-8b-instant, see src/llm_client.py) is used
strictly to narrate each handoff in natural language for the trace -- it
never touches a number or a decision, so a bad LLM sample cannot corrupt
graded output.
"""

from __future__ import annotations

import datetime as dt

from src.agents import customer_agent, delivery_agent, order_product_agent, payment_agent, policy_agent, verifier_agent
from src.data_layer import OlistData
from src.llm_client import LLMUnavailableError, MODEL_NAME, chat
from src.schema import build_output

NARRATION_SYSTEM_PROMPT = (
    "Ban la mot agent dieu tra khieu nai thuong mai dien tu. "
    "Viet 1 cau tieng Viet ngan gon (<=30 tu), khach quan, chi dua tren du lieu duoc cung cap, "
    "khong bia them so lieu hay su kien khong co trong du lieu."
)


def _narrate(agent_name: str, payload: dict) -> tuple[str, bool]:
    try:
        text = chat(NARRATION_SYSTEM_PROMPT, f"[{agent_name}] Du lieu quan sat duoc: {payload}")
        return text, True
    except LLMUnavailableError:
        return f"[{agent_name}] narrative unavailable (Groq API not reachable); structured data attached.", False


def _log(trace_fh, case_id: str, step: str, narrative: str, llm_used: bool, data: dict) -> None:
    trace_fh.write_line(
        {
            "case_id": case_id,
            "step": step,
            "handoff_to": "coordinator",
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "model": MODEL_NAME,
            "llm_used": llm_used,
            "narrative": narrative,
            "data": data,
        }
    )


def process_case(case_input: dict, data: OlistData, trace_fh) -> dict:
    case_id = case_input["case_id"]
    order_id = case_input["customer_request"]["claimed_order_id"]

    order = data.get_order(order_id)
    if order is None:
        raise ValueError(f"{case_id}: claimed_order_id {order_id} not found in orders.csv")

    cust = customer_agent.investigate(data, order)
    narrative, used = _narrate(
        "customer_agent",
        {"customer_unique_id": cust["customer_unique_id"], "related_order_ids": cust["related_order_ids"]},
    )
    _log(trace_fh, case_id, "customer_agent", narrative, used, cust)

    op = order_product_agent.investigate(data, order_id)
    narrative, used = _narrate(
        "order_product_agent",
        {"item_count": len(op["items"]), "seller_ids": op["seller_ids"], "category_names": op["category_names"]},
    )
    _log(trace_fh, case_id, "order_product_agent", narrative, used, {k: v for k, v in op.items() if k != "sellers"})

    pay = payment_agent.investigate(data, order_id, op["items"])
    narrative, used = _narrate(
        "payment_agent",
        {
            "payment_total_brl": pay["payment_total_brl"],
            "expected_total_brl": pay["expected_total_brl"],
            "reconciled": pay["reconciled"],
        },
    )
    _log(trace_fh, case_id, "payment_agent", narrative, used, {k: v for k, v in pay.items() if k != "payments"})

    deliv = delivery_agent.investigate(data, order, op["items"])
    narrative, used = _narrate(
        "delivery_agent",
        {
            "delivery_variance_hours": deliv["delivery_variance_hours"],
            "is_late": deliv["is_late"],
            "late_handoff_seller_ids": deliv["late_handoff_seller_ids"],
        },
    )
    _log(trace_fh, case_id, "delivery_agent", narrative, used, deliv)

    decision = policy_agent.decide(order, op, pay, deliv, cust)
    narrative, used = _narrate(
        "policy_agent",
        {
            "primary_issue": decision["primary_issue"],
            "root_cause_code": decision["root_cause_code"],
            "recommended_refund_brl": decision["recommended_refund_brl"],
        },
    )
    _log(trace_fh, case_id, "policy_agent", narrative, used, decision)

    output = build_output(case_id, order_id, order, op, pay, deliv, cust, decision)

    ok, issues = verifier_agent.verify(output, data)
    _log(
        trace_fh,
        case_id,
        "verifier_agent",
        f"verification {'passed' if ok else 'FAILED'}: {len(issues)} issue(s)",
        False,
        {"ok": ok, "issues": issues},
    )
    if not ok:
        raise ValueError(f"{case_id}: verifier rejected output: {issues}")

    return output
