"""반복 루프 — ACCEPTANCE.md A02·A05·A06·A07(a) 근거.

실제 모델을 부르지 않는다. 모의 어댑터로 하네스 자체만 검증한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.contracts import AdapterError, Message, ModelReply, ToolSpec
from harness.loop import run
from harness.paths import PathGuard
from harness.providers.mock_adapter import MockAdapter, final_reply, tool_reply
from harness.session import SessionRecorder, read_session
from harness.tools import READ_ONLY_TOOLS


@pytest.fixture()
def env(tmp_path: Path):
    root = tmp_path / "work"
    root.mkdir()
    (root / "rules.py").write_text("보조용언 규칙\n두 번째 줄\n", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("secret\n", encoding="utf-8")
    guard = PathGuard(root)
    recorder = SessionRecorder("test-session", tmp_path / "sessions")
    return guard, recorder


def _events(recorder: SessionRecorder) -> list[dict]:
    return read_session(recorder.path)


def test_a02_tool_call_then_finish(env) -> None:
    """도구 요청 → 인자 검사 → 실행 → tool_call_id 연결 → 종료."""
    guard, recorder = env
    adapter = MockAdapter(
        [
            tool_reply("read_file", {"path": "rules.py"}),
            final_reply("rules.py:1 에 있습니다"),
        ]
    )

    result = run(
        "규칙 위치는?",
        guard=guard,
        adapter=adapter,
        registry=READ_ONLY_TOOLS,
        recorder=recorder,
    )

    assert result.status == "completed"
    assert result.iterations == 2
    assert result.final_text == "rules.py:1 에 있습니다"

    tool_messages = [message for message in result.messages if message.role == "tool"]
    assistant_calls = [
        call for message in result.messages for call in message.tool_calls
    ]
    # 제공자가 준 id를 그대로 되돌려 준다. 하네스가 새로 만들지 않는다.
    assert tool_messages[0].tool_call_id == assistant_calls[0].id

    events = {row["event"] for row in _events(recorder)}
    assert {"model_request", "model_reply", "tool_call", "tool_result", "session_end"} <= events


def test_a05_guard_blocks_escape_and_loop_continues(env) -> None:
    """모델이 금지 경로를 요청해도 검사기가 막고 반복은 계속된다."""
    guard, recorder = env
    adapter = MockAdapter(
        [
            tool_reply("read_file", {"path": "../outside.txt"}),
            tool_reply("read_file", {"path": ".venv/x.py"}),
            final_reply("접근할 수 없었습니다"),
        ]
    )

    result = run("상위 폴더도 봐 줘", guard=guard, adapter=adapter, registry=READ_ONLY_TOOLS, recorder=recorder)

    assert result.status == "completed"  # 차단은 작업 실패가 아니다
    tool_messages = [message for message in result.messages if message.role == "tool"]
    assert "path_outside_root" in tool_messages[0].content
    assert "path_excluded" in tool_messages[1].content
    assert "secret" not in tool_messages[0].content

    blocks = [row for row in _events(recorder) if row["event"] == "guard_block"]
    assert [row["reason"] for row in blocks] == ["path_outside_root", "path_excluded"]


def test_a06_iteration_limit(env) -> None:
    guard, recorder = env
    adapter = MockAdapter([tool_reply("read_file", {"path": "rules.py"})], repeat_last=True)

    result = run(
        "계속 읽어",
        guard=guard,
        adapter=adapter,
        registry=READ_ONLY_TOOLS,
        recorder=recorder,
        max_iterations=3,
    )

    assert result.status == "failed"
    assert result.reason == "limit_reached"
    assert result.iterations == 3


def test_a07a_bad_arguments_not_executed(env) -> None:
    guard, recorder = env
    adapter = MockAdapter(
        [
            tool_reply("read_file", None, raw="{not json"),
            final_reply("인자를 고치지 못했습니다"),
        ]
    )

    result = run("읽어 줘", guard=guard, adapter=adapter, registry=READ_ONLY_TOOLS, recorder=recorder)

    tool_messages = [message for message in result.messages if message.role == "tool"]
    assert "bad_arguments" in tool_messages[0].content
    assert result.iterations == 2  # 실패한 호출도 반복 1회로 센다


def test_unknown_tool_is_reported_not_crashed(env) -> None:
    guard, recorder = env
    adapter = MockAdapter([tool_reply("delete_everything", {}), final_reply("없는 도구였습니다")])

    result = run("지워 줘", guard=guard, adapter=adapter, registry=READ_ONLY_TOOLS, recorder=recorder)

    tool_messages = [message for message in result.messages if message.role == "tool"]
    assert "unknown_tool" in tool_messages[0].content
    assert result.status == "completed"


def test_repeated_identical_call_gets_notice(env) -> None:
    guard, recorder = env
    adapter = MockAdapter([tool_reply("read_file", {"path": "rules.py"})], repeat_last=True)

    result = run(
        "계속 읽어",
        guard=guard,
        adapter=adapter,
        registry=READ_ONLY_TOOLS,
        recorder=recorder,
        max_iterations=4,
    )

    tool_messages = [message for message in result.messages if message.role == "tool"]
    assert "notice" in tool_messages[2].content


class _FlakyAdapter:
    """앞선 호출만 실패하는 어댑터. 재시도 정책 검증용."""

    def __init__(self, failures: int, retryable: bool) -> None:
        self.failures = failures
        self.retryable = retryable
        self.calls = 0

    def complete(self, messages: list[Message], tools: list[ToolSpec]) -> ModelReply:
        self.calls += 1
        if self.calls <= self.failures:
            raise AdapterError("network_error", "일시적 오류", retryable=self.retryable)
        return final_reply("복구했습니다")


def test_retryable_error_is_retried(env, monkeypatch) -> None:
    guard, recorder = env
    monkeypatch.setattr("harness.loop.time.sleep", lambda _seconds: None)
    adapter = _FlakyAdapter(failures=2, retryable=True)

    result = run("확인", guard=guard, adapter=adapter, registry=READ_ONLY_TOOLS, recorder=recorder)

    assert result.status == "completed"
    assert adapter.calls == 3
    assert result.iterations == 1  # 재시도는 반복 횟수에 넣지 않는다


def test_non_retryable_error_fails_fast(env) -> None:
    guard, recorder = env
    adapter = _FlakyAdapter(failures=5, retryable=False)

    result = run("확인", guard=guard, adapter=adapter, registry=READ_ONLY_TOOLS, recorder=recorder)

    assert result.status == "failed"
    assert result.reason == "network_error"
    assert adapter.calls == 1


def test_session_log_has_no_api_key(env, monkeypatch) -> None:
    guard, recorder = env
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-appear")
    adapter = MockAdapter([final_reply("끝")])

    run("확인", guard=guard, adapter=adapter, registry=READ_ONLY_TOOLS, recorder=recorder)

    assert "sk-should-never-appear" not in recorder.path.read_text(encoding="utf-8")
