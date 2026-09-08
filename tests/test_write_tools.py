"""쓰기·테스트 실행과 승인 흐름 — ACCEPTANCE.md A03·A04 근거.

실제 모델을 부르지 않는다. 모의 어댑터와 정해진 승인 답으로 하네스만 검증한다.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.approval import AlwaysReject, ConsoleApprover, ScriptedApprover
from harness.contracts import Preview
from harness.loop import run
from harness.paths import PathGuard
from harness.providers.mock_adapter import MockAdapter, final_reply, tool_reply
from harness.session import SessionRecorder, new_session_id, read_session
from harness.tools import READ_WRITE_TOOLS, run_pytest, write_file

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "spacing_rules"

FIXED_RULES = '''"""수정본."""

from __future__ import annotations

import re

UNITS = ("개", "명", "권", "번")

_PATTERN = re.compile(r"(\\d+)\\s+(" + "|".join(UNITS) + r")")


def fix_unit_spacing(text: str) -> str:
    return _PATTERN.sub(r"\\1\\2", text)
'''


@pytest.fixture()
def work(tmp_path: Path):
    """fixture 저장소를 복사해 쓴다. 원본은 건드리지 않는다."""
    root = tmp_path / "spacing_rules"
    shutil.copytree(FIXTURE, root)
    guard = PathGuard(root)
    recorder = SessionRecorder(new_session_id(), tmp_path / "sessions")
    return root, guard, recorder


def _tool_results(result) -> list[str]:
    return [message.content for message in result.messages if message.role == "tool"]


def test_a03_approved_write_then_pytest_passes(work) -> None:
    root, guard, recorder = work
    before = (root / "rules.py").read_text(encoding="utf-8")
    assert "것" in before  # 결함이 있는 상태에서 시작한다

    approver = ScriptedApprover([True, True])
    adapter = MockAdapter(
        [
            tool_reply("write_file", {"path": "rules.py", "content": FIXED_RULES, "why": "의존명사 오교정"}),
            tool_reply("run_pytest", {"test_path": "test_rules.py"}),
            final_reply("rules.py:8 의 UNITS에서 '것'을 빼고 수량만 매칭하도록 고쳤습니다"),
        ]
    )

    result = run(
        "테스트가 실패한다. 고쳐 줘",
        guard=guard,
        adapter=adapter,
        registry=READ_WRITE_TOOLS,
        recorder=recorder,
        approver=approver,
    )

    assert result.status == "completed"
    assert (root / "rules.py").read_text(encoding="utf-8") == FIXED_RULES

    results = _tool_results(result)
    assert '"applied": true' in results[0]
    assert '"exit_code": 0' in results[1]
    assert '"failed": 0' in results[1]

    # 승인 화면에는 diff와 실제 명령줄이 있어야 한다.
    assert approver.seen[0].kind == "write"
    assert "--- a/rules.py" in approver.seen[0].detail
    assert approver.seen[1].kind == "exec"
    assert "-m pytest" in approver.seen[1].detail
    assert str(guard.root) in approver.seen[1].detail

    events = read_session(recorder.path)
    decisions = [row["decision"] for row in events if row["event"] == "approval"]
    assert decisions == ["approve", "approve"]
    states = [row["value"] for row in events if row["event"] == "state"]
    assert states == ["waiting_approval", "running", "waiting_approval", "running"]


def test_a04_rejected_write_leaves_file_untouched(work) -> None:
    root, guard, recorder = work
    before = (root / "rules.py").read_bytes()

    approver = ScriptedApprover([False])
    adapter = MockAdapter(
        [
            tool_reply("write_file", {"path": "rules.py", "content": FIXED_RULES}),
            final_reply("거절되어 바꾸지 않았습니다"),
        ]
    )

    result = run(
        "고쳐 줘", guard=guard, adapter=adapter, registry=READ_WRITE_TOOLS,
        recorder=recorder, approver=approver,
    )

    assert (root / "rules.py").read_bytes() == before  # 바이트가 그대로다
    assert "rejected_by_user" in _tool_results(result)[0]
    assert result.status == "completed"  # 거절은 그 호출만 실패다. 반복은 계속된다

    events = read_session(recorder.path)
    assert [row["decision"] for row in events if row["event"] == "approval"] == ["reject"]


def test_write_outside_root_is_refused_before_asking(work) -> None:
    root, guard, recorder = work
    approver = ScriptedApprover([True])
    adapter = MockAdapter(
        [
            tool_reply("write_file", {"path": "../escape.py", "content": "x = 1"}),
            final_reply("막혔습니다"),
        ]
    )

    result = run(
        "상위 폴더에 써 줘", guard=guard, adapter=adapter, registry=READ_WRITE_TOOLS,
        recorder=recorder, approver=approver,
    )

    assert "path_outside_root" in _tool_results(result)[0]
    assert approver.seen == []  # 검사에서 걸린 것은 사용자에게 묻지도 않는다
    assert not (root.parent / "escape.py").exists()

    events = read_session(recorder.path)
    assert any(row["event"] == "guard_block" for row in events)


def test_write_creates_new_file_when_parent_exists(work) -> None:
    root, guard, _ = work
    preview_obj = write_file.preview(guard, {"path": "new_thing.py", "content": "x = 1"})
    assert isinstance(preview_obj, Preview)
    assert preview_obj.payload["is_new"] is True
    assert "/dev/null" in preview_obj.detail

    outcome = write_file.run(guard, {}, preview_obj)
    assert outcome["applied"] is True
    assert outcome["created"] is True
    assert (root / "new_thing.py").read_text(encoding="utf-8") == "x = 1"


def test_write_refuses_new_file_without_parent_folder(work) -> None:
    root, guard, _ = work
    outcome = write_file.preview(guard, {"path": "missing_dir/new_thing.py", "content": "x = 1"})
    assert outcome["error"] == "parent_missing"
    assert not (root / "missing_dir").exists()


def test_write_new_file_stale_if_created_meanwhile(work) -> None:
    root, guard, _ = work
    preview_obj = write_file.preview(guard, {"path": "new_thing.py", "content": "x = 1"})
    assert isinstance(preview_obj, Preview)

    # 승인 화면을 보여 준 뒤 다른 경로로 그 파일이 생겨 버렸다.
    (root / "new_thing.py").write_text("이미 누가 만들었다", encoding="utf-8")

    outcome = write_file.run(guard, {}, preview_obj)
    assert outcome["error"] == "stale_approval"
    assert (root / "new_thing.py").read_text(encoding="utf-8") == "이미 누가 만들었다"


def test_stale_approval_is_refused(work) -> None:
    root, guard, _ = work
    preview_obj = write_file.preview(guard, {"path": "rules.py", "content": FIXED_RULES})
    assert isinstance(preview_obj, Preview)

    # 보여 준 뒤 파일이 바뀌었다.
    (root / "rules.py").write_text("# 다른 사람이 먼저 고쳤다\n", encoding="utf-8")

    outcome = write_file.run(guard, {}, preview_obj)
    assert outcome["error"] == "stale_approval"
    assert (root / "rules.py").read_text(encoding="utf-8") == "# 다른 사람이 먼저 고쳤다\n"


def test_write_without_preview_is_refused(work) -> None:
    _, guard, _ = work
    outcome = write_file.run(guard, {"path": "rules.py", "content": "x = 1"}, None)
    assert outcome["error"] == "approval_required"


def test_no_change_is_reported(work) -> None:
    root, guard, _ = work
    same = (root / "rules.py").read_text(encoding="utf-8")
    outcome = write_file.preview(guard, {"path": "rules.py", "content": same})
    assert outcome["error"] == "no_change"


@pytest.mark.parametrize("bad", ["test_x; rm -rf /", "a && b", "$(whoami)", "x | y", "`id`"])
def test_pytest_select_whitelist(work, bad: str) -> None:
    _, guard, _ = work
    outcome = run_pytest.preview(guard, {"test_path": "test_rules.py", "test_name": bad})
    assert outcome["error"] == "invalid_argument"
    assert outcome["field"] == "test_name"


def test_pytest_path_outside_root(work) -> None:
    _, guard, _ = work
    outcome = run_pytest.preview(guard, {"test_path": "../../tests"})
    assert outcome["error"] == "path_outside_root"


def test_pytest_reports_failure_honestly(work) -> None:
    """고치기 전에 돌리면 실패가 실패로 보고돼야 한다."""
    _, guard, _ = work
    preview_obj = run_pytest.preview(guard, {"test_path": "test_rules.py"})
    assert isinstance(preview_obj, Preview)
    outcome = run_pytest.run(guard, {}, preview_obj)
    assert outcome["exit_code"] != 0
    assert outcome["failed"] == 1
    assert outcome["passed"] == 2


def test_default_approver_rejects(work) -> None:
    """승인자를 주지 않으면 쓰기가 통과하지 않는다."""
    root, guard, recorder = work
    before = (root / "rules.py").read_bytes()
    adapter = MockAdapter(
        [tool_reply("write_file", {"path": "rules.py", "content": FIXED_RULES}), final_reply("끝")]
    )

    result = run(
        "고쳐 줘", guard=guard, adapter=adapter, registry=READ_WRITE_TOOLS, recorder=recorder
    )

    assert "rejected_by_user" in _tool_results(result)[0]
    assert (root / "rules.py").read_bytes() == before


def test_console_approver_treats_eof_as_reject() -> None:
    import io

    approver = ConsoleApprover(stream=io.StringIO(""), prompt_stream=io.StringIO())
    preview_obj = Preview(kind="write", summary="s", detail="d", digest="h", payload={})
    assert approver.ask(preview_obj) is False


def test_console_approver_requires_explicit_yes() -> None:
    import io

    preview_obj = Preview(kind="write", summary="s", detail="d", digest="h", payload={})
    for answer, expected in [("y\n", True), ("yes\n", True), ("\n", False), ("n\n", False), ("ㅇ\n", False)]:
        approver = ConsoleApprover(stream=io.StringIO(answer), prompt_stream=io.StringIO())
        assert approver.ask(preview_obj) is expected


def test_always_reject_never_approves() -> None:
    preview_obj = Preview(kind="exec", summary="s", detail="d", digest="h", payload={})
    assert AlwaysReject().ask(preview_obj) is False
