"""모의 어댑터 — 실제 모델을 부르지 않는다(--dry-run).

모델 호출 전에 하네스 자체가 옳은지 먼저 확인하기 위한 것이다.
ACCEPTANCE.md의 A02·A05·A06·A07(a)를 이 어댑터로 검증한다.
여기서 나온 결과를 실제 모델 실행처럼 기록하지 않는다.
"""

from __future__ import annotations

import itertools
from typing import Iterable

from ..contracts import Message, ModelReply, ToolCall, ToolSpec

_counter = itertools.count(1)


def tool_reply(name: str, arguments: dict | None, *, raw: str = "", text: str | None = None) -> ModelReply:
    return ModelReply(
        text=text,
        tool_calls=(ToolCall(id=f"mock-{next(_counter)}", name=name, arguments=arguments, raw_arguments=raw),),
        finish_reason="tool_calls",
        usage={},
    )


def final_reply(text: str) -> ModelReply:
    return ModelReply(text=text, tool_calls=(), finish_reason="stop", usage={})


class MockAdapter:
    """미리 정한 응답을 순서대로 돌려준다.

    script를 다 쓰면 last_reply를 계속 돌려준다. 상한 검증에 쓴다.
    """

    def __init__(self, script: Iterable[ModelReply], repeat_last: bool = False) -> None:
        self.script = list(script)
        self.repeat_last = repeat_last
        self.calls = 0

    def complete(self, messages: list[Message], tools: list[ToolSpec]) -> ModelReply:
        index = self.calls
        self.calls += 1
        if index < len(self.script):
            return self.script[index]
        if self.repeat_last and self.script:
            return self.script[-1]
        return final_reply("(모의 어댑터: 더 이상 스크립트가 없습니다)")


DEFAULT_DEMO_SCRIPT = [
    tool_reply("search_text", {"pattern": "def ", "glob": "**/*.py", "max_results": 5}),
    final_reply("모의 어댑터 실행입니다. 실제 모델을 부르지 않았습니다."),
]
