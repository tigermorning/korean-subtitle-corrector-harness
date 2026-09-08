"""승인 흐름 (D06).

읽기·검색은 자동, 쓰기와 명령 실행만 건별 승인이다.
승인은 특정 도구 호출의 특정 내용에 묶인다. 보여 준 내용이 바뀌면 그 승인을 재사용하지 않는다.

기본값은 거절이다. 입력을 받을 수 없는 환경(파이프·CI)에서 승인을 물었다면
사람이 본 적이 없다는 뜻이므로 통과시키지 않는다.
"""

from __future__ import annotations

import sys
from typing import Protocol

from .contracts import Preview

DETAIL_LINE_LIMIT = 60


class Approver(Protocol):
    def ask(self, preview: Preview) -> bool: ...


class AlwaysReject:
    """비대화 환경의 기본값. 물어볼 수 없으면 거절한다."""

    reason = "no_interactive_input"

    def ask(self, preview: Preview) -> bool:
        return False


class ConsoleApprover:
    """터미널에서 y/n을 받는다."""

    reason = "console"

    def __init__(self, stream=None, prompt_stream=None) -> None:
        self._in = stream if stream is not None else sys.stdin
        self._out = prompt_stream if prompt_stream is not None else sys.stdout

    def ask(self, preview: Preview) -> bool:
        write = self._out.write
        write("\n" + "=" * 60 + "\n")
        write(f"승인 요청 ({preview.kind}): {preview.summary}\n")
        write("-" * 60 + "\n")
        write(_clip(preview.detail) + "\n")
        write("=" * 60 + "\n")
        write("적용할까요? [y/N] ")
        self._out.flush()

        answer = self._in.readline()
        if not answer:  # EOF — 사람이 답한 적이 없다
            write("\n입력이 없어 거절로 처리합니다.\n")
            return False
        decided = answer.strip().lower() in {"y", "yes"}
        write(("승인했습니다.\n" if decided else "거절했습니다.\n"))
        self._out.flush()
        return decided


class ScriptedApprover:
    """테스트용. 미리 정한 답을 순서대로 돌려준다."""

    reason = "scripted"

    def __init__(self, answers: list[bool], default: bool = False) -> None:
        self.answers = list(answers)
        self.default = default
        self.seen: list[Preview] = []

    def ask(self, preview: Preview) -> bool:
        self.seen.append(preview)
        if self.answers:
            return self.answers.pop(0)
        return self.default


def _clip(detail: str, limit: int = DETAIL_LINE_LIMIT) -> str:
    lines = detail.splitlines()
    if len(lines) <= limit:
        return detail
    hidden = len(lines) - limit
    return "\n".join(lines[:limit] + [f"... ({hidden}줄 더 있음. 전체는 세션 기록에 남습니다)"])
