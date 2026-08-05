"""Verifier Agent: chot chan cuoi cung truoc khi ghi file.

Hai lop kiem tra, phan vai ro rang:

  LOP 1 - 12 hard gate deterministic (src/policy/schema.py)
      Day la lop QUYET DINH. ID co ton tai trong CSV khong, mang co vuot tran khong,
      timestamp dung dinh dang chua, null co dung quy tac chua, confidence co trong
      [0,1] khong. Vi pham o lop nay chan ghi file.

  LOP 2 - review cua LLM
      Doc output cung fact book va tim mau thuan ngu nghia ma regex khong thay
      duoc, vi du ket luan seller chiu trach nhiem nhung late_handoff_seller_ids
      lai rong. Nhan xet cua lop nay duoc ghi vao trace, khong tu chan file --
      model 9B khong duoc quyen phu quyet mot bo kiem tra da chay dung.
"""

from __future__ import annotations

import json

from src.agents.base import AgentContext, BaseAgent
from src.loader import OlistStore
from src.policy import schema
from src.policy.rules import FactBook

# Luu y khi sua prompt nay: KHONG dua vi du mau thuan cu the vao day.
# Da thu va that bai -- Nemotron 9B chep nguyen van cac cau vi du ra lam ket qua
# thay vi doi chieu du lieu that. Thay bang bang cau hoi bat buoc dien gia tri that.
_SYSTEM = """Ban la verifier_agent, buoc kiem tra cuoi truoc khi ho so duoc nop.

Ban nhan mot ho so ket luan va tap fact ma cac agent da thu thap. Nhiem vu cua ban la
doi chieu hai thu do va tra loi dung bon cau hoi duoi day.

Voi moi cau hoi: chep gia tri THAT tu du lieu duoc cung cap vao truong "observed",
roi moi ket luan "consistent". Khong duoc doan, khong duoc chep lai cau hoi.
Neu du lieu can thiet khong co, dat "consistent": true va giai thich trong "observed".

Tra ve DUY NHAT mot doi tuong JSON:
{
  "answers": [
    {"id": "responsible_seller_backed_by_late_handoff",
     "observed": "responsible_parties=<chep vao>, late_handoff_seller_ids=<chep vao>",
     "consistent": <true/false>},
    {"id": "case_status_matches_refund",
     "observed": "case_status=<chep vao>, recommended_refund_brl=<chep vao>",
     "consistent": <true/false>},
    {"id": "root_cause_matches_primary_issue",
     "observed": "primary_issue=<chep vao>, cause_code=<chep vao>",
     "consistent": <true/false>},
    {"id": "secondary_issues_backed_by_counts",
     "observed": "secondary_issues=<chep vao>, item_count=<chep vao>, seller_count=<chep vao>, payment_count=<chep vao>, related_order_count=<chep vao>",
     "consistent": <true/false>}
  ],
  "verdict": "pass" neu tat ca consistent deu true, nguoc lai "fail"
}

Quy tac:
- responsible_parties rong LA HOP LE khi primary_issue la valid_split_payment hoac
  unsupported_late_claim. Chi khi primary_issue la late_delivery_seller thi moi bat
  buoc late_handoff_seller_ids khac rong.
- case_status phai la action_required khi va chi khi recommended_refund_brl > 0.
- Gia tri null la su that cua du lieu, khong phai loi.
- KHONG bao loi ve dinh dang, tran do dai mang hay quy tac null: da co bo kiem tra
  rieng lo nhung thu do."""

# Cac truong dua cho LLM soi. Bo evidence_ids dai dong de prompt gon.
_REVIEW_FACT_KEYS = (
    "order_status",
    "item_count",
    "seller_count",
    "payment_count",
    "related_order_count",
    "distinct_category_count",
    "payment_total_brl",
    "freight_total_brl",
    "reconciled",
    "delivery_variance_hours",
    "late_handoff_seller_ids",
)


class VerifierAgent(BaseAgent):
    name = "verifier_agent"

    def run(
        self,
        ctx: AgentContext,
        doc: dict,
        facts: FactBook,
        store: OlistStore,
    ) -> tuple[bool, list[schema.Violation], list[str]]:
        """Tra ve (duoc phep ghi file, vi pham hard gate, nhan xet cua LLM)."""
        violations = schema.validate_output(doc, ctx.case_id, ctx.order_id, store)

        ctx.trace.emit(
            case_id=ctx.case_id,
            agent=self.name,
            step="hard_gates",
            event="gate_result",
            passed=not violations,
            violation_count=len(violations),
            violations=[str(v) for v in violations][:10],
        )

        review_payload = self.ask_llm(
            ctx,
            _SYSTEM,
            json.dumps(
                {
                    "ticket_id": ctx.case_id,
                    "ho_so": {
                        "case_assessment": doc.get("case_assessment"),
                        "affected_entities": doc.get("affected_entities"),
                        "root_cause_analysis": doc.get("root_cause_analysis"),
                        "financial_resolution": doc.get("financial_resolution"),
                        "resolution_actions": doc.get("resolution_actions"),
                        "evidence_count": len(doc.get("evidence_ids") or []),
                    },
                    "fact_da_thu_thap": {k: facts.get(k) for k in _REVIEW_FACT_KEYS},
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            step="semantic_review",
            max_tokens=768,
        )

        llm_issues: list[str] = []
        if review_payload is not None:
            answers = review_payload.get("answers")
            if isinstance(answers, list):
                # Chi giu cau tra loi bao KHONG nhat quan, kem gia tri quan sat duoc.
                for answer in answers:
                    if isinstance(answer, dict) and answer.get("consistent") is False:
                        llm_issues.append(
                            f"{answer.get('id')}: {str(answer.get('observed'))[:160]}"
                        )
            else:
                raw = review_payload.get("issues")
                if isinstance(raw, list):
                    llm_issues = [str(x)[:200] for x in raw if str(x).strip()][:10]
            llm_issues = llm_issues[:10]
            ctx.trace.emit(
                case_id=ctx.case_id,
                agent=self.name,
                step="semantic_review",
                event="review_result",
                verdict=review_payload.get("verdict"),
                issue_count=len(llm_issues),
                issues=llm_issues,
            )

        # Hard gate quyet dinh. Nhan xet cua LLM duoc luu de doc lai, khong phu quyet.
        return (not violations), violations, llm_issues


__all__ = ["VerifierAgent"]
