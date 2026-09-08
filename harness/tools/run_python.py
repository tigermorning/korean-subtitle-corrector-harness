"""run_python — 작업 폴더 안의 기존 .py 파일 실행 (2026-09-08 결정 변경, DECISIONS.md).

R08 벤치마크 A11·A12 실측에서, write_file로 새 파일까지 만들 수 있게 돼도
그 스크립트를 실행할 도구가 없어 산출물이 끝내 안 생기는 것을 확인하고 추가했다.

임의 셸 명령이 아니다. 실행 파일은 현재 파이썬(sys.executable)으로 고정하고,
대상은 작업 폴더 안에 이미 있는 .py 파일 하나뿐이며, 인자는 문자열 배열로만 받아
셸을 거치지 않고(shell=False) 그대로 argv에 넣는다. 인라인 코드 실행(-c)이나
표준입력으로 코드를 흘려 넣는 방식은 지원하지 않는다.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from typing import Any

from ..contracts import Preview, ToolSpec
from ..paths import PathGuard, PathRejected

TIMEOUT_SECONDS = 30
STDOUT_TAIL_CHARS = 4000
MAX_ARGS = 20

SPEC = ToolSpec(
    name="run_python",
    description=(
        "작업 폴더 안에 이미 있는 .py 파일 하나를 현재 파이썬으로 실행한다. "
        "인라인 코드나 셸 명령은 실행할 수 없다. 사용자 승인을 받은 뒤에만 실행된다."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "작업 폴더 기준 상대 경로. 이미 있는 .py 파일만"},
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "스크립트에 그대로 전달할 문자열 인자 목록. 생략하면 빈 배열",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
)


def preview(guard: PathGuard, arguments: dict[str, Any]) -> Preview | dict[str, Any]:
    try:
        target = guard.resolve(arguments.get("path", ""))
    except PathRejected as rejected:
        return {"error": rejected.code, "message": rejected.message, **rejected.extra}

    if not target.exists():
        return {"error": "not_found", "message": "실행할 파일이 없습니다"}
    if not target.is_file():
        return {"error": "not_a_file", "message": "파일이 아닙니다"}
    if target.suffix != ".py":
        return {"error": "invalid_argument", "field": "path", "message": ".py 파일만 실행합니다"}

    args = arguments.get("args", [])
    if args is None:
        args = []
    if not isinstance(args, list) or len(args) > MAX_ARGS or not all(isinstance(a, str) for a in args):
        return {"error": "invalid_argument", "field": "args", "message": f"문자열 배열이어야 하고 최대 {MAX_ARGS}개까지입니다"}

    relative = guard.relative(target)
    argv = [sys.executable, relative, *args]
    command_line = " ".join(argv)
    detail = f"실행할 명령: {command_line}\n작업 디렉터리: {guard.root}\n시간 상한: {TIMEOUT_SECONDS}초"

    return Preview(
        kind="exec",
        summary=f"python {relative}" + (f" {' '.join(args)}" if args else ""),
        detail=detail,
        digest=hashlib.sha256(f"{command_line}|{guard.root}".encode("utf-8")).hexdigest(),
        payload={"argv": argv, "command_line": command_line},
    )


def run(guard: PathGuard, arguments: dict[str, Any], preview_obj: Preview | None = None) -> dict[str, Any]:
    if preview_obj is None:
        return {"error": "approval_required", "message": "승인 절차를 거치지 않은 호출입니다"}

    argv = preview_obj.payload["argv"]
    try:
        completed = subprocess.run(
            argv,
            cwd=str(guard.root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            shell=False,  # 명시적으로 셸을 거치지 않는다
        )
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "message": f"{TIMEOUT_SECONDS}초 안에 끝나지 않아 중단했습니다"}
    except OSError as exc:
        return {"error": "exec_failed", "message": str(exc)}

    output = (completed.stdout or "") + (completed.stderr or "")
    return {
        "command": preview_obj.payload["command_line"],
        "exit_code": completed.returncode,
        "stdout_tail": output[-STDOUT_TAIL_CHARS:],
    }
