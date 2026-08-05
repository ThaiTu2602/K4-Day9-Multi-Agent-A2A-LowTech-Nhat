"""Lop nen cho moi agent: goi LLM, parse JSON, ghi trace, chiu duoc loi.

Nguyen tac an toan quan trong nhat cua he thong nam o day:

    LLM khong bao gio duoc phep go lai mot con so.

Neu de model 8B chep lai "87.39" no co the ra "87.4" va mat diem exact match.
Vi vay `HandoffCard.facts` luon do CODE gan tu ket qua tool, con LLM chi dien cac
truong dien giai: question, missing_or_conflicting, next_action, notes.

Khi LLM hong (rate limit, JSON vo, timeout), agent KHONG dung ca case. No ghi
llm_ok=false vao trace roi di tiep bang fact deterministic. Day la degradation
trung thuc: so lieu van dung, con phan dien giai thi trong, va trace noi ro case
nao roi vao tinh huong do.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src import config
from src.agents import llm
from src.contracts import Gap, HandoffCard
from src.trace import NullTrace, TraceWriter


@dataclass
class AgentContext:
    """Thu moi agent can de chay mot case."""

    case_id: str
    order_id: str
    trace: TraceWriter | NullTrace


class BaseAgent:
    """Khung chung cho ca 7 agent."""

    #: Khoa trong config.AGENTS
    name: str = ""

    def __init__(self) -> None:
        if self.name not in config.AGENTS:
            raise KeyError(f"Agent '{self.name}' chua khai bao trong config.AGENTS")
        self.spec = config.AGENTS[self.name]
        self.model = self.spec.model

    # -- goi LLM -----------------------------------------------------------

    def ask_llm(
        self,
        ctx: AgentContext,
        system: str,
        user: str,
        *,
        step: str,
        max_tokens: int | None = None,
    ) -> dict | None:
        """Goi LLM va tra ve dict JSON, hoac None neu that bai.

        Moi lan goi deu sinh mot dong trace, ke ca khi hong.

        Neu provider chinh het quota (429/402) thi chuyen sang model du phong o
        provider con lai. Chi chuyen vi ly do quota, khong chuyen vi loi mang hay
        JSON hong -- nhung loi do phai duoc thay chu khong duoc che di.
        """
        model = self.model
        try:
            result = llm.complete(
                model,
                llm.reasoning_prefix(self.name, model) + system,
                user,
                json_mode=True,
                max_tokens=max_tokens,
            )
        except llm.LLMQuotaError as exc:
            spare = config.fallback_model_for(model)
            if spare is None or spare.model_id == model.model_id:
                ctx.trace.emit(
                    case_id=ctx.case_id,
                    agent=self.name,
                    step=step,
                    event="llm_quota_exhausted",
                    provider=model.provider.key,
                    model_id=model.model_id,
                    error=str(exc)[:300],
                )
                return None

            ctx.trace.emit(
                case_id=ctx.case_id,
                agent=self.name,
                step=step,
                event="model_fallback",
                from_model=model.model_id,
                to_model=spare.model_id,
                reason=str(exc)[:200],
            )
            model = spare
            try:
                result = llm.complete(
                    model,
                    llm.reasoning_prefix(self.name, model) + system,
                    user,
                    json_mode=True,
                    max_tokens=max_tokens,
                )
            except llm.LLMError as exc2:
                ctx.trace.emit(
                    case_id=ctx.case_id,
                    agent=self.name,
                    step=step,
                    event="llm_error",
                    provider=model.provider.key,
                    model_id=model.model_id,
                    error=str(exc2)[:300],
                )
                return None
        except llm.LLMError as exc:
            ctx.trace.emit(
                case_id=ctx.case_id,
                agent=self.name,
                step=step,
                event="llm_error",
                provider=model.provider.key,
                model_id=model.model_id,
                error=str(exc)[:300],
            )
            return None

        parsed = llm.parse_json(result.text)
        ctx.trace.emit(
            case_id=ctx.case_id,
            agent=self.name,
            step=step,
            event="llm_call",
            parsed_ok=parsed is not None,
            **result.as_trace(),
        )
        if parsed is None:
            ctx.trace.emit(
                case_id=ctx.case_id,
                agent=self.name,
                step=step,
                event="llm_parse_failed",
                raw_head=result.text[:300],
            )
        return parsed

    # -- dung handoff card --------------------------------------------------

    @staticmethod
    def _as_gaps(raw: Any) -> list[Gap]:
        """Chuan hoa phan missing_or_conflicting do LLM sinh ra.

        Model nho tra ve du kieu: list[str], list[dict], hoac mot chuoi. Nhan het.
        """
        gaps: list[Gap] = []
        if isinstance(raw, str) and raw.strip():
            return [Gap(field_name="unspecified", reason=raw.strip())]
        if not isinstance(raw, list):
            return gaps
        for entry in raw[:5]:
            if isinstance(entry, str) and entry.strip():
                gaps.append(Gap(field_name="unspecified", reason=entry.strip()))
            elif isinstance(entry, dict):
                gaps.append(
                    Gap(
                        field_name=str(entry.get("field") or entry.get("field_name") or "unspecified"),
                        reason=str(entry.get("reason") or ""),
                        impact=str(entry.get("impact") or ""),
                    )
                )
        return gaps

    def make_card(
        self,
        ctx: AgentContext,
        *,
        to_agent: str,
        question: str,
        facts: list,
        llm_payload: dict | None,
        tools_used: list[str],
        fallback_next_action: str,
    ) -> HandoffCard:
        """Ghep phan deterministic (facts) voi phan dien giai cua LLM."""
        payload = llm_payload or {}
        return HandoffCard(
            ticket_id=ctx.case_id,
            from_agent=self.name,
            to_agent=to_agent,
            # Cho LLM viet lai cau hoi neu no dien dat ro hon, con khong thi giu ban goc.
            question=str(payload.get("question") or question)[:400],
            facts=facts,
            missing_or_conflicting=self._as_gaps(payload.get("missing_or_conflicting")),
            next_action=str(payload.get("next_action") or fallback_next_action)[:400],
            notes=str(payload.get("notes") or "")[:600],
            tools_used=tools_used,
            llm_ok=llm_payload is not None,
        )


__all__ = ["AgentContext", "BaseAgent"]
