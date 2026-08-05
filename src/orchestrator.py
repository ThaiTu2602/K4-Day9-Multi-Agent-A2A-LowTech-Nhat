"""Diem vao: chay he multi-agent tren 50 case.

    python -m src.orchestrator                # chay het 50 case
    python -m src.orchestrator --cases EC_001 EC_002
    python -m src.orchestrator --limit 5      # chay 5 case dau, de thu nhanh

Luong mot case:

    coordinator.plan_dispatch          1 luot LLM
        |
        +-- 4 domain agent chay song song, moi agent 2 luot LLM
        |     (luot 1 chon tool, tool chay deterministic, luot 2 dung handoff card)
        |
    coordinator.merge_cards            deterministic
        |
    policy_agent.run                   1..3 luot LLM, doi chieu voi rule engine moi luot
        |
    assemble_output                    deterministic
        |
    verifier_agent.run                 12 hard gate + 1 luot LLM review ngu nghia
        |
    ghi output/EC_xxx.json

Sau khi chay xong, orchestrator tu dong diff toan bo output voi duong tham chieu
(src/reference.py). Diff khac rong nghia la co bug, va no duoc in ra ngay.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from src import config
from src.agents import AgentContext, Coordinator, PolicyAgent, VerifierAgent, build_domain_agents
from src.contracts import CaseTicket, HandoffCard
from src.loader import OlistStore, get_store
from src.policy import schema
from src.policy.assembler import assemble_output
from src.reference import build_reference_output, load_tickets
from src.trace import TraceWriter


# ---------------------------------------------------------------------------
# Nap .env (khong dung thu vien ngoai)
# ---------------------------------------------------------------------------


def load_dotenv(path: Path | None = None) -> None:
    """Doc .env vao os.environ. Bien da co san trong moi truong duoc uu tien."""
    env_path = Path(path or config.ROOT_DIR / ".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# ---------------------------------------------------------------------------
# Ket qua mot case
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    case_id: str
    order_id: str
    document: dict
    violations: list[schema.Violation] = field(default_factory=list)
    llm_review_issues: list[str] = field(default_factory=list)
    policy_stats: dict = field(default_factory=dict)
    cards: list[HandoffCard] = field(default_factory=list)
    elapsed_s: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and not self.violations


# ---------------------------------------------------------------------------
# Chay mot case
# ---------------------------------------------------------------------------


class CaseRunner:
    """Giu san instance agent de tai su dung qua nhieu case."""

    def __init__(self, store: OlistStore, trace: TraceWriter) -> None:
        self.store = store
        self.trace = trace
        self.coordinator = Coordinator()
        self.domain_agents = {agent.name: agent for agent in build_domain_agents()}
        self.policy_agent = PolicyAgent()
        self.verifier = VerifierAgent()

    def run(self, ticket: CaseTicket) -> CaseResult:
        started = time.time()
        ctx = AgentContext(
            case_id=ticket.case_id, order_id=ticket.claimed_order_id, trace=self.trace
        )
        self.trace.emit(
            case_id=ticket.case_id,
            agent="orchestrator",
            step="start",
            event="case_start",
            claimed_order_id=ticket.claimed_order_id,
            policy_version=ticket.policy_version,
        )

        try:
            bundle = self.store.build_bundle(ticket.claimed_order_id)
            if not bundle.found:
                self.trace.emit(
                    case_id=ticket.case_id,
                    agent="orchestrator",
                    step="start",
                    event="order_not_found",
                    claimed_order_id=ticket.claimed_order_id,
                )

            # 1. Coordinator giao viec.
            dispatch, _ = self.coordinator.plan_dispatch(ctx, ticket)

            # 2. Bon agent chuyen trach chay song song.
            cards: list[HandoffCard] = []
            with ThreadPoolExecutor(max_workers=len(dispatch) or 1) as pool:
                futures = {
                    pool.submit(self.domain_agents[name].run, ctx, bundle): name
                    for name in dispatch
                }
                for future in as_completed(futures):
                    cards.append(future.result())
            # Sap lai theo thu tu dispatch de fact book on dinh giua cac lan chay.
            order_index = {name: i for i, name in enumerate(dispatch)}
            cards.sort(key=lambda c: order_index.get(c.from_agent, 99))

            # 3. Coordinator gop card.
            facts = self.coordinator.merge_cards(ctx, cards)

            # 4. Policy Agent ket luan, rule engine kiem chung.
            decision, policy_stats = self.policy_agent.run(ctx, facts)

            # 5. Dung ho so.
            document = assemble_output(
                ticket.case_id, ticket.claimed_order_id, facts, decision
            )

            # 6. Verifier chan hard gate.
            passed, violations, llm_issues = self.verifier.run(
                ctx, document, facts, self.store
            )

            result = CaseResult(
                case_id=ticket.case_id,
                order_id=ticket.claimed_order_id,
                document=document,
                violations=violations,
                llm_review_issues=llm_issues,
                policy_stats=policy_stats,
                cards=cards,
                elapsed_s=round(time.time() - started, 2),
            )
            self.trace.emit(
                case_id=ticket.case_id,
                agent="orchestrator",
                step="end",
                event="case_done",
                passed=passed,
                violation_count=len(violations),
                primary_issue=document["case_assessment"]["primary_issue"],
                case_status=document["case_assessment"]["case_status"],
                recommended_refund_brl=document["financial_resolution"][
                    "recommended_refund_brl"
                ],
                policy_agreed=policy_stats.get("agreed_with_rule_engine"),
                elapsed_s=result.elapsed_s,
            )
            return result

        except Exception as exc:  # noqa: BLE001 - mot case hong khong duoc lam do 49 case con lai
            self.trace.emit(
                case_id=ticket.case_id,
                agent="orchestrator",
                step="end",
                event="case_error",
                error=f"{type(exc).__name__}: {exc}"[:400],
            )
            return CaseResult(
                case_id=ticket.case_id,
                order_id=ticket.claimed_order_id,
                document={},
                error=f"{type(exc).__name__}: {exc}",
                elapsed_s=round(time.time() - started, 2),
            )


# ---------------------------------------------------------------------------
# Doi chieu voi duong tham chieu
# ---------------------------------------------------------------------------


def diff_documents(produced: dict, reference: dict, path: str = "") -> list[str]:
    """So sanh sau hai ho so, tra ve danh sach duong dan khac nhau."""
    diffs: list[str] = []

    if isinstance(produced, dict) and isinstance(reference, dict):
        for key in sorted(set(produced) | set(reference)):
            child = f"{path}.{key}" if path else key
            if key not in produced:
                diffs.append(f"{child}: thieu trong output agent")
            elif key not in reference:
                diffs.append(f"{child}: thua trong output agent")
            else:
                diffs.extend(diff_documents(produced[key], reference[key], child))
        return diffs

    if isinstance(produced, list) and isinstance(reference, list):
        if len(produced) != len(reference):
            diffs.append(f"{path}: do dai {len(produced)} vs tham chieu {len(reference)}")
        for index, (a, b) in enumerate(zip(produced, reference)):
            diffs.extend(diff_documents(a, b, f"{path}[{index}]"))
        return diffs

    if produced != reference:
        diffs.append(f"{path}: {produced!r} vs tham chieu {reference!r}")
    return diffs


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def observed_model_usage(trace_path: Path) -> dict:
    """Doc lai trace de biet model NAO DA THUC SU chay, khong phai model duoc cau hinh.

    Neu OpenRouter het quota giua chung, mot phan cong viec se roi sang model du
    phong. metadata.json phai phan anh dieu do, neu khong thi no khai bao sai.
    """
    calls: dict[str, int] = {}
    errors = 0
    fallbacks = 0
    parse_failures = 0
    if not trace_path.exists():
        return {}
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        event = record.get("event")
        if event == "llm_call":
            key = f"{record.get('provider')}/{record.get('model_id')}"
            calls[key] = calls.get(key, 0) + 1
            if record.get("parsed_ok") is False:
                parse_failures += 1
        elif event in ("llm_error", "llm_quota_exhausted"):
            errors += 1
        elif event == "model_fallback":
            fallbacks += 1
    return {
        "llm_calls_by_model": calls,
        "llm_calls_total": sum(calls.values()),
        "llm_errors": errors,
        "llm_parse_failures": parse_failures,
        "model_fallbacks": fallbacks,
    }


def write_metadata(results: list[CaseResult], wall_clock_s: float) -> None:
    """Sinh logging/metadata.json tu config + so lieu thuc cua luot chay."""
    agreed = sum(1 for r in results if r.policy_stats.get("agreed_with_rule_engine"))
    overridden = sum(1 for r in results if r.policy_stats.get("overridden"))

    metadata = config.build_metadata(
        runtime={
            **observed_model_usage(config.TRACE_PATH),
            "python": platform.python_version(),
            "os": f"{platform.system()} {platform.release()}",
            "run_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "cases_total": len(results),
            "cases_passed_hard_gates": sum(1 for r in results if r.ok),
            "wall_clock_s": round(wall_clock_s, 2),
            "concurrency": config.CONCURRENCY,
            "temperature": config.TEMPERATURE,
            "top_p": config.TOP_P,
            "seed": config.SEED,
            "cache_enabled": config.ENABLE_CACHE,
            "policy_agent_agreed_with_rule_engine": agreed,
            "policy_agent_overridden": overridden,
        }
    )
    config.METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.METADATA_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Chay he multi-agent A2A tren cac case")
    parser.add_argument("--cases", nargs="*", help="Chi chay cac case_id nay")
    parser.add_argument("--limit", type=int, help="Chi chay N case dau tien")
    parser.add_argument(
        "--concurrency", type=int, default=config.CONCURRENCY, help="So case chay song song"
    )
    parser.add_argument("--no-cache", action="store_true", help="Bo qua cache response LLM")
    parser.add_argument(
        "--output", default=str(config.OUTPUT_DIR), help="Thu muc ghi output"
    )
    args = parser.parse_args()

    load_dotenv()
    if args.no_cache:
        config.ENABLE_CACHE = False

    try:
        config.check_credentials()
    except RuntimeError as exc:
        print(f"LOI: {exc}", file=sys.stderr)
        return 2

    store = get_store()
    tickets = load_tickets()
    if args.cases:
        wanted = set(args.cases)
        tickets = [t for t in tickets if t.case_id in wanted]
    if args.limit:
        tickets = tickets[: args.limit]

    if not tickets:
        print("LOI: khong co case nao de chay", file=sys.stderr)
        return 2

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Du lieu: {store.stats()}")
    for agent_name, agent_spec in config.AGENTS.items():
        print(
            f"  {agent_name:22} {agent_spec.model.provider.key:11} {agent_spec.model.model_id}"
        )
    print(f"\nChay {len(tickets)} case, concurrency={args.concurrency}\n")

    started = time.time()
    results: list[CaseResult] = []
    print_lock = threading.Lock()

    with TraceWriter() as trace:
        runner = CaseRunner(store, trace)

        def work(ticket: CaseTicket) -> CaseResult:
            result = runner.run(ticket)
            with print_lock:
                if result.error:
                    mark = "ERR "
                    detail = result.error[:70]
                elif result.violations:
                    mark = "GATE"
                    detail = f"{len(result.violations)} vi pham hard gate"
                else:
                    mark = "ok  "
                    assessment = result.document["case_assessment"]
                    detail = (
                        f"{assessment['primary_issue']:24} "
                        f"{assessment['case_status']:16} "
                        f"refund={result.document['financial_resolution']['recommended_refund_brl']:>8.2f}"
                    )
                agreed = result.policy_stats.get("agreed_with_rule_engine")
                flag = "" if agreed or not result.policy_stats else "  [policy_override]"
                print(f"  {mark} {result.case_id}  {detail}{flag}  {result.elapsed_s}s")
            return result

        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(work, ticket) for ticket in tickets]
            for future in as_completed(futures):
                results.append(future.result())

    results.sort(key=lambda r: r.case_id)
    wall_clock = time.time() - started

    # Ghi output cua nhung case qua duoc hard gate.
    written = 0
    for result in results:
        if result.document and not result.violations:
            (out_dir / f"{result.case_id}.json").write_text(
                json.dumps(result.document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            written += 1

    write_metadata(results, wall_clock)

    # --- Doi chieu voi duong tham chieu ------------------------------------
    print("\n" + "=" * 78)
    print("DOI CHIEU VOI DUONG THAM CHIEU (tool + rule engine, khong LLM)")
    print("=" * 78)
    total_diffs = 0
    for result in results:
        if not result.document:
            continue
        ticket = next(t for t in tickets if t.case_id == result.case_id)
        diffs = diff_documents(result.document, build_reference_output(ticket, store))
        if diffs:
            total_diffs += len(diffs)
            print(f"  {result.case_id}: {len(diffs)} diem lech")
            for line in diffs[:6]:
                print(f"      {line}")

    # --- Tong ket -----------------------------------------------------------
    passed = sum(1 for r in results if r.ok)
    errored = [r for r in results if r.error]
    gated = [r for r in results if r.violations]
    agreed = sum(1 for r in results if r.policy_stats.get("agreed_with_rule_engine"))
    llm_flagged = [r for r in results if r.llm_review_issues]

    print("\n" + "=" * 78)
    print("TONG KET")
    print("=" * 78)
    print(f"  Case chay             : {len(results)}")
    print(f"  Qua het hard gate     : {passed}/{len(results)}")
    print(f"  Ghi ra file           : {written}")
    print(f"  Lech so voi tham chieu: {total_diffs}")
    print(f"  Policy Agent khop rule engine: {agreed}/{len(results)}")
    print(f"  Verifier LLM neu nghi van    : {len(llm_flagged)}")
    print(f"  Thoi gian             : {wall_clock:.1f}s")
    print(f"  Trace                 : {config.TRACE_PATH}")
    print(f"  Metadata              : {config.METADATA_PATH}")

    for result in errored:
        print(f"\n  LOI {result.case_id}: {result.error}")
    for result in gated:
        print(f"\n  HARD GATE {result.case_id}:")
        for violation in result.violations[:8]:
            print(f"      {violation}")
    for result in llm_flagged:
        print(f"\n  Verifier LLM neu nghi van {result.case_id}:")
        for issue in result.llm_review_issues[:4]:
            print(f"      - {issue}")

    return 0 if (passed == len(results) and total_diffs == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
