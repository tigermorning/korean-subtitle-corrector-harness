"""반복 루프.

모델 호출 → 도구 요청 파싱 → 인자·경로 검사 → 실행 → 결과를 모델에 반환을 직접 구현한다(R02).
기존 에이전트 CLI나 Agent SDK에 이 반복을 위임하지 않는다.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from .approval import AlwaysReject, Approver
from .contracts import AdapterError, Message, ModelReply, Preview, ToolCall, ToolSpec
from .paths import PathGuard
from .session import SessionRecorder
from .tools import GUARD_ERRORS, Tool

DEFAULT_MAX_ITERATIONS = 20
DEFAULT_MAX_SECONDS = 300.0
RETRY_LIMIT = 3
REPEAT_THRESHOLD = 3

SYSTEM_PROMPT = """너는 로컬 코드베이스를 조사하는 보조자다.

규칙:
- 파일 내용을 추측하지 않는다. 반드시 도구로 읽은 것만 근거로 삼는다.
- 최종 답에는 근거를 `경로:줄번호` 형식으로 적는다. 예: subtitle_corrector/engine/spacing.py:128
- 읽지 않은 파일이나 확인하지 않은 줄 번호를 적지 않는다. 모르면 모른다고 답한다.
- 도구가 오류를 돌려주면 인자를 고쳐 다시 시도한다. 같은 인자를 반복하지 않는다.
- 충분히 확인했으면 도구를 더 부르지 말고 최종 답을 낸다."""

WRITE_PROMPT_SUFFIX = """

쓰기와 테스트 실행이 열려 있다. 추가 규칙:
- 파일을 바꾸기 전에 반드시 read_file로 현재 내용을 확인한다. content에는 파일 전체를 넣는다.
- write_file로 새 파일을 만들 수도 있다. 다만 상위 폴더가 미리 있어야 하고, 새 디렉터리는 만들지 못한다.
- write_file·run_pytest·run_python은 사용자 승인을 받은 뒤에만 적용된다. 거절당하면 다시 같은 것을 요청하지 말고
  왜 필요한지 설명하거나 다른 방법을 제안한다.
- 고친 뒤에는 run_pytest로 확인한다. 테스트를 돌리지 않고 고쳤다고 말하지 않는다.
- 스크립트를 작성해 산출물을 만들어야 하면, 쓰기만으로 끝내지 말고 run_python으로 실제로 실행해 결과를 확인한다.
  run_python은 작업 폴더 안 기존 .py 파일 하나만 실행하며 인라인 코드나 셸 명령은 못 받는다."""


class Adapter(Protocol):
    """제공자 어댑터. 루프는 이 함수 하나만 안다."""

    def complete(self, messages: list[Message], tools: list[ToolSpec]) -> ModelReply: ...


@dataclass
class RunResult:
    status: str  # completed | failed
    reason: str | None
    final_text: str | None
    iterations: int
    elapsed_seconds: float
    session_id: str
    session_path: str
    messages: list[Message]


def run(
    request: str,
    *,
    guard: PathGuard,
    adapter: Adapter,
    registry: dict[str, Tool],
    recorder: SessionRecorder,
    approver: Approver | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    on_event: Any = None,
    history: list[Message] | None = None,
) -> RunResult:
    tools = [tool.spec for tool in registry.values()]
    # 승인자를 주지 않았는데 승인이 필요한 도구가 있으면 전부 거절한다.
    approver = approver or AlwaysReject()
    needs_write_prompt = any(tool.needs_approval for tool in registry.values())
    system_prompt = SYSTEM_PROMPT + (WRITE_PROMPT_SUFFIX if needs_write_prompt else "")
    messages: list[Message] = list(history) if history else [
        Message(role="system", content=system_prompt)
    ]
    messages.append(Message(role="user", content=request))

    started = time.monotonic()
    iteration = 0
    recent: list[str] = []

    def emit(text: str) -> None:
        if on_event:
            on_event(text)

    while True:
        elapsed = time.monotonic() - started
        if elapsed > max_seconds:
            return _finish(
                recorder, "failed", "time_limit", None, iteration, elapsed, messages,
                note=f"시간 상한 {max_seconds}초를 넘었습니다",
            )
        if iteration >= max_iterations:
            return _finish(
                recorder, "failed", "limit_reached", None, iteration, elapsed, messages,
                note=f"반복 상한 {max_iterations}회에 도달했습니다",
            )

        iteration += 1
        recorder.record(
            "model_request",
            iteration=iteration,
            message_count=len(messages),
            tool_names=[spec.name for spec in tools],
        )

        try:
            reply = _complete_with_retry(adapter, messages, tools)
        except AdapterError as exc:
            recorder.record("adapter_error", iteration=iteration, code=exc.code, message=exc.message)
            return _finish(
                recorder, "failed", exc.code, None, iteration,
                time.monotonic() - started, messages, note=exc.message,
            )

        recorder.record(
            "model_reply",
            iteration=iteration,
            text=reply.text,
            tool_calls=[_call_row(call) for call in reply.tool_calls],
            finish_reason=reply.finish_reason,
            usage=reply.usage,
        )
        messages.append(
            Message(role="assistant", content=reply.text, tool_calls=reply.tool_calls)
        )

        # 종료 조건: 도구 요청이 없으면 최종 답이다.
        if not reply.tool_calls:
            return _finish(
                recorder, "completed", None, reply.text, iteration,
                time.monotonic() - started, messages,
            )

        # 여러 요청은 받은 순서대로 하나씩. 하나가 실패해도 나머지를 실행한다.
        for call in reply.tool_calls:
            result = _execute(call, guard, registry, recorder, iteration, recent, approver, emit)
            emit(_progress_line(iteration, max_iterations, call, result))
            messages.append(
                Message(
                    role="tool",
                    content=json.dumps(result, ensure_ascii=False, default=str),
                    tool_call_id=call.id,
                )
            )


def _execute(
    call: ToolCall,
    guard: PathGuard,
    registry: dict[str, Tool],
    recorder: SessionRecorder,
    iteration: int,
    recent: list[str],
    approver: Approver,
    emit: Any,
) -> dict[str, Any]:
    recorder.record(
        "tool_call",
        iteration=iteration,
        tool_call_id=call.id,
        name=call.name,
        arguments=call.arguments if call.arguments is not None else call.raw_arguments,
    )

    if call.arguments is None:
        result = {
            "error": "bad_arguments",
            "message": "도구 인자가 JSON이 아니어서 실행하지 않았습니다",
            "received": call.raw_arguments[:200],
        }
        recorder.record("tool_result", iteration=iteration, tool_call_id=call.id, ok=False, error=result)
        return result

    tool = registry.get(call.name)
    if tool is None:
        result = {
            "error": "unknown_tool",
            "message": f"{call.name}은 없는 도구입니다",
            "available": sorted(registry),
        }
        recorder.record("tool_result", iteration=iteration, tool_call_id=call.id, ok=False, error=result)
        return result

    preview_obj: Preview | None = None
    if tool.needs_approval:
        outcome = _approve(call, tool, guard, recorder, iteration, approver, emit)
        if isinstance(outcome, dict):  # 검사 실패 또는 거절
            recorder.record(
                "tool_result", iteration=iteration, tool_call_id=call.id, ok=False, error=outcome
            )
            if outcome.get("error") in GUARD_ERRORS:
                recorder.record(
                    "guard_block",
                    iteration=iteration,
                    name=call.name,
                    arguments=call.arguments,
                    reason=outcome["error"],
                )
            return outcome
        preview_obj = outcome

    try:
        result = tool.run(guard, call.arguments, preview_obj)
    except Exception as exc:  # 도구 내부 오류로 반복 전체를 죽이지 않는다
        result = {"error": "tool_crashed", "message": f"{type(exc).__name__}: {exc}"}

    error_code = result.get("error") if isinstance(result, dict) else None
    if error_code in GUARD_ERRORS:
        recorder.record(
            "guard_block",
            iteration=iteration,
            name=call.name,
            arguments=call.arguments,
            reason=error_code,
        )

    # 같은 인자를 계속 부르면 진행이 없다는 사실을 결과에 덧붙인다.
    signature = f"{call.name}:{json.dumps(call.arguments, sort_keys=True, ensure_ascii=False, default=str)}"
    recent.append(signature)
    del recent[:-REPEAT_THRESHOLD]
    if len(recent) == REPEAT_THRESHOLD and len(set(recent)) == 1:
        result = dict(result)
        result["notice"] = (
            f"같은 인자로 {REPEAT_THRESHOLD}회 연속 호출했습니다. "
            "인자를 바꾸거나 지금까지 확인한 것으로 최종 답을 내세요."
        )

    recorder.record(
        "tool_result",
        iteration=iteration,
        tool_call_id=call.id,
        ok=error_code is None,
        result=_trim(result),
    )
    return result


def _approve(
    call: ToolCall,
    tool: Tool,
    guard: PathGuard,
    recorder: SessionRecorder,
    iteration: int,
    approver: Approver,
    emit: Any,
) -> Preview | dict[str, Any]:
    """적용 전에 보여 주고 승인을 받는다. 검사 실패나 거절이면 오류 dict를 돌려준다."""
    assert tool.preview is not None
    try:
        outcome = tool.preview(guard, call.arguments or {})
    except Exception as exc:
        return {"error": "tool_crashed", "message": f"{type(exc).__name__}: {exc}"}

    if isinstance(outcome, dict):  # 경로 이탈·없는 파일 등은 묻지 않고 바로 거부
        return outcome

    approval_id = uuid.uuid4().hex[:12]
    recorder.record("state", iteration=iteration, value="waiting_approval", approval_id=approval_id)
    recorder.record(
        "approval_request",
        iteration=iteration,
        approval_id=approval_id,
        tool_call_id=call.id,
        kind=outcome.kind,
        summary=outcome.summary,
        detail=outcome.detail,
        shown_hash=outcome.digest,
    )

    decided = bool(approver.ask(outcome))

    recorder.record(
        "approval",
        iteration=iteration,
        approval_id=approval_id,
        tool_call_id=call.id,
        decision="approve" if decided else "reject",
        shown_hash=outcome.digest,
    )
    recorder.record("state", iteration=iteration, value="running")

    if not decided:
        emit(f"[{iteration}] {call.name} 거절됨 — {outcome.summary}")
        return {
            "error": "rejected_by_user",
            "message": "사용자가 거절했습니다. 파일과 시스템은 바뀌지 않았습니다",
            "summary": outcome.summary,
        }
    return outcome


def _complete_with_retry(adapter: Adapter, messages: list[Message], tools: list[ToolSpec]) -> ModelReply:
    """재시도는 네트워크·5xx만. 재시도는 반복 횟수에 넣지 않는다."""
    delay = 1.0
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            return adapter.complete(messages, tools)
        except AdapterError as exc:
            if not exc.retryable or attempt == RETRY_LIMIT:
                raise
            time.sleep(delay)
            delay *= 2
    raise AdapterError("unreachable", "재시도 루프가 잘못되었습니다")


def _finish(
    recorder: SessionRecorder,
    status: str,
    reason: str | None,
    final_text: str | None,
    iterations: int,
    elapsed: float,
    messages: list[Message],
    note: str | None = None,
) -> RunResult:
    recorder.record(
        "session_end",
        status=status,
        reason=reason,
        iterations=iterations,
        elapsed_seconds=round(elapsed, 3),
        final_text=final_text,
        note=note,
    )
    return RunResult(
        status=status,
        reason=reason,
        final_text=final_text,
        iterations=iterations,
        elapsed_seconds=elapsed,
        session_id=recorder.session_id,
        session_path=str(recorder.path),
        messages=messages,
    )


def _call_row(call: ToolCall) -> dict[str, Any]:
    return {
        "id": call.id,
        "name": call.name,
        "arguments": call.arguments if call.arguments is not None else call.raw_arguments,
        "parsed": call.arguments is not None,
    }


def _trim(result: dict[str, Any], limit: int = 2000) -> dict[str, Any]:
    """기록이 파일 전체를 복사하지 않도록 긴 본문만 잘라 둔다."""
    trimmed = dict(result)
    content = trimmed.get("content")
    if isinstance(content, str) and len(content) > limit:
        trimmed["content"] = content[:limit]
        trimmed["content_truncated_in_log"] = True
    return trimmed


def _progress_line(iteration: int, max_iterations: int, call: ToolCall, result: dict[str, Any]) -> str:
    head = f"[{iteration}/{max_iterations}] {call.name}"
    if isinstance(result, dict) and result.get("error"):
        return f"{head} -> {result['error']}"
    if call.name == "read_file" and isinstance(result, dict) and "total_lines" in result:
        return (
            f"{head} {result['path']}:{result['start_line']}-{result['end_line']} "
            f"({result['total_lines']}줄 중)"
        )
    if call.name == "search_text" and isinstance(result, dict) and "total" in result:
        return f"{head} {len(result['matches'])}건 표시 / 전체 {result['total']}건"
    if call.name == "write_file" and isinstance(result, dict) and result.get("applied"):
        return f"{head} {result['path']} 적용 ({result['bytes']}바이트)"
    if call.name == "run_pytest" and isinstance(result, dict) and "exit_code" in result:
        return (
            f"{head} exit={result['exit_code']} "
            f"passed={result['passed']} failed={result['failed']}"
        )
    return head
