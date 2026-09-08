"""read_file — INTERFACES.md "구체적 계약 한 개"의 구현."""

from __future__ import annotations

from typing import Any

from ..contracts import ToolSpec
from ..paths import PathGuard, PathRejected

MAX_LINES_LIMIT = 500

SPEC = ToolSpec(
    name="read_file",
    description=(
        "작업 폴더 안의 텍스트 파일을 줄 단위로 읽는다. "
        "항상 total_lines를 함께 돌려주므로 이어서 읽을 위치를 알 수 있다."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "작업 폴더 기준 상대 경로"},
            "start_line": {"type": "integer", "minimum": 1, "description": "1부터 시작. 기본 1"},
            "max_lines": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_LINES_LIMIT,
                "description": f"한 번에 읽을 줄 수. 1~{MAX_LINES_LIMIT}, 기본 200",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
)


def _int_arg(arguments: dict[str, Any], field: str, default: int, low: int, high: int) -> int:
    value = arguments.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(field)
    if not low <= value <= high:
        raise ValueError(field)
    return value


def run(guard: PathGuard, arguments: dict[str, Any], preview_obj: object = None) -> dict[str, Any]:
    # preview_obj는 승인이 필요한 도구와 시그니처를 맞추기 위한 것이며 여기서는 쓰지 않는다.
    try:
        start_line = _int_arg(arguments, "start_line", 1, 1, 10_000_000)
        max_lines = _int_arg(arguments, "max_lines", 200, 1, MAX_LINES_LIMIT)
    except ValueError as exc:
        return {"error": "invalid_argument", "field": str(exc)}

    try:
        target = guard.resolve(arguments.get("path", ""))
    except PathRejected as rejected:
        return {"error": rejected.code, "message": rejected.message, **rejected.extra}

    if not target.exists():
        return {"error": "not_found", "message": "파일이 없습니다"}
    if not target.is_file():
        return {"error": "not_a_file", "message": "파일이 아닙니다"}

    try:
        # 손상된 바이트가 있어도 실패시키지 않는다. 모델이 읽고 판단하도록 대체 문자로 넘긴다.
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": "read_failed", "message": str(exc)}

    lines = text.splitlines()
    total = len(lines)
    begin = start_line - 1
    chunk = lines[begin : begin + max_lines]
    end_line = begin + len(chunk)

    return {
        "path": guard.relative(target),
        "start_line": start_line,
        "end_line": end_line,
        "total_lines": total,
        "truncated": end_line < total,
        "content": "\n".join(chunk),
    }
