"""Bon agent chuyen trach theo nguon du lieu: customer, order&product, payment, delivery.

Moi agent chay hai luot LLM cho mot case:

  Luot 1 - LAP KE HOACH
      Agent nhin ticket va danh muc tool NO DUOC PHEP goi, tu chon tool nao can.
      Day la quyet dinh that: neu chon thieu tool, fact se thieu va Verifier bat loi.
      Chon tool ngoai quyen -> ToolAccessError, khong am tham bo qua.

  Luot 2 - DUNG HANDOFF CARD
      Agent doc ket qua tool va viet phan dien giai: cau hoi da tra loi duoc gi,
      fact nao con thieu hoac mau thuan, agent tiep theo nen lam gi.

Giua hai luot la tang tool deterministic. So lieu di thang tu tool vao card,
LLM khong cham vao.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.agents.base import AgentContext, BaseAgent
from src.contracts import Fact, HandoffCard
from src.loader import OrderBundle
from src.tools.registry import call_tool, describe_tools_for_prompt, tools_for_agent

# Prompt duoc giu ngan co chu dich: Groq gioi han 6000 token/phut va 4 agent nay
# chiem phan lon luu luong. Moi 100 token cat di o day tiet kiem 20000 token cho
# ca luot chay 50 case.

_PLAN_SYSTEM = """Ban la {agent_name}, dieu tra khieu nai thuong mai dien tu.
Nhiem vu: {role}

Tool duoc phep goi:
{tool_list}

Chon du tool can de tra loi cau hoi, khong chon thua.
Tra ve JSON: {{"tools": ["..."], "reason": "..."}}"""

_CARD_SYSTEM = """Ban la {agent_name}, dieu tra khieu nai thuong mai dien tu.
Nhiem vu: {role}

Ban vua nhan ket qua tool. KHONG go lai con so hay ID nao; he thong da dinh kem
chung. Viec cua ban la danh gia va ban giao.

Tra ve JSON:
{{"question": "...", "missing_or_conflicting": [{{"field": "...", "reason": "...", "impact": "..."}}],
  "next_action": "...", "notes": "toi da 2 cau"}}

