"""Ghi trace.jsonl: mot dong cho moi buoc cua moi agent.

README muc 8: "trace.jsonl: trace chay that cua 50 case (khong append, chi can luot
chay moi nhat)" -> mo file mode 'w' mot lan khi bat dau run, khong append qua cac lan.

Trace chay song song nen moi lan ghi deu qua lock. Khong bao gio ghi API key.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from src import config


class TraceWriter:
    """Ghi JSONL an toan da luong."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or config.TRACE_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = 0
        # mode 'w': xoa trace cu, chi giu luot chay moi nhat.
        self._handle = self.path.open("w", encoding="utf-8")

    def emit(self, **fields: Any) -> None:
        with self._lock:
            self._seq += 1
            record = {
                "seq": self._seq,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                **fields,
            }
            self._handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._handle.flush()

    def close(self) -> None:
        with self._lock:
            if not self._handle.closed:
                self._handle.close()

    def __enter__(self) -> "TraceWriter":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class NullTrace:
    """Dung khi chay test hoac duong tham chieu, khong sinh file."""

    def emit(self, **fields: Any) -> None:  # noqa: D102
        return

    def close(self) -> None:  # noqa: D102
        return


__all__ = ["TraceWriter", "NullTrace"]
