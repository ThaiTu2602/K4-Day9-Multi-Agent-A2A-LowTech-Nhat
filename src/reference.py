"""Duong chay THAM CHIEU: khong goi LLM, chi tool + rule engine.

Muc dich khong phai de thay the he agent. Muc dich la co mot moc so sanh:

  - Chay `python -m src.reference --check` bat ky luc nao de biet tang du lieu va
    tang luat con dung hay khong, khong ton mot dong token nao.
  - Sau khi he agent chay xong, `python -m src.orchestrator` tu dong diff ket qua
    agent voi moc nay. Diff khac rong = co bug, phai dieu tra truoc khi nop.

"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src import config
from src.contracts import CaseTicket, Fact
from src.loader import OlistStore, OrderBundle, get_store
from src.policy import schema
from src.policy.assembler import assemble_output
from src.policy.rules import FactBook, decide
from src.tools.registry import TOOL_REGISTRY, call_tool

# Thu tu goi tool cua duong tham chieu: dung tap tool ma 4 domain agent so huu.
_REFERENCE_TOOL_PLAN: list[tuple[str, str]] = [
    ("customer_agent", "get_customer_identity"),
    ("customer_agent", "get_customer_order_history"),
    ("order_product_agent", "get_order_header"),
    ("order_product_agent", "get_order_items"),
    ("order_product_agent", "get_product_context"),
    ("payment_agent", "get_payment_rows"),
    ("payment_agent", "reconcile_payments"),
    ("delivery_agent", "get_delivery_timestamps"),
    ("delivery_agent", "analyze_seller_handoff"),
]


def facts_to_book(facts: list[Fact]) -> FactBook:
    """Gop danh sach Fact thanh dict key -> value de rule engine tra cuu."""
    return {f.key: f.value for f in facts}


def collect_all_facts(bundle: OrderBundle) -> list[Fact]:
    """Goi day du 9 tool qua lop kiem soat quyen, gom thanh mot danh sach Fact."""
    collected: list[Fact] = []
    for agent_name, tool_name in _REFERENCE_TOOL_PLAN:
        collected.extend(call_tool(agent_name, tool_name, bundle))
    return collected


def build_reference_output(ticket: CaseTicket, store: OlistStore) -> dict:
    """Sinh output cho mot case bang duong tham chieu."""
    bundle = store.build_bundle(ticket.claimed_order_id)
    facts = collect_all_facts(bundle)
    book = facts_to_book(facts)
    decision = decide(book)
    return assemble_output(ticket.case_id, ticket.claimed_order_id, book, decision)


def load_tickets(input_dir: Path | None = None) -> list[CaseTicket]:
    """Doc toan bo input/EC_*.json theo thu tu ten file."""
    directory = Path(input_dir or config.INPUT_DIR)
    tickets: list[CaseTicket] = []
    for path in sorted(directory.glob("EC_*.json")):
        tickets.append(CaseTicket.from_input(json.loads(path.read_text(encoding="utf-8"))))
    return tickets


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Duong chay tham chieu (khong dung LLM)")
    parser.add_argument(
        "--write",
        metavar="DIR",
        help="Ghi output tham chieu ra thu muc nay (mac dinh chi kiem tra, khong ghi)",
    )
    parser.add_argument("--summary", action="store_true", help="In bang tom tat 50 case")
    args = parser.parse_args()

    store = get_store()
    tickets = load_tickets()
    print(f"Nap du lieu: {store.stats()}")
    print(f"Nap {len(tickets)} case tu {config.INPUT_DIR}")
    print(f"Tool kha dung: {len(TOOL_REGISTRY)}\n")

    total_violations = 0
    rows: list[tuple[str, str, str, float, int]] = []

    out_dir = Path(args.write) if args.write else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    for ticket in tickets:
        doc = build_reference_output(ticket, store)
        violations = schema.validate_output(
            doc, ticket.case_id, ticket.claimed_order_id, store
        )
        total_violations += len(violations)
        for violation in violations:
            print(f"  {ticket.case_id} {violation}")

        rows.append(
            (
                ticket.case_id,
                doc["case_assessment"]["primary_issue"],
                doc["case_assessment"]["case_status"],
                doc["financial_resolution"]["recommended_refund_brl"],
                len(doc["evidence_ids"]),
            )
        )

        if out_dir:
            (out_dir / f"{ticket.case_id}.json").write_text(
                json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

    if args.summary:
        print(f"\n{'case':8} {'primary_issue':26} {'status':16} {'refund':>10} {'ev':>3}")
        for row in rows:
            print(f"{row[0]:8} {row[1]:26} {row[2]:16} {row[3]:10.2f} {row[4]:3}")

    print()
    if total_violations:
        print(f"HARD GATE THAT BAI: {total_violations} vi pham")
        return 1
    print(f"HARD GATE: {len(tickets)}/{len(tickets)} case sach")
    if out_dir:
        print(f"Da ghi output tham chieu vao {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
