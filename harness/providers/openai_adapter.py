"""OpenAI 어댑터.

제공자의 요청·응답을 contracts.py의 내부 계약으로 변환하는 유일한 자리다.
루프는 이 파일 밖에서 OpenAI라는 사실을 모른다.

API 키는 OPENAI_API_KEY 환경변수에서만 읽는다. 값을 반환하거나 기록하지 않는다.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..contracts import AdapterError, Message, ModelReply, ToolCall, ToolSpec

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIAdapter:
    def __init__(self, model: str = DEFAULT_MODEL, timeout: float = 60.0) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - 의존성 미설치 환경
            raise AdapterError(
                "missing_dependency",
                "openai 패키지가 필요합니다. pip install -r requirements.txt",
            ) from exc

        if not os.environ.get("OPENAI_API_KEY"):
            raise AdapterError(
                "missing_api_key",
                "OPENAI_API_KEY 환경변수가 없습니다. 키를 소스나 문서에 넣지 말고 환경변수로 설정하세요.",
            )

        self.model = model
        self._client = OpenAI(timeout=timeout)

    def complete(self, messages: list[Message], tools: list[ToolSpec]) -> ModelReply:
        import openai

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[_to_openai_message(message) for message in messages],
                tools=[_to_openai_tool(spec) for spec in tools],
                tool_choice="auto",
            )
        except openai.AuthenticationError as exc:
            raise AdapterError("auth_failed", str(exc), retryable=False) from exc
        except openai.BadRequestError as exc:
            raise AdapterError("bad_request", str(exc), retryable=False) from exc
        except openai.NotFoundError as exc:
            raise AdapterError("model_not_found", str(exc), retryable=False) from exc
        except (openai.APIConnectionError, openai.APITimeoutError) as exc:
            raise AdapterError("network_error", str(exc), retryable=True) from exc
        except (openai.RateLimitError, openai.InternalServerError) as exc:
            raise AdapterError("provider_unavailable", str(exc), retryable=True) from exc

        choice = response.choices[0]
        calls: list[ToolCall] = []
        for raw in choice.message.tool_calls or []:
            calls.append(_to_tool_call(raw))

        usage = {}
        if response.usage is not None:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return ModelReply(
            text=choice.message.content,
            tool_calls=tuple(calls),
            finish_reason=choice.finish_reason or "",
            usage=usage,
        )


def _to_tool_call(raw: Any) -> ToolCall:
    raw_arguments = raw.function.arguments or ""
    try:
        parsed = json.loads(raw_arguments) if raw_arguments else {}
        # 최상위가 객체가 아니면 도구 인자로 쓸 수 없다.
        if not isinstance(parsed, dict):
            parsed = None
    except json.JSONDecodeError:
        # 실행하지 않고 bad_arguments로 모델에 돌려준다(INTERFACES.md).
        parsed = None
    return ToolCall(id=raw.id, name=raw.function.name, arguments=parsed, raw_arguments=raw_arguments)


def _to_openai_message(message: Message) -> dict[str, Any]:
    if message.role == "assistant":
        row: dict[str, Any] = {"role": "assistant", "content": message.content}
        if message.tool_calls:
            row["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.raw_arguments
                        or json.dumps(call.arguments or {}, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        return row
    if message.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content or "",
        }
    return {"role": message.role, "content": message.content or ""}


def _to_openai_tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }
