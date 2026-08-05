"""Client LLM da provider, chi dung thu vien chuan cua Python.

Vi sao khong dung SDK openai: bai thi 4 tieng, them mot dependency la them mot cho
co the vo. Ca OpenRouter lan Groq deu noi giao dien /chat/completions kieu OpenAI,
mot ham urllib la du.

Ba thu quyet dinh chat luong o day:

1. THAM SO TAT NGAU NHIEN
   temperature=0, top_p=1, seed co dinh. Bai cham exact match nen moi nguon ngau
   nhien deu la rui ro. Hai lan chay phai ra cung ket qua.

2. JSON MODE
   response_format={"type":"json_object"}. Model 8-9B rat hay boc JSON trong ```json
   hoac them mot cau dan nhap -> parse hong. Neu backend tu choi tham so nay thi tu
   dong thu lai khong co no, va van co lop go code fence o duoi.

3. DIEU KHIEN SUY LUAN CUA NEMOTRON
   Nemotron Nano 9B V2 bat/tat suy luan bang token /think hoac /no_think dat o dau
   system prompt. Bat cho khau phan loai va kiem chung, tat cho khau chi can dung
   format -> JSON sach hon va it ton token hon.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src import config
from src.agents import ratelimit
from src.config import ModelSpec

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class LLMError(RuntimeError):
    """Goi LLM that bai sau khi da retry het luot."""


class LLMQuotaError(LLMError):
    """Provider tu choi vi het quota hoac qua tran request (429 / 402).

    Tach rieng khoi LLMError de tang tren biet day la truong hop DUY NHAT nen
    chuyen sang model du phong. Loi mang hay JSON hong thi khong chuyen.
    """


@dataclass
class LLMResult:
    text: str
    model_id: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    throttle_wait_ms: int = 0
    attempts: int = 1
    from_cache: bool = False
    raw_finish_reason: str = ""

    def as_trace(self) -> dict:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            # latency_ms la thoi gian HTTP thuc su; throttle_wait_ms la thoi gian
            # nam cho rate limiter. Gop chung lai se doc nham la model cham.
            "latency_ms": self.latency_ms,
            "throttle_wait_ms": self.throttle_wait_ms,
            "attempts": self.attempts,
            "from_cache": self.from_cache,
        }


# ---------------------------------------------------------------------------
# Cache tren dia
# ---------------------------------------------------------------------------


@dataclass
class ResponseCache:
    """Cache theo hash(model, prompt). Chay lai lan hai gan nhu mien phi.

    Rat quan trong khi debug: sua mot agent roi chay lai 50 case ma khong phai
    goi lai toan bo cac agent khac, va khong dot rate limit ban :free.
    """

    directory: Path = field(default_factory=lambda: Path(config.CACHE_DIR))
    enabled: bool = field(default_factory=lambda: config.ENABLE_CACHE)

    def __post_init__(self) -> None:
        if self.enabled:
            self.directory.mkdir(parents=True, exist_ok=True)

    def _key(self, model_id: str, payload: dict) -> str:
        blob = json.dumps({"model": model_id, "payload": payload}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]

    def get(self, model_id: str, payload: dict) -> dict | None:
        if not self.enabled:
            return None
        path = self.directory / f"{self._key(model_id, payload)}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def put(self, model_id: str, payload: dict, response: dict) -> None:
        if not self.enabled:
            return
        path = self.directory / f"{self._key(model_id, payload)}.json"
        try:
            path.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


_CACHE = ResponseCache()


# ---------------------------------------------------------------------------
# Goi HTTP
# ---------------------------------------------------------------------------


#: Cloudflare truoc Groq chan User-Agent mac dinh cua urllib ("Python-urllib/3.x")
#: bang loi 403 error code 1010. Phai dat User-Agent that.
_USER_AGENT = "K4-Day9-Multi-Agent-A2A/1.0 (+python-stdlib)"


def _headers(model: ModelSpec) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {model.provider.api_key()}",
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    }
    if model.provider.key == "openrouter":
        import os

        site = os.environ.get("OPENROUTER_SITE_URL", "").strip()
        app = os.environ.get("OPENROUTER_APP_NAME", "").strip()
        if site:
            headers["HTTP-Referer"] = site
        if app:
            headers["X-Title"] = app
    return headers


def _post(model: ModelSpec, payload: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        url=f"{model.provider.base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(model),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_payload(
    model: ModelSpec, system: str, user: str, json_mode: bool, max_tokens: int
) -> dict:
    payload: dict[str, Any] = {
        "model": model.model_id,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": config.TEMPERATURE,
        "top_p": config.TOP_P,
        "max_tokens": max_tokens,
    }
    if config.SEED is not None:
        payload["seed"] = config.SEED
    if json_mode and config.FORCE_JSON_MODE:
        payload["response_format"] = {"type": "json_object"}
    return payload


def complete(
    model: ModelSpec,
    system: str,
    user: str,
    *,
    json_mode: bool = True,
    max_tokens: int | None = None,
) -> LLMResult:
    """Goi mot luot chat. Retry co backoff cho 429 va 5xx."""
    payload = _build_payload(
        model, system, user, json_mode, max_tokens or config.MAX_TOKENS
    )

    cached = _CACHE.get(model.model_id, payload)
    if cached is not None:
        return LLMResult(
            text=cached.get("text", ""),
            model_id=model.model_id,
            provider=model.provider.key,
            prompt_tokens=cached.get("prompt_tokens", 0),
            completion_tokens=cached.get("completion_tokens", 0),
            latency_ms=0,
            attempts=0,
            from_cache=True,
            raw_finish_reason=cached.get("finish_reason", ""),
        )

    limits = config.provider_limits(model.provider.key)
    limiter = ratelimit.limiter_for(
        model.provider.key, limits["requests_per_minute"], limits["tokens_per_minute"]
    )
    # Uoc luong ca prompt lan phan sinh ra, vi tran TPM cua Groq tinh ca hai.
    estimated = ratelimit.estimate_tokens(system) + ratelimit.estimate_tokens(user) + 256

    last_error: Exception | None = None
    delay = config.RETRY_BACKOFF_S
    throttle_wait = 0.0

    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            throttle_wait += limiter.acquire(estimated)
            started = time.time()
            data = _post(model, payload, config.REQUEST_TIMEOUT_S)
            choice = (data.get("choices") or [{}])[0]
            text = (choice.get("message") or {}).get("content") or ""
            usage = data.get("usage") or {}
            result = LLMResult(
                text=text,
                model_id=model.model_id,
                provider=model.provider.key,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                latency_ms=int((time.time() - started) * 1000),
                throttle_wait_ms=int(throttle_wait * 1000),
                attempts=attempt,
                raw_finish_reason=choice.get("finish_reason") or "",
            )
            limiter.record_actual(
                estimated, result.prompt_tokens + result.completion_tokens
            )
            _CACHE.put(
                model.model_id,
                payload,
                {
                    "text": result.text,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "finish_reason": result.raw_finish_reason,
                },
            )
            return result

        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:  # noqa: BLE001 - doc body loi la best effort
                pass
            last_error = LLMError(f"HTTP {exc.code} tu {model.provider.key}: {body}")

            # Backend tu choi response_format -> bo tham so va thu lai ngay.
            if exc.code == 400 and "response_format" in body and "response_format" in payload:
                payload.pop("response_format")
                continue

            # 402 = het credit, 429 = qua tran request. Bao rieng de tang tren
            # chuyen sang model du phong thay vi cu backoff vo ich.
            if exc.code in (402, 429):
                quota_error = LLMQuotaError(
                    f"HTTP {exc.code} tu {model.provider.key} (het quota hoac qua tran): {body}"
                )
                if exc.code == 402:
                    raise quota_error from exc
                last_error = quota_error

            # 5xx la loi tam thoi -> backoff. Cac ma con lai do het ngay.
            elif exc.code < 500:
                raise last_error from exc

        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            # OSError bao gom http.client.RemoteDisconnected ("Remote end closed
            # connection without response") -- gap that su voi ban :free khi tai cao.
            last_error = LLMError(f"Loi mang toi {model.provider.key}: {exc}")

        if attempt < config.MAX_RETRIES:
            time.sleep(delay)
            delay *= 2

    raise last_error or LLMError("Goi LLM that bai khong ro nguyen nhan")


# ---------------------------------------------------------------------------
# Parse JSON tu output cua model nho
# ---------------------------------------------------------------------------


def parse_json(text: str) -> dict | None:
    """Rut JSON tu output cua model 8-9B, chiu duoc cac kieu boc pho bien.

    Da gap: bao quanh bang ```json, them mot cau dan truoc JSON, va voi model
    reasoning thi con them khoi <think>...</think> o dau.
    """
    if not text:
        return None

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    fence = _JSON_FENCE_RE.search(cleaned)
    if fence:
        try:
            parsed = json.loads(fence.group(1))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

    # Lay khoi ngoac nhon can bang dau tien.
    start = cleaned.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(cleaned[start : index + 1])
                    return parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


def reasoning_prefix(agent_name: str, model: ModelSpec) -> str:
    """Token dieu khien suy luan cua Nemotron, dat o dau system prompt."""
    if "nemotron" not in model.model_id.lower():
        return ""
    want_reasoning = config.REASONING_BY_AGENT.get(agent_name, False)
    return "/think\n" if want_reasoning else "/no_think\n"


__all__ = ["LLMError", "LLMResult", "ResponseCache", "complete", "parse_json", "reasoning_prefix"]
