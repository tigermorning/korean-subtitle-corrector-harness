"""write_file — 승인 후에만 적용한다(D06, R04·R05).

기존 파일 덮어쓰기와 새 파일 생성을 둘 다 허용한다(2026-09-08 결정 변경, DECISIONS.md 참고).
원래는 기존 파일만 바꾸도록 좁혔었는데, R08 벤치마크 A11 실측에서 고정 10문항 전부가
새 출력 파일 생성을 요구해 0/10이 나오는 것을 확인했다. 새 파일이라도 상위 폴더는 미리
있어야 한다 — 없는 상위 폴더까지 만들면 작업 폴더 어디에나 새 디렉터리 구조를 통째로
뿌릴 수 있어 승인 화면 한 장이 감당하는 변경 범위가 너무 커진다.
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import Any

from ..contracts import Preview, ToolSpec
from ..paths import PathGuard, PathRejected

SPEC = ToolSpec(
    name="write_file",
    description=(
        "작업 폴더 안의 파일 내용을 통째로 바꾸거나(기존 파일) 새로 만든다(새 파일). "
        "새 파일이라도 상위 폴더는 이미 있어야 한다. "
        "사용자 승인을 받은 뒤에만 적용된다. 기존 파일을 바꿀 때는 read_file로 현재 내용을 반드시 먼저 확인한다."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "작업 폴더 기준 상대 경로. 새 파일도 되지만 상위 폴더는 이미 있어야 함"},
            "content": {"type": "string", "description": "파일 전체를 대체하거나 새로 채울 내용"},
            "why": {"type": "string", "description": "이 변경이 필요한 이유 한 줄"},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
)

# 파일이 아직 없는 상태를 나타내는 표식. 빈 문자열("")과 구별해야 한다 —
# "빈 파일을 덮어씀"과 "새로 만듦"은 다른 사건이고 stale_approval 판정도 갈려야 한다.
_ABSENT = b"\x00__ABSENT__\x00"


def _digest(old_text: str | None, new_text: str) -> str:
    old_bytes = _ABSENT if old_text is None else old_text.encode("utf-8")
    payload = old_bytes + b"\x00" + new_text.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def preview(guard: PathGuard, arguments: dict[str, Any]) -> Preview | dict[str, Any]:
    new_text = arguments.get("content")
    if not isinstance(new_text, str):
        return {"error": "invalid_argument", "field": "content"}

    try:
        target = guard.resolve(arguments.get("path", ""))
    except PathRejected as rejected:
        return {"error": rejected.code, "message": rejected.message, **rejected.extra}

    is_new = not target.exists()
    if is_new and not target.parent.is_dir():
        return {"error": "parent_missing", "message": "상위 폴더가 없습니다. 새 폴더는 만들지 않습니다"}
    if not is_new and not target.is_file():
        return {"error": "not_a_file", "message": "파일이 아닙니다"}

    old_text: str | None = None
    if not is_new:
        try:
            old_text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return {"error": "read_failed", "message": str(exc)}

    if old_text == new_text:
        return {"error": "no_change", "message": "내용이 같아 바꿀 것이 없습니다"}

    relative = guard.relative(target)
    diff = "\n".join(
        difflib.unified_diff(
            (old_text or "").splitlines(),
            new_text.splitlines(),
            fromfile="/dev/null" if is_new else f"a/{relative}",
            tofile=f"b/{relative}",
            lineterm="",
        )
    )
    why = arguments.get("why")
    summary = f"{relative} {'생성' if is_new else '수정'}"
    if isinstance(why, str) and why.strip():
        summary += f" — {why.strip()}"

    return Preview(
        kind="write",
        summary=summary,
        detail=diff,
        digest=_digest(old_text, new_text),
        payload={"target": str(target), "relative": relative, "new_text": new_text, "is_new": is_new},
    )


def run(guard: PathGuard, arguments: dict[str, Any], preview_obj: Preview | None = None) -> dict[str, Any]:
    if preview_obj is None:  # 승인 없이 부를 수 없다
        return {"error": "approval_required", "message": "승인 절차를 거치지 않은 호출입니다"}

    target = Path(preview_obj.payload["target"])
    new_text = preview_obj.payload["new_text"]

    # 보여 준 뒤 상태(파일 없음/기존 내용)가 바뀌었으면 그 승인은 다른 내용에 대한 것이다.
    current: str | None = None
    if target.exists():
        try:
            current = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return {"error": "read_failed", "message": str(exc)}
    if _digest(current, new_text) != preview_obj.digest:
        return {
            "error": "stale_approval",
            "message": "승인 화면을 보여 준 뒤 파일 상태가 바뀌었습니다. 다시 읽고 다시 제안하세요",
        }

    try:
        target.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        return {"error": "write_failed", "message": str(exc)}

    return {
        "applied": True,
        "path": preview_obj.payload["relative"],
        "bytes": len(new_text.encode("utf-8")),
        "created": preview_obj.payload["is_new"],
    }
