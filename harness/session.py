"""세션 기록.

INTERFACES.md "세션 기록 형식"의 이벤트 표를 그대로 쓴다.
재개는 구현하지 않는다(D07). 이 파일은 A/B 비교와 R08 제출의 원본 결과물이다.

API 키와 키가 담긴 환경변수 값은 어떤 이벤트에도 넣지 않는다.
어댑터가 키를 os.environ에서 직접 읽고, 이 모듈은 키를 인자로 받지 않는다.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SESSION_DIR = Path(__file__).resolve().parent / ".sessions"


def new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


class SessionRecorder:
    def __init__(self, session_id: str, directory: Path | None = None) -> None:
        self.session_id = session_id
        self.directory = Path(directory) if directory else DEFAULT_SESSION_DIR
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / f"{session_id}.jsonl"
        self.started_at = time.monotonic()

    def record(self, event: str, **fields: Any) -> None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at


def read_session(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