Quy tac: gia tri null la SU THAT cua du lieu, khong phai loi (don bi huy thi khong co
ngay giao). Chi bao thieu khi that su can cho ket luan. Khong suy dien su kien khong co
trong du lieu. Khong co gi thieu thi tra mang rong."""


@dataclass(frozen=True)
class DomainAgentProfile:
    name: str
    question: str
    to_agent: str
    fallback_next_action: str


_PROFILES: dict[str, DomainAgentProfile] = {
    "customer_agent": DomainAgentProfile(
        name="customer_agent",
        question="Khach hang dung sau order nay la ai va ho da tung mua don nao khac chua?",
        to_agent="coordinator",
        fallback_next_action=(
            "coordinator: chuyen customer_unique_id va related_order_ids cho policy_agent "
            "de xet secondary issue repeat_customer"
        ),
    ),
    "order_product_agent": DomainAgentProfile(
        name="order_product_agent",
        question="Order dang o trang thai nao, gom nhung item, seller, product va category nao?",
        to_agent="coordinator",
        fallback_next_action=(
            "coordinator: chuyen order_status cho policy_agent de xet hai luat uu tien cao nhat, "
            "va chuyen danh sach item/seller cho delivery_agent"
        ),
    ),
    "payment_agent": DomainAgentProfile(
        name="payment_agent",
        question="Khach da tra bao nhieu, bang phuong thuc nao, va co khop voi item + freight khong?",
        to_agent="coordinator",
        fallback_next_action=(
            "coordinator: chuyen payment_total_brl, difference_brl va reconciled cho policy_agent"
        ),
    ),
    "delivery_agent": DomainAgentProfile(
        name="delivery_agent",
        question="Don co giao tre hon cam ket khong, va seller nao ban giao sau shipping_limit_date?",
        to_agent="coordinator",
        fallback_next_action=(
            "coordinator: chuyen delivery_variance_hours va late_handoff_seller_ids cho policy_agent "
            "de phan biet late_delivery_seller voi late_delivery_logistics"
        ),
    ),
}


class DomainAgent(BaseAgent):
    """Mot agent chuyen trach theo nguon du lieu."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__()
        self.profile = _PROFILES[name]

    # -- luot 1 -------------------------------------------------------------

    def plan_tools(self, ctx: AgentContext) -> tuple[list[str], bool]:
        """Cho LLM chon tool. Tra ve (danh sach tool, co dung fallback khong)."""
        available = [spec.name for spec in tools_for_agent(self.name)]

        system = _PLAN_SYSTEM.format(
            agent_name=self.name,
            role=self.spec.role,
            tool_list=describe_tools_for_prompt(self.name),
        )
        user = json.dumps(
            {
                "ticket_id": ctx.case_id,
                "claimed_order_id": ctx.order_id,
                "question": self.profile.question,
            },
            ensure_ascii=False,
            indent=2,
        )

        payload = self.ask_llm(ctx, system, user, step="plan_tools", max_tokens=192)
        if payload is None:
            return available, True

        raw = payload.get("tools")
        chosen = [name for name in raw if name in available] if isinstance(raw, list) else []

        if not chosen:
            ctx.trace.emit(
                case_id=ctx.case_id,
                agent=self.name,
                step="plan_tools",
                event="plan_fallback",
                reason="LLM khong chon duoc tool hop le",
                llm_returned=raw,
                fallback_tools=available,
            )
            return available, True

        # Thieu tool thi fact se thieu va Verifier se bat. Ghi lai de con dieu tra.
        skipped = [name for name in available if name not in chosen]
        if skipped:
            ctx.trace.emit(
                case_id=ctx.case_id,
                agent=self.name,
                step="plan_tools",
                event="tools_skipped",
                skipped=skipped,
                reason=str(payload.get("reason") or "")[:200],
            )
        return chosen, False

    # -- luot 2 -------------------------------------------------------------

    def run(self, ctx: AgentContext, bundle: OrderBundle) -> HandoffCard:
        """Chay tron mot luot: lap ke hoach -> goi tool -> dung handoff card."""
        chosen, used_fallback = self.plan_tools(ctx)

        facts: list[Fact] = []
        for tool_name in chosen:
            tool_facts = call_tool(self.name, tool_name, bundle)
            facts.extend(tool_facts)
            ctx.trace.emit(
                case_id=ctx.case_id,
                agent=self.name,
                step="tool_call",
                event="tool_result",
                tool=tool_name,
                fact_keys=[f.key for f in tool_facts],
            )

        system = _CARD_SYSTEM.format(agent_name=self.name, role=self.spec.role)
        user = json.dumps(
            {
                "ticket_id": ctx.case_id,
                "claimed_order_id": ctx.order_id,
                "question": self.profile.question,
                "tools_called": chosen,
                # Bo source_ids khoi prompt: moi ID la 32 ky tu hex lap di lap lai,
                # chiem toi mot nua so token ma LLM khong can toi chung -- code da
                # dinh kem chung vao card. Groq gioi han 6000 token/phut nen cat
                # cho nay giam gan mot nua thoi gian chay.
                "tool_results": [
                    {"key": f.key, "value": f.value, "source_count": len(f.source_ids)}
                    for f in facts
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        payload = self.ask_llm(ctx, system, user, step="build_card", max_tokens=320)

        card = self.make_card(
            ctx,
            to_agent=self.profile.to_agent,
            question=self.profile.question,
            facts=facts,
            llm_payload=payload,
            tools_used=chosen,
            fallback_next_action=self.profile.fallback_next_action,
        )
        ctx.trace.emit(
            case_id=ctx.case_id,
            agent=self.name,
            step="handoff",
            event="handoff_sent",
            to_agent=card.to_agent,
            fact_count=len(card.facts),
            gap_count=len(card.missing_or_conflicting),
            tools_used=chosen,
            plan_fallback=used_fallback,
            llm_ok=card.llm_ok,
        )
        return card


def build_domain_agents() -> list[DomainAgent]:
    """Bon agent chuyen trach, theo thu tu dieu phoi cua coordinator."""
    return [DomainAgent(name) for name in _PROFILES]


__all__ = ["DomainAgent", "DomainAgentProfile", "build_domain_agents"]
