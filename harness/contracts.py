"""제공자와 무관한 내부 계약 타입.

INTERFACES.md "모델 제공자 연결부"의 표와 1:1로 대응한다.
어댑터는 각 제공자의 요청·응답을 이 타입으로 변환하고, 루프는 제공자를 모른 채 이것만 다룬다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ToolCall:
    """모델이 요청한 도구 호출 하나.

    id는 제공자가 준 값을 그대로 보관한다. 하네스가 새로 만들지 않는다.
    arguments가 None이면 제공자가 준 문자열이 JSON이 아니었다는 뜻이며,
    이 경우 도구를 실행하지 않고 bad_arguments 오류를 결과로 돌려준다.
    """

    id: str
    name: str
    arguments: dict[str, Any] | None
    raw_arguments: str = ""


@dataclass(frozen=True)
class Message:
    role: Role
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass(frozen=True)
class ModelReply:
    text: str | None
    tool_calls: tuple[ToolCall, ...]
    finish_reason: str
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Preview:
    """승인이 필요한 도구가 "적용 전에 보여 줄 것"을 담는다.

    digest는 사용자에게 실제로 보여 준 내용의 해시다. 적용 직전에 다시 계산해
    값이 다르면 그 사이 파일이 바뀐 것이므로 승인을 재사용하지 않는다(INTERFACES.md).
    payload는 도구가 적용할 때 쓰는 값이며 사용자에게 보여 주지 않는다.
    """

    kind: str  # "write" | "exec"
    summary: str
    detail: str
    digest: str
    payload: dict[str, Any]


class AdapterError(Exception):
    """제공자 연결부의 실패.

    retryable이 True인 것만 루프가 재시도한다(네트워크·5xx).
    인증 오류와 4xx는 재시도하지 않는다.
    """

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
