"""search_text — 작업 폴더 안에서 정규식으로 줄을 찾는다.

os.walk로 훑으면서 제외 디렉터리를 가지치기한다. Path.glob은 가지치기를 못 해
1.6GB짜리 .venv를 전부 훑게 되므로 쓰지 않는다.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ..contracts import ToolSpec
from ..paths import PathGuard

MAX_RESULTS_LIMIT = 500
MAX_LINE_CHARS = 400
DEFAULT_GLOB = "**/*.py"

SPEC = ToolSpec(
    name="search_text",
    description=(
        "작업 폴더 안의 파일에서 정규식과 일치하는 줄을 찾는다. "
        "파일 경로와 줄 번호를 함께 돌려주므로 read_file로 이어서 확인할 수 있다."
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "파이썬 정규식"},
            "glob": {
                "type": "string",
                "description": f"검색할 파일 패턴. **와 *를 쓸 수 있다. 기본 {DEFAULT_GLOB}",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_RESULTS_LIMIT,
                "description": f"돌려줄 최대 건수. 1~{MAX_RESULTS_LIMIT}, 기본 50",
            },
        },
        "required": ["pattern"],
        "additionalProperties": False,
    },
)


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """glob을 슬래시 구분 경로용 정규식으로 바꾼다.

    `**/`는 0개 이상의 디렉터리, `*`와 `?`는 구분자를 넘지 않는다.
    fnmatch는 `*`가 슬래시를 넘어가서 `**/*.py`가 최상위 파일을 놓치므로 쓰지 않는다.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def run(guard: PathGuard, arguments: dict[str, Any], preview_obj: object = None) -> dict[str, Any]:
    # preview_obj는 승인이 필요한 도구와 시그니처를 맞추기 위한 것이며 여기서는 쓰지 않는다.
    raw_pattern = arguments.get("pattern")
    if not isinstance(raw_pattern, str) or not raw_pattern:
        return {"error": "invalid_argument", "field": "pattern"}

    glob = arguments.get("glob", DEFAULT_GLOB)
    if not isinstance(glob, str) or not glob:
        return {"error": "invalid_argument", "field": "glob"}
    # glob으로 작업 폴더를 벗어나려는 시도를 미리 막는다.
    if ".." in glob.replace("\\", "/").split("/") or os.path.isabs(glob):
        return {"error": "invalid_argument", "field": "glob", "message": "glob은 작업 폴더 기준 상대 패턴이어야 합니다"}

    max_results = arguments.get("max_results", 50)
    if isinstance(max_results, bool) or not isinstance(max_results, int):
        return {"error": "invalid_argument", "field": "max_results"}
    if not 1 <= max_results <= MAX_RESULTS_LIMIT:
        return {"error": "invalid_argument", "field": "max_results"}

    try:
        needle = re.compile(raw_pattern)
    except re.error as exc:
        return {"error": "invalid_pattern", "message": str(exc)}

    matcher = _glob_to_regex(glob)
    matches: list[dict[str, Any]] = []
    total = 0
    files_scanned = 0

    for dirpath, dirnames, filenames in os.walk(guard.root):
        here = Path(dirpath)
        # 제외 디렉터리는 내려가지 않는다. 이것이 .venv를 훑지 않는 유일한 이유다.
        dirnames[:] = [name for name in dirnames if guard.is_allowed(here / name)]
        for filename in filenames:
            candidate = here / filename
            if not guard.is_allowed(candidate):
                continue
            relative = guard.relative(candidate)
            if not matcher.match(relative):
                continue
            files_scanned += 1
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if not needle.search(line):
                    continue
                total += 1
                if len(matches) < max_results:
                    matches.append(
                        {"path": relative, "line": number, "text": line[:MAX_LINE_CHARS]}
                    )

    return {
        "matches": matches,
        "total": total,
        "files_scanned": files_scanned,
        "truncated": total > len(matches),
    }
