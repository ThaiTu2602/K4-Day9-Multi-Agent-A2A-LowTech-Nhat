"""Rate limiter theo tung provider, dung mo hinh token bucket nap lai lien tuc.

Do duoc tu header that cua nha cung cap:

  Groq  llama-3.1-8b-instant : 14400 request/ngay, 6000 TOKEN/PHUT
                               -> nut that la TOKEN, khong phai so request
  OpenRouter ban :free       : gioi han theo so request moi phut

VI SAO LA TOKEN BUCKET CHU KHONG PHAI CUA SO TRUOT 60 GIAY:
Header cua Groq tra ve `x-ratelimit-remaining-tokens: 5959` va
`x-ratelimit-reset-tokens: 410ms` ngay sau mot luot dung 41 token. 41 token hoi lai
trong 410ms nghia la bucket nap lai lien tuc voi toc do 6000/60 = 100 token/giay,
chu khong phai xa mot lan sau moi 60 giay.

Ban dau code nay dung cua so truot 60 giay va do duoc 1326 giay nam cho tren 40 luot
goi, trong khi thoi gian HTTP that chi 0.9 giay moi luot. Doi sang token bucket thi
chi phai cho dung phan token chua kip nap lai.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

WINDOW_S = 60.0


@dataclass
class TokenBucketLimiter:
    """Hai bucket song song: so request va so token, deu nap lai lien tuc."""

    name: str
    max_requests: int
    max_tokens: int
    _request_credit: float = field(default=0.0)
    _token_credit: float = field(default=0.0)
    _last_refill: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _total_wait_s: float = field(default=0.0)

    def __post_init__(self) -> None:
        # Bat dau day bucket: chua goi lan nao thi chua tieu gi.
        self._request_credit = float(self.max_requests)
        self._token_credit = float(self.max_tokens)

    def _refill(self, now: float) -> None:
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._request_credit = min(
            self.max_requests, self._request_credit + self.max_requests * elapsed / WINDOW_S
        )
        self._token_credit = min(
            self.max_tokens, self._token_credit + self.max_tokens * elapsed / WINDOW_S
        )
        self._last_refill = now

    def acquire(self, estimated_tokens: int) -> float:
        """Cho toi khi du credit, tru di, roi tra ve so giay da phai cho."""
        # Mot luot goi khong bao gio duoc doi hoi nhieu hon suc chua cua bucket,
        # neu khong se cho vo han.
        need_tokens = min(float(estimated_tokens), float(self.max_tokens))
        waited = 0.0

        while True:
            with self._lock:
                now = time.time()
                self._refill(now)

                if self._request_credit >= 1.0 and self._token_credit >= need_tokens:
                    self._request_credit -= 1.0
                    self._token_credit -= need_tokens
                    self._total_wait_s += waited
                    return waited

                # Cho dung bang thoi gian nap lai phan con thieu.
                request_gap = max(0.0, 1.0 - self._request_credit) * WINDOW_S / self.max_requests
                token_gap = (
                    max(0.0, need_tokens - self._token_credit) * WINDOW_S / self.max_tokens
                )
                sleep_for = max(0.05, request_gap, token_gap)

            time.sleep(sleep_for)
            waited += sleep_for

    def record_actual(self, estimated_tokens: int, actual_tokens: int) -> None:
        """Hieu chinh bucket bang so token that trong response.

        Uoc luong thap hon thuc te thi tru them; cao hon thi hoan lai. Nho vay
        sai so uoc luong khong tich luy qua hang tram luot goi.
        """
        if actual_tokens <= 0:
            return
        with self._lock:
            delta = float(actual_tokens - min(estimated_tokens, self.max_tokens))
            self._token_credit = max(
                0.0, min(float(self.max_tokens), self._token_credit - delta)
            )

    def snapshot(self) -> dict:
        with self._lock:
            self._refill(time.time())
            return {
                "provider": self.name,
                "request_credit": round(self._request_credit, 1),
                "token_credit": round(self._token_credit, 1),
                "max_requests_per_minute": self.max_requests,
                "max_tokens_per_minute": self.max_tokens,
                "total_throttle_wait_s": round(self._total_wait_s, 1),
            }


_LIMITERS: dict[str, TokenBucketLimiter] = {}
_REGISTRY_LOCK = threading.Lock()


def limiter_for(provider_key: str, max_requests: int, max_tokens: int) -> TokenBucketLimiter:
    """Mot limiter dung chung cho moi luong, theo tung provider."""
    with _REGISTRY_LOCK:
        existing = _LIMITERS.get(provider_key)
        if existing is None:
            existing = TokenBucketLimiter(provider_key, max_requests, max_tokens)
            _LIMITERS[provider_key] = existing
        return existing


def all_snapshots() -> list[dict]:
    with _REGISTRY_LOCK:
        return [limiter.snapshot() for limiter in _LIMITERS.values()]


def estimate_tokens(text: str) -> int:
    """Uoc luong tho: 1 token ~ 4 ky tu. Du chinh xac de dieu tiet."""
    return max(1, len(text) // 4)


__all__ = ["TokenBucketLimiter", "limiter_for", "all_snapshots", "estimate_tokens"]
