"""Coordinator: nhan ticket, giao viec, gop handoff card, dung ho so cuoi.

Coordinator khong co quyen doc CSV (allowed_tables rong). No khong tu tra cuu
duoc gi ca; moi thu deu phai di qua handoff card cua agent chuyen trach.

Mot luot LLM duy nhat cho moi case: lap ke hoach dieu phoi. Day khong phai thu
tuc hinh thuc -- investigation_scope trong ticket co the tat customer history
hoac product context, va coordinator phai quyet dinh dua tren do.

Phan gop card la deterministic co chu dich: gop la viec cua code, khong phai viec
de mot model 9B go lai vai chuc con so.
"""

from __future__ import annotations

import json

from src.agents.base import AgentContext, BaseAgent
from src.contracts import CaseTicket, HandoffCard
from src.policy.rules import FactBook

_SYSTEM = """Ban la coordinator cua mot to dieu tra khieu nai thuong mai dien tu.
Ban khong tu tra cuu du lieu. Ban giao viec cho cac agent chuyen trach roi tong hop.

Doi ngu cua ban:
- customer_agent      : nhan dien khach hang (customer_unique_id) va lich su mua hang
- order_product_agent : trang thai don, item, seller, product, category
- payment_agent       : cac dong thanh toan va doi soat voi item + freight
- delivery_agent      : do tre giao hang va do tre ban giao cua tung seller

Bon agent nay lam viec doc lap nhau nen chay song song duoc.
Sau do policy_agent ap quy tac, cuoi cung verifier_agent kiem tra truoc khi nop.

Tra ve DUY NHAT mot doi tuong JSON:
{
  "dispatch": [
    {"agent": "ten_agent", "question": "cau hoi cu the giao cho agent nay"}
  ],
  "rationale": "mot cau ve cach ban phan cong"
}

Chi giao viec cho agent thuc su can cho case nay, can cu investigation_scope trong ticket."""

_ALL_DOMAIN_AGENTS = (
    "customer_agent",
    "order_product_agent",
    "payment_agent",
    "delivery_agent",
)


class Coordinator(BaseAgent):
    name = "coordinator"

    def plan_dispatch(self, ctx: AgentContext, ticket: CaseTicket) -> tuple[list[str], bool]:
        """Cho LLM quyet dinh giao viec cho nhung agent nao.

        Tra ve (danh sach agent, co dung fallback khong). Neu LLM tra ve rac thi
        giao het cho ca bon -- thieu fact nguy hiem hon la thua mot luot goi tool.
        """
        system = _SYSTEM
        user = json.dumps(
            {
                "ticket_id": ticket.case_id,
                "claimed_order_id": ticket.claimed_order_id,
                "customer_message": ticket.message,
                "investigation_scope": {
                    "include_customer_history": ticket.include_customer_history,
                    "include_product_context": ticket.include_product_context,
                },
                "policy_version": ticket.policy_version,
            },
            ensure_ascii=False,
            indent=2,
        )

        payload = self.ask_llm(ctx, system, user, step="plan_dispatch", max_tokens=384)
        if payload is None:
            return list(_ALL_DOMAIN_AGENTS), True

        raw = payload.get("dispatch")
        chosen: list[str] = []
        if isinstance(raw, list):
            for entry in raw:
                name = entry.get("agent") if isinstance(entry, dict) else entry
                if name in _ALL_DOMAIN_AGENTS and name not in chosen:
                    chosen.append(name)

        if not chosen:
            ctx.trace.emit(
                case_id=ctx.case_id,
                agent=self.name,
                step="plan_dispatch",
                event="dispatch_fallback",
                reason="LLM khong chon duoc agent hop le",
                fallback=list(_ALL_DOMAIN_AGENTS),
            )
            return list(_ALL_DOMAIN_AGENTS), True

        # order_product_agent va payment_agent la bat buoc: khong co order_status
        # va payment_total_brl thi khong luat nao trong EC_POLICY_V2 xet duoc.
        # delivery_agent bat buoc de phan biet hai luat late_delivery_*.
        required = ("order_product_agent", "payment_agent", "delivery_agent")
        forced = [name for name in required if name not in chosen]
        if forced:
            ctx.trace.emit(
                case_id=ctx.case_id,
                agent=self.name,
                step="plan_dispatch",
                event="dispatch_corrected",
                reason="Bo sung agent bat buoc ma ke hoach cua LLM bo sot",
                added=forced,
                llm_plan=chosen,
            )
            chosen = [name for name in _ALL_DOMAIN_AGENTS if name in chosen or name in forced]

        ctx.trace.emit(
            case_id=ctx.case_id,
            agent=self.name,
            step="plan_dispatch",
            event="dispatch_ready",
            agents=chosen,
            rationale=str(payload.get("rationale") or "")[:200],
        )
        return chosen, False

    @staticmethod
    def merge_cards(ctx: AgentContext, cards: list[HandoffCard]) -> FactBook:
        """Gop fact tu nhieu card thanh mot fact book cho policy_agent.

        Gop bang code chu khong bang LLM: neu de model go lai vai chuc con so thi
        chi can mot chu so sai la mat diem exact match.

        Trung key giua hai card duoc ghi vao trace. Hien tai cac agent khong chong
        lan fact nao ngoai payment_total_brl (payment_agent bao cao o ca hai tool
        cua no, cung mot gia tri).
        """
        book: FactBook = {}
        origin: dict[str, str] = {}
        for card in cards:
            for fact in card.facts:
                if fact.key in book and book[fact.key] != fact.value:
                    ctx.trace.emit(
                        case_id=ctx.case_id,
                        agent="coordinator",
                        step="merge",
                        event="fact_conflict",
                        key=fact.key,
                        existing_from=origin.get(fact.key),
                        existing_value=book[fact.key],
                        new_from=card.from_agent,
                        new_value=fact.value,
                    )
                book[fact.key] = fact.value
                origin[fact.key] = card.from_agent

        ctx.trace.emit(
            case_id=ctx.case_id,
            agent="coordinator",
            step="merge",
            event="fact_book_ready",
            fact_count=len(book),
            from_agents=[c.from_agent for c in cards],
            open_gaps=sum(len(c.missing_or_conflicting) for c in cards),
        )
        return book


__all__ = ["Coordinator"]
