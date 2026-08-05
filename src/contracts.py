"""Hop dong du lieu dung chung giua cac agent (A2A envelope).

Moi thu di qua giua hai agent deu phai la mot HandoffCard. Khong agent nao duoc
doc bien noi bo cua agent khac.

Nguyen tac chong bia so lieu:
  - `facts` do CODE gan vao tu ket qua tool, LLM khong duoc go lai. Neu de LLM
    chep lai "87.39" no co the go thanh "87.4" va mat diem exact match.
  - LLM chiu trach nhiem cac truong dien giai: `question`, `missing_or_conflicting`,
    `next_action`, `notes`.
  - Moi fact bat buoc co `source_ids`. Fact khong co nguon bi Verifier tu choi.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Ticket
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseTicket:
    """Mot case lay tu input/EC_xxx.json."""

    case_id: str
    claimed_order_id: str
    language: str
    message: str
    include_customer_history: bool
    include_product_context: bool
    policy_version: str

    @staticmethod
    def from_input(payload: dict) -> "CaseTicket":
        req = payload.get("customer_request", {}) or {}
        scope = payload.get("investigation_scope", {}) or {}
        return CaseTicket(
            case_id=payload["case_id"],
            claimed_order_id=req.get("claimed_order_id", ""),
            language=req.get("language", "vi"),
            message=req.get("message", ""),
            include_customer_history=bool(scope.get("include_customer_history", True)),
            include_product_context=bool(scope.get("include_product_context", True)),
            policy_version=payload.get("policy_version", ""),
        )


# ---------------------------------------------------------------------------
# Handoff
# ---------------------------------------------------------------------------


@dataclass
class Fact:
    """Mot su that da xac minh, kem ID nguon truy nguoc duoc ve CSV."""

    key: str
    value: Any
    source_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"key": self.key, "value": self.value, "source_ids": list(self.source_ids)}


@dataclass
class Gap:
    """Mot fact con thieu hoac mau thuan."""

    field_name: str
    reason: str
    impact: str = ""

    def to_dict(self) -> dict:
        return {"field": self.field_name, "reason": self.reason, "impact": self.impact}


@dataclass
class HandoffCard:
    """Envelope A2A toi thieu theo dung 4 yeu cau cua de bai.

    1. ticket_id + question   -> case nao, can tra loi cau gi
    2. facts + source_ids     -> fact tim duoc kem ID nguon
    3. missing_or_conflicting -> fact con thieu hoac mau thuan
    4. next_action            -> de xuat cho agent nhan viec
    """

    ticket_id: str
    from_agent: str
    to_agent: str
    question: str
    facts: list[Fact] = field(default_factory=list)
    missing_or_conflicting: list[Gap] = field(default_factory=list)
    next_action: str = ""
    notes: str = ""
    # Metadata phuc vu trace, khong phai noi dung nghiep vu.
    tools_used: list[str] = field(default_factory=list)
    llm_ok: bool = True

    def fact_map(self) -> dict[str, Any]:
        """Truy cap nhanh facts theo key."""
        return {f.key: f.value for f in self.facts}

    def all_source_ids(self) -> list[str]:
        out: list[str] = []
        for f in self.facts:
            for sid in f.source_ids:
                if sid not in out:
                    out.append(sid)
        return out

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "question": self.question,
            "facts": [f.to_dict() for f in self.facts],
            "missing_or_conflicting": [g.to_dict() for g in self.missing_or_conflicting],
            "next_action": self.next_action,
            "notes": self.notes,
            "tools_used": list(self.tools_used),
            "llm_ok": self.llm_ok,
        }

    def to_prompt_json(self) -> str:
        """Ban rut gon dua vao prompt cua agent nhan viec."""
        return json.dumps(
            {
                "ticket_id": self.ticket_id,
                "from_agent": self.from_agent,
                "question": self.question,
                "facts": [f.to_dict() for f in self.facts],
                "missing_or_conflicting": [g.to_dict() for g in self.missing_or_conflicting],
                "next_action": self.next_action,
            },
            ensure_ascii=False,
            indent=2,
        )


# ---------------------------------------------------------------------------
# Quyet dinh cua Policy Agent
# ---------------------------------------------------------------------------


@dataclass
class PolicyDecision:
    """Ket luan ap EC_POLICY_V2 cho mot case."""

    primary_issue: str
    secondary_issues: list[str]
    root_cause_code: str
    responsible_parties: list[dict]
    recommended_refund_brl: float
    resolution_actions: list[str]
    case_status: str
    confidence: float
    rationale: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


__all__ = ["CaseTicket", "Fact", "Gap", "HandoffCard", "PolicyDecision"]
