"""run_pytest — 제한된 테스트 실행(R04).

임의 셸 명령이 아니다. 실행 파일은 현재 파이썬의 pytest로 고정하고,
인자는 검사한 값만 배열로 넘기며 셸을 거치지 않는다(shell=False).
사용자가 승인 화면에서 실제 명령줄과 작업 디렉터리를 본다.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from typing import Any

from ..contracts import Preview, ToolSpec
from ..paths import PathGuard, PathRejected

TIMEOUT_SECONDS = 120
STDOUT_TAIL_CHARS = 4000
# -k 표현식 화이트리스트. 이름·공백·and/or/not·괄호만 허용한다.
SELECT_PATTERN = re.compile(r"^[A-Za-z0-9_\s()\[\]\-.:]+$")

SPEC = ToolSpec(
    name="run_pytest",
    description=(
        "작업 폴더에서 지정한 테스트 파일만 pytest로 실행한다. "
        "사용자 승인을 받은 뒤에만 실행된다. 임의 셸 명령은 실행할 수 없다."
    ),
    parameters={
        "type": "object",
        "properties": {
            "test_path": {"type": "string", "description": "작업 폴더 기준 테스트 파일 또는 폴더 경로"},
            "test_name": {
                "type": "string",
                "description": "선택. pytest -k 표현식. 이름과 and/or/not만 쓸 수 있다",
            },
        },
        "required": ["test_path"],
        "additionalProperties": False,
    },
)


def preview(guard: PathGuard, arguments: dict[str, Any]) -> Preview | dict[str, Any]:
    try:
        target = guard.resolve(arguments.get("test_path", ""))
    except PathRejected as rejected:
        return {"error": rejected.code, "message": rejected.message, **rejected.extra}

    if not target.exists():
        return {"error": "not_found", "message": "테스트 경로가 없습니다"}

    relative = guard.relative(target)
    argv = [sys.executable, "-m", "pytest", relative, "-q"]

    select = arguments.get("test_name")
    if select is not None:
        if not isinstance(select, str) or not select.strip():
            return {"error": "invalid_argument", "field": "test_name"}
        if not SELECT_PATTERN.match(select):
            return {
                "error": "invalid_argument",
                "field": "test_name",
                "message": "-k 표현식에 허용되지 않는 문자가 있습니다",
            }
        argv += ["-k", select]

    command_line = " ".join(argv)
    detail = f"실행할 명령: {command_line}\n작업 디렉터리: {guard.root}\n시간 상한: {TIMEOUT_SECONDS}초"
    return Preview(
        kind="exec",
        summary=f"pytest {relative}" + (f" -k {select}" if select else ""),
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
    counts = _parse_counts(output)
    return {
        "command": preview_obj.payload["command_line"],
        "exit_code": completed.returncode,
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0) + counts.get("error", 0),
        "stdout_tail": output[-STDOUT_TAIL_CHARS:],
    }


def _parse_counts(output: str) -> dict[str, int]:
    """pytest -q 요약줄에서 건수를 뽑는다. 못 뽑으면 0으로 둔다."""
    counts: dict[str, int] = {}
    for number, label in re.findall(r"(\d+)\s+(passed|failed|error|errors|skipped)", output):
        key = "error" if label.startswith("error") else label
        counts[key] = counts.get(key, 0) + int(number)
    return counts
