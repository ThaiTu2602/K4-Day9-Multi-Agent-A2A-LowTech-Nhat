"""Cau hinh provider, model va agent cho he thong multi-agent A2A (K4 Day 09).

README muc 9.1: moi agent chi duoc dung model <= 10B parameters.
README muc 9.4: ten model PHAI khai bao ro trong source code (khong dat trong .env)
                va ghi lai trong metadata.json.

He thong dung 2 provider:
  - OpenRouter -> NVIDIA Nemotron Nano 9B V2 (9B, reasoning)
  - Groq       -> Meta Llama 3.1 8B Instant  (8B, tra cuu nhanh)

Ca hai deu noi qua giao dien OpenAI-compatible nen dung chung mot client wrapper.
File nay la nguon chan ly duy nhat cho ten model. logging/metadata.json duoc sinh
tu day khi chay, khong go tay.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Duong dan
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"
LOGGING_DIR = ROOT_DIR / "logging"
CACHE_DIR = ROOT_DIR / ".cache"

TRACE_PATH = LOGGING_DIR / "trace.jsonl"
METADATA_PATH = LOGGING_DIR / "metadata.json"

# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderSpec:
    """Mot LLM provider theo giao dien OpenAI-compatible."""

    key: str
    display_name: str
    base_url: str
    api_key_env: str
    # Rate limit tham khao de chinh CONCURRENCY, khong phai rang buoc cung.
    notes: str = ""

    def api_key(self) -> str:
        """Doc API key tu bien moi truong. Khong bao gio log gia tri nay."""
        value = os.environ.get(self.api_key_env, "").strip()
        if not value:
            raise RuntimeError(
                f"Thieu {self.api_key_env} cho provider '{self.key}'. "
                f"Copy .env.example thanh .env va dan API key vao."
            )
        return value


OPENROUTER = ProviderSpec(
    key="openrouter",
    display_name="OpenRouter",
    base_url="https://openrouter.ai/api/v1",
    api_key_env="OPENROUTER_API_KEY",
    notes="Ban :free bi siet so request moi phut -> giu concurrency thap, bat cache.",
)

GROQ = ProviderSpec(
    key="groq",
    display_name="Groq",
    base_url="https://api.groq.com/openai/v1",
    api_key_env="GROQ_API_KEY",
    notes="14400 request/ngay nhung chi 6000 token/phut -> nut that la TOKEN.",
)

PROVIDERS: dict[str, ProviderSpec] = {OPENROUTER.key: OPENROUTER, GROQ.key: GROQ}

# ---------------------------------------------------------------------------
# Danh muc model (TAT CA <= 10B parameters)
# ---------------------------------------------------------------------------

MAX_PARAMETER_SIZE_B = 10.0


@dataclass(frozen=True)
class ModelSpec:
    """Mot model duoc phep dung trong he thong."""

    key: str
    model_id: str
    display_name: str
    provider: ProviderSpec
    parameter_size_b: float
    context_length: int
    notes: str = ""

    def __post_init__(self) -> None:
        if self.parameter_size_b > MAX_PARAMETER_SIZE_B:
            raise ValueError(
                f"{self.model_id} co {self.parameter_size_b}B params, "
                f"vuot tran {MAX_PARAMETER_SIZE_B}B cua de bai"
            )


NEMOTRON_NANO_9B = ModelSpec(
    key="nemotron_nano_9b_v2",
    model_id="nvidia/nemotron-nano-9b-v2:free",
    display_name="NVIDIA Nemotron Nano 9B V2",
    provider=OPENROUTER,
    parameter_size_b=9.0,
    context_length=128_000,
    notes="Model reasoning. Dung cho khau suy luan va kiem chung.",
)

LLAMA_31_8B = ModelSpec(
    key="llama_3_1_8b_instant",
    model_id="llama-3.1-8b-instant",
    display_name="Meta Llama 3.1 8B Instant",
    provider=GROQ,
    parameter_size_b=8.0,
    context_length=131_072,
    notes="Model instruct nhanh. Dung cho cac agent tra cuu domain va dien handoff card.",
)

MODEL_REGISTRY: dict[str, ModelSpec] = {
    NEMOTRON_NANO_9B.key: NEMOTRON_NANO_9B,
    LLAMA_31_8B.key: LLAMA_31_8B,
}

# ---------------------------------------------------------------------------
# Phan model cho tung agent
# ---------------------------------------------------------------------------
#   Nemotron Nano 9B V2 (OpenRouter) -> agent phai SUY LUAN / KIEM CHUNG
#   Llama 3.1 8B Instant (Groq)      -> agent chi TRA CUU + dien handoff card


@dataclass(frozen=True)
class AgentSpec:
    """Vai tro, model va quyen truy cap du lieu cua mot agent."""

    name: str
    role: str
    model: ModelSpec
    # Whitelist bang du lieu duoc doc (least privilege). Rong = khong duoc doc CSV.
    allowed_tables: tuple[str, ...] = field(default=())
    temperature: float = 0.0


AGENTS: dict[str, AgentSpec] = {
    "coordinator": AgentSpec(
        name="coordinator",
        role="Nhan ticket, giao viec cho cac agent chuyen trach, gop handoff card, assemble output.",
        model=NEMOTRON_NANO_9B,
        allowed_tables=(),
    ),
    "customer_agent": AgentSpec(
        name="customer_agent",
        role="Xac dinh customer_unique_id va lich su order khac cua cung khach hang.",
        model=LLAMA_31_8B,
        allowed_tables=("customers", "orders"),
    ),
    "order_product_agent": AgentSpec(
        name="order_product_agent",
        role="Kiem tra order status, item, seller, product va category.",
        model=LLAMA_31_8B,
        allowed_tables=("orders", "order_items", "products", "sellers", "category_translation"),
    ),
    "payment_agent": AgentSpec(
        name="payment_agent",
        role="Tong hop payment row va doi soat voi item + freight.",
        model=LLAMA_31_8B,
        allowed_tables=("order_payments", "order_items"),
    ),
    "delivery_agent": AgentSpec(
        name="delivery_agent",
        role="Tinh delivery variance va seller handoff variance.",
        model=LLAMA_31_8B,
        allowed_tables=("orders", "order_items"),
    ),
    "policy_agent": AgentSpec(
        name="policy_agent",
        role=(
            "Ap EC_POLICY_V2: primary/secondary issue, root cause, responsible party, "
            "refund va resolution actions. Khong duoc doc CSV, chi ket luan tu handoff card."
        ),
        model=NEMOTRON_NANO_9B,
        allowed_tables=(),
    ),
    "verifier_agent": AgentSpec(
        name="verifier_agent",
        role="Kiem tra ID, so tien, null handling, array limit va schema truoc khi ghi file.",
        model=NEMOTRON_NANO_9B,
        allowed_tables=(
            "orders",
            "order_items",
            "order_payments",
            "customers",
            "products",
            "sellers",
        ),
    ),
}

# ---------------------------------------------------------------------------
# Tham so nghiep vu EC_POLICY_V2 (lay tu README, khong hardcode dap an)
# ---------------------------------------------------------------------------

POLICY_VERSION = "EC_POLICY_V2"
CURRENCY = "BRL"

# README muc 4: reconciled = abs(difference_brl) <= 0.10 BRL
RECONCILE_TOLERANCE_BRL = "0.10"

# README muc 4: "Moi phep tinh tien va so gio duoc lam tron 2 chu so thap phan"
MONEY_DECIMALS = 2
HOURS_DECIMALS = 2

# Ten category lay tu cot nao.
#   "pt" -> products.product_category_name (nguyen ban trong CSV)
#   "en" -> join sang product_category_name_translation
# Mac dinh "pt": README muc 2 liet ke khoa join khong bao gom bang translation.
CATEGORY_NAME_LANGUAGE = "pt"

# ---------------------------------------------------------------------------
# Tham so LLM
# ---------------------------------------------------------------------------
# Muc tieu duy nhat cua khoi nay: KET QUA LAP LAI DUOC giua cac lan chay.
# Bai cham theo exact match nen moi nguon ngau nhien deu la rui ro mat diem.

TEMPERATURE = 0.0          # tat sampling
TOP_P = 1.0                # khong cat phan phoi khi da greedy
SEED = 42                  # Groq ho tro seed; OpenRouter bo qua neu backend khong ho tro
MAX_TOKENS = 2048
REQUEST_TIMEOUT_S = 120

# JSON mode: bat buoc model tra ve JSON hop le thay vi van xuoi lan code fence.
FORCE_JSON_MODE = True

# Nemotron Nano 9B V2 la model reasoning, dieu khien bang token /think va /no_think
# dat o dau system prompt.
#
# DO THUC TE tren bo de nay (xem bao cao ca nhan): bat /think lam hong nhieu hon la
# giup. Chuoi suy luan an chiem het max_tokens roi bi cat giua chung, JSON khong bao
# gio dong duoc -> parse hong 100%. Nang max_tokens len 3500 thi parse duoc nhung
# moi luot mat 18-45s thay vi 5-9s, ma do chinh xac KHONG tot hon: o EC_015 che do
# /think con them nham mot action ma /no_think khong them.
#
# Ket luan: tat suy luan cho ca ba agent. Do chinh xac duoc bao dam boi vong doi
# chieu voi rule engine, khong phai boi chuoi suy luan cua model 9B.
REASONING_BY_AGENT: dict[str, bool] = {
    "coordinator": False,
    "policy_agent": False,
    "verifier_agent": False,
}

MAX_RETRIES = 5            # retry khi loi mang / rate limit 429
RETRY_BACKOFF_S = 2.0      # backoff nhan doi moi lan: 2s, 4s, 8s, 16s, 32s
MAX_AGENT_RETRIES = 2      # retry khi Verifier hoac rule engine tra nguoc handoff

# So case chay song song. Nut that la OpenRouter :free chu khong phai Groq.
CONCURRENCY = 4

# --- Gioi han toc do, do tu header that cua nha cung cap --------------------
# Groq tra ve x-ratelimit-limit-tokens: 6000 (moi phut) va 14400 request/ngay.
# Nut that la TOKEN chu khong phai request -> dat nguong duoi tran mot chut.
PROVIDER_LIMITS: dict[str, dict[str, int]] = {
    "groq": {"requests_per_minute": 28, "tokens_per_minute": 5200},
    "openrouter": {"requests_per_minute": 16, "tokens_per_minute": 200_000},
}


def provider_limits(provider_key: str) -> dict[str, int]:
    return PROVIDER_LIMITS.get(
        provider_key, {"requests_per_minute": 20, "tokens_per_minute": 50_000}
    )


# --- Du phong khi mot provider het quota -----------------------------------
# Neu mot provider tra 429/402, agent chuyen sang model o PROVIDER KHAC thay vi
# lam do ca luot chay 50 case. Chuyen sang model cung provider la vo nghia vi
# quota van dang can. Moi lan chuyen deu ghi ro vao trace.jsonl, khong giau.
ENABLE_MODEL_FALLBACK = True


def fallback_model_for(model: ModelSpec):
    """Model du phong nam o provider KHAC voi model dang bi tu choi."""
    if not ENABLE_MODEL_FALLBACK:
        return None
    for candidate in MODEL_REGISTRY.values():
        if candidate.provider.key != model.provider.key:
            return candidate
    return None

ENABLE_CACHE = True        # cache response theo hash(agent, model, prompt)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def get_api_key(provider_key: str) -> str:
    """Lay API key cua mot provider theo key ('openrouter' | 'groq')."""
    return PROVIDERS[provider_key].api_key()


def models_in_use() -> list[ModelSpec]:
    """Cac model thuc su duoc gan cho agent, khong trung lap."""
    seen: dict[str, ModelSpec] = {}
    for agent in AGENTS.values():
        seen.setdefault(f"{agent.model.provider.key}/{agent.model.model_id}", agent.model)
    return list(seen.values())


def providers_in_use() -> list[ProviderSpec]:
    """Cac provider thuc su duoc dung, khong trung lap."""
    seen: dict[str, ProviderSpec] = {}
    for model in models_in_use():
        seen.setdefault(model.provider.key, model.provider)
    return list(seen.values())


def check_credentials() -> None:
    """Kiem tra du key cho moi provider dang dung. Goi truoc khi chay 50 case."""
    missing = [p.api_key_env for p in providers_in_use() if not os.environ.get(p.api_key_env, "").strip()]
    if missing:
        raise RuntimeError(f"Thieu bien moi truong: {', '.join(missing)}. Kiem tra file .env")


def build_metadata(runtime: dict | None = None) -> dict:
    """Dung noi dung metadata.json tu chinh config nay (README muc 8)."""
    used = models_in_use()
    return {
        "framework": "custom-a2a-orchestrator",
        "policy_version": POLICY_VERSION,
        "parameter_size_constraint": f"<= {MAX_PARAMETER_SIZE_B:g}B",
        "max_parameter_size_used_b": max(m.parameter_size_b for m in used),
        "providers": [
            {"key": p.key, "display_name": p.display_name, "base_url": p.base_url}
            for p in providers_in_use()
        ],
        "models": [
            {
                "model_id": m.model_id,
                "display_name": m.display_name,
                "provider": m.provider.key,
                "parameter_size_b": m.parameter_size_b,
                "context_length": m.context_length,
            }
            for m in used
        ],
        "agents": [
            {
                "name": a.name,
                "role": a.role,
                "provider": a.model.provider.key,
                "model_id": a.model.model_id,
                "parameter_size_b": a.model.parameter_size_b,
                "allowed_tables": list(a.allowed_tables),
            }
            for a in AGENTS.values()
        ],
        "runtime": runtime or {},
    }


if __name__ == "__main__":
    import json

    print(json.dumps(build_metadata(), indent=2, ensure_ascii=False))
