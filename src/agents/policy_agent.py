"""Policy Agent: ap EC_POLICY_V2 len fact book do coordinator gop lai.

Agent nay CO CHU DICH khong duoc quyen doc CSV (config.AGENTS['policy_agent']
.allowed_tables rong). No chi duoc ket luan tu handoff card cua agent khac. Do la
diem cot loi cua de bai: co phan cong, co handoff, co kiem chung -- khong phai mot
prompt lam tat.

Vong kiem chung:

    Policy Agent de xuat  ->  rule engine phan bien
                              |- khop  -> nhan de xuat cua agent
                              |- lech  -> tra nguoc kem dung diem lech, agent sua lai
                                          (toi da MAX_AGENT_RETRIES lan)
                              |- van lech -> lay ket qua rule engine, ghi
                                             policy_override=true vao trace

Vong nay khong phai de che giau LLM. No la co che kiem chung that: ty le dong y
giua agent va rule engine duoc do va bao cao sau moi luot chay.
"""

from __future__ import annotations

import json

from src import config
from src.agents.base import AgentContext, BaseAgent
from src.contracts import PolicyDecision
from src.policy import limits, taxonomy
from src.policy.rules import FactBook, decide, diff_decisions

_SYSTEM = """Ban la policy_agent, ap bo quy tac EC_POLICY_V2 cho mot khieu nai thuong mai dien tu.
Ban KHONG duoc truy cap du lieu goc. Ban chi duoc ket luan tu fact ma cac agent khac ban giao.

PRIMARY ISSUE - xet theo DUNG THU TU SAU, luat dau tien thoa man la ket qua:
1. canceled_order_paid     : order_status = "canceled" VA payment_total_brl > 0
2. unavailable_order_paid  : order_status = "unavailable" VA payment_total_brl > 0
3. late_delivery_seller    : delivery_variance_hours > 0 VA co seller ban giao sau shipping_limit_date
4. late_delivery_logistics : delivery_variance_hours > 0 VA khong seller nao ban giao muon
5. valid_split_payment     : payment_count >= 2 VA reconciled = true
6. unsupported_late_claim  : delivery_variance_hours <= 0 VA reconciled = true

Thu tu quan trong hon dieu kien. Mot don giao tre ma co 2 payment row thoa ca luat 3/4
lan luat 5, nhung luat 3/4 dung truoc nen thang.

SECONDARY ISSUES - kiem tra DU CA NAM dieu kien, dung dung lai sau khi tim thay mot cai.
Them vao ket qua theo DUNG THU TU duoi day:
1. multi_item_order     : item_count >= 2
2. multi_seller_order   : seller_count >= 2
3. split_payment        : payment_count >= 2
4. repeat_customer      : related_order_count > 0     <- rat de bo sot, kiem tra ky
5. multiple_categories  : distinct_category_count >= 2

ROOT CAUSE ung voi primary issue:
  canceled_order_paid     -> ORDER_CANCELED_AFTER_PAYMENT
  unavailable_order_paid  -> ORDER_UNAVAILABLE_AFTER_PAYMENT
  late_delivery_seller    -> SELLER_HANDOFF_AFTER_LIMIT
  late_delivery_logistics -> CARRIER_DELIVERED_AFTER_ESTIMATE
  valid_split_payment     -> MULTIPLE_PAYMENTS_RECONCILED
  unsupported_late_claim  -> DELIVERY_WITHIN_ESTIMATE

RESPONSIBLE PARTY:
  canceled_order_paid / unavailable_order_paid -> [{"party_type":"platform","party_id":"OLIST_PLATFORM"}]
  late_delivery_seller    -> moi seller trong late_handoff_seller_ids, party_type "seller"
  late_delivery_logistics -> [{"party_type":"logistics_provider","party_id":"LOGISTICS_PROVIDER"}]
  valid_split_payment / unsupported_late_claim -> []

REFUND:
  canceled_order_paid / unavailable_order_paid -> payment_total_brl
  late_delivery_seller / late_delivery_logistics -> freight_total_brl (tong freight CA DON)
  con lai -> 0

ACTION - dat action chinh truoc, roi duyet DUNG NAM buoc bo sung theo thu tu duoi.
Voi moi buoc, tra loi co hoac khong roi moi sang buoc tiep; khong bo qua buoc nao.

  Action chinh:
    canceled_order_paid / unavailable_order_paid -> issue_full_refund
    late_delivery_seller / late_delivery_logistics -> refund_freight
    valid_split_payment    -> explain_valid_split_payment
    unsupported_late_claim -> reject_late_refund

  Buoc 1  review_seller_handoff        : primary co phai late_delivery_seller khong?
  Buoc 2  review_carrier_delay         : primary co phai late_delivery_logistics khong?
  Buoc 3  verify_refund_completion     : action chinh co phai issue_full_refund khong?
  Buoc 4  coordinate_multi_seller_case : secondary co multi_seller_order khong?
  Buoc 5  verify_payment_allocation    : secondary co split_payment khong?
          NHUNG neu primary la valid_split_payment thi KHONG duoc them action nay,
          vi explain_valid_split_payment da giai thich split payment roi.

  Toi da 5 action.

CASE STATUS: "action_required" neu refund > 0, nguoc lai "no_action".

Tra ve DUY NHAT mot doi tuong JSON theo dung khuon duoi.

Voi MOI dong trong "secondary_checks" ban phai chep lai gia tri that tu fact book vao
"value", chep nguong vao "rule", roi tu thuc hien phep so sanh de dien "result".
Day la buoc de sai nhat: dung chep "result" theo cam tinh, phai so sanh "value" voi
"rule" that su. Vi du value=1 va rule="> 0" thi result BAT BUOC la true.

{
  "primary_check": {
    "order_status": "...",
    "payment_total_brl": <so>,
    "delivery_variance_hours": <so hoac null>,
    "is_delivered_late": <true/false>,
    "has_late_handoff_seller": <true/false>,
    "payment_count": <so>,
    "reconciled": <true/false hoac null>,
    "first_rule_matched": <1..6>
  },
  "secondary_checks": [
    {"issue": "multi_item_order",     "value": <item_count>,              "rule": ">= 2", "result": <true/false>},
    {"issue": "multi_seller_order",   "value": <seller_count>,            "rule": ">= 2", "result": <true/false>},
    {"issue": "split_payment",        "value": <payment_count>,           "rule": ">= 2", "result": <true/false>},
    {"issue": "repeat_customer",      "value": <related_order_count>,     "rule": "> 0",  "result": <true/false>},
    {"issue": "multiple_categories",  "value": <distinct_category_count>, "rule": ">= 2", "result": <true/false>}
  ],
  "primary_action": "...",
  "action_checks": [
    {"action": "review_seller_handoff",        "condition": "primary la late_delivery_seller",              "applies": <true/false>},
    {"action": "review_carrier_delay",         "condition": "primary la late_delivery_logistics",           "applies": <true/false>},
    {"action": "verify_refund_completion",     "condition": "primary_action la issue_full_refund",          "applies": <true/false>},
    {"action": "coordinate_multi_seller_case", "condition": "multi_seller_order = true",                    "applies": <true/false>},
    {"action": "verify_payment_allocation",    "condition": "split_payment = true VA primary khong phai valid_split_payment", "applies": <true/false>}
  ],
  "primary_issue": "...",
  "root_cause_code": "...",
  "responsible_parties": [{"party_type":"...","party_id":"..."}],
  "recommended_refund_brl": <so>,
  "case_status": "...",
  "rationale": "mot cau giai thich vi sao chon primary issue nay"
}

Danh sach secondary_issues va resolution_actions cuoi cung se duoc ghep tu chinh
"secondary_checks" va "action_checks" cua ban, theo dung thu tu nghiep vu. Ban khong
can tu sap xep -- ban chi can so sanh cho dung."""

_RETRY_NOTE = """

LUOT TRUOC BAN DA SAI. Bo kiem chung doc lap phat hien cac diem lech sau:

{conflicts}

Lam lai tu dau va cham hon. Voi moi dong trong "secondary_checks" va "action_checks",
doc lai gia tri that trong fact book, viet no vao "value", roi thuc hien phep so sanh
VOI TUNG CHU SO thay vi doan. Neu related_order_count la 1 thi 1 > 0 la dung, nen
repeat_customer phai la true. Neu seller_count la 2 thi 2 >= 2 la dung, nen
multi_seller_order phai la true va coordinate_multi_seller_case phai applies=true."""

# Cac fact ma Policy Agent duoc nhin. Cat gon de prompt khong bi loang boi cac
# truong chi phuc vu assembler (ID, timestamp chi tiet...).
_DECISION_FACT_KEYS = (
    "order_found",
    "order_status",
    "item_count",
    "seller_count",
    "payment_count",
    "related_order_count",
    "distinct_category_count",
    "payment_total_brl",
    "freight_total_brl",
    "item_total_brl",
    "expected_total_brl",
    "difference_brl",
    "reconciled",
    "delivery_variance_hours",
    "is_delivered_late",
    "has_late_handoff_seller",
    "late_handoff_seller_ids",
    "carrier_handoff_at",
    "has_delivery_timestamps",
)


class PolicyAgent(BaseAgent):
    name = "policy_agent"

    def _decision_view(self, facts: FactBook) -> dict:
        return {key: facts.get(key) for key in _DECISION_FACT_KEYS}

    @staticmethod
    def _secondary_from_checks(payload: dict) -> list[str] | None:
        """Ghep secondary_issues tu phan doi chieu cua chinh LLM, theo thu tu nghiep vu.

        Phan xet doan la cua LLM (no tu so sanh value voi rule de ra result). Phan
        sap xep la cua code. Bat mot model 9B vua so sanh vua nho thu tu 1..5 la
        dat hai viec vao mot cho, va thu tu la thu duy nhat code lam khong bao gio sai.
        """
        raw = payload.get("secondary_checks")
        if not isinstance(raw, list) or not raw:
            return None
        results: dict[str, bool] = {}
        for entry in raw:
            if isinstance(entry, dict) and entry.get("issue") in taxonomy.SECONDARY_ISSUE_ORDER:
                results[str(entry["issue"])] = entry.get("result") is True
        if not results:
            return None
        return [name for name in taxonomy.SECONDARY_ISSUE_ORDER if results.get(name)]

    @staticmethod
    def _actions_from_checks(payload: dict, primary_issue: str) -> list[str] | None:
        """Ghep resolution_actions tu action_checks cua LLM, theo thu tu nghiep vu."""
        raw = payload.get("action_checks")
        if not isinstance(raw, list) or not raw:
            return None
        applies: dict[str, bool] = {}
        for entry in raw:
            if isinstance(entry, dict) and entry.get("action") in taxonomy.SUPPLEMENTARY_ACTION_ORDER:
                applies[str(entry["action"])] = entry.get("applies") is True

        primary_action = payload.get("primary_action")
        if primary_action not in taxonomy.PRIMARY_ACTION_BY_ISSUE.values():
            primary_action = taxonomy.PRIMARY_ACTION_BY_ISSUE[primary_issue]

        actions = [primary_action]
        actions += [a for a in taxonomy.SUPPLEMENTARY_ACTION_ORDER if applies.get(a)]
        return actions[: limits.MAX_RESOLUTION_ACTIONS]

    def _parse(self, payload: dict, reference: PolicyDecision) -> PolicyDecision | None:
        """Chuyen JSON cua LLM thanh PolicyDecision. Tra None neu sai kieu nang."""
        primary = payload.get("primary_issue")
        if primary not in taxonomy.PRIMARY_ISSUE_PRIORITY:
            return None

        # Uu tien phan doi chieu tuong minh; chi doc danh sach tho khi khong co.
        secondary = self._secondary_from_checks(payload)
        if secondary is None:
            raw_secondary = payload.get("secondary_issues")
            if not isinstance(raw_secondary, list):
                return None
            secondary = [
                name
                for name in taxonomy.SECONDARY_ISSUE_ORDER
                if name in raw_secondary
            ]

        parties = payload.get("responsible_parties")
        if not isinstance(parties, list):
            parties = []
        clean_parties = [
            {"party_type": str(p.get("party_type")), "party_id": str(p.get("party_id"))}
            for p in parties
            if isinstance(p, dict) and p.get("party_type") and p.get("party_id")
        ]

        refund = payload.get("recommended_refund_brl")
        if not isinstance(refund, (int, float)):
            return None

        actions = self._actions_from_checks(payload, primary)
        if actions is None:
            raw_actions = payload.get("resolution_actions")
            if not isinstance(raw_actions, list):
                return None
            actions = [a for a in raw_actions if a in taxonomy.ALL_ACTIONS]

        status = payload.get("case_status")
        if status not in taxonomy.CASE_STATUSES:
            return None

        return PolicyDecision(
            primary_issue=primary,
            secondary_issues=secondary,
            root_cause_code=str(
                payload.get("root_cause_code") or taxonomy.ROOT_CAUSE_BY_PRIMARY[primary]
            ),
            responsible_parties=clean_parties,
            recommended_refund_brl=round(float(refund), 2),
            resolution_actions=actions,
            case_status=status,
            # Confidence khong hoi LLM: no phai la ham cua bang chung thuc te,
            # khong phai cam giac cua model.
            confidence=reference.confidence,
            rationale=str(payload.get("rationale") or "")[:400],
        )

    def run(self, ctx: AgentContext, facts: FactBook) -> tuple[PolicyDecision, dict]:
        """Tra ve (quyet dinh duoc chon, thong ke kiem chung)."""
        reference = decide(facts)
        view = json.dumps(self._decision_view(facts), ensure_ascii=False, indent=2, default=str)

        conflicts: list[str] = []
        accepted: PolicyDecision | None = None
        attempts = 0

        for attempt in range(config.MAX_AGENT_RETRIES + 1):
            attempts = attempt + 1
            system = _SYSTEM
            if conflicts:
                system += _RETRY_NOTE.format(conflicts="\n".join(f"- {c}" for c in conflicts))

            payload = self.ask_llm(
                ctx,
                system,
                f"Fact book cho ticket {ctx.case_id}:\n{view}",
                step=f"apply_policy_attempt_{attempts}",
                max_tokens=1024,
            )
            if payload is None:
                conflicts = ["Khong lay duoc JSON hop le tu model"]
                continue

            proposed = self._parse(payload, reference)
            if proposed is None:
                conflicts = ["JSON tra ve thieu truong bat buoc hoac gia tri ngoai danh muc"]
                ctx.trace.emit(
                    case_id=ctx.case_id,
                    agent=self.name,
                    step="apply_policy",
                    event="proposal_invalid",
                    attempt=attempts,
                )
                continue

            conflicts = diff_decisions(proposed, reference)
            ctx.trace.emit(
                case_id=ctx.case_id,
                agent=self.name,
                step="apply_policy",
                event="cross_check",
                attempt=attempts,
                agreed=not conflicts,
                conflicts=conflicts,
                agent_primary_issue=proposed.primary_issue,
                rule_primary_issue=reference.primary_issue,
            )

            if not conflicts:
                accepted = proposed
                break

        overridden = accepted is None
        decision = reference if overridden else accepted
        assert decision is not None

        if overridden:
            ctx.trace.emit(
                case_id=ctx.case_id,
                agent=self.name,
                step="apply_policy",
                event="policy_override",
                reason="Policy Agent khong khop rule engine sau khi da retry",
                remaining_conflicts=conflicts,
                attempts=attempts,
            )

        stats = {
            "attempts": attempts,
            "agreed_with_rule_engine": not overridden,
            "overridden": overridden,
            "conflicts": conflicts,
        }
        return decision, stats


__all__ = ["PolicyAgent"]
