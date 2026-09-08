"""run_python 도구 — 정상 실행·승인 흐름·오류 구조.

2026-09-08 결정 변경(DECISIONS.md)으로 추가됨. 실제 모델을 부르지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.approval import ScriptedApprover
from harness.contracts import Preview
from harness.loop import run
from harness.paths import PathGuard
from harness.providers.mock_adapter import MockAdapter, final_reply, tool_reply
from harness.session import SessionRecorder, new_session_id
from harness.tools import READ_WRITE_TOOLS, run_python


@pytest.fixture()
def guard(tmp_path: Path) -> PathGuard:
    root = tmp_path / "work"
    root.mkdir()
    (root / "echo_args.py").write_text(
        "import sys\nprint('got:', sys.argv[1:])\n", encoding="utf-8"
    )
    (root / "writes_output.py").write_text(
        "from pathlib import Path\nPath('output.txt').write_text('done', encoding='utf-8')\n",
        encoding="utf-8",
    )
    (root / "not_a_script.txt").write_text("x", encoding="utf-8")
    return PathGuard(root)


def test_preview_rejects_missing_file(guard: PathGuard) -> None:
    outcome = run_python.preview(guard, {"path": "missing.py"})
    assert outcome["error"] == "not_found"


def test_preview_rejects_non_python_file(guard: PathGuard) -> None:
    outcome = run_python.preview(guard, {"path": "not_a_script.txt"})
    assert outcome["error"] == "invalid_argument"
    assert outcome["field"] == "path"


def test_preview_rejects_bad_args(guard: PathGuard) -> None:
    outcome = run_python.preview(guard, {"path": "echo_args.py", "args": "not-a-list"})
    assert outcome["error"] == "invalid_argument"
    assert outcome["field"] == "args"


def test_run_without_preview_is_refused(guard: PathGuard) -> None:
    outcome = run_python.run(guard, {"path": "echo_args.py"}, None)
    assert outcome["error"] == "approval_required"


def test_approved_run_executes_and_returns_output(guard: PathGuard) -> None:
    preview_obj = run_python.preview(guard, {"path": "echo_args.py", "args": ["a", "b"]})
    assert isinstance(preview_obj, Preview)
    assert preview_obj.kind == "exec"
    assert sys.executable in preview_obj.detail

    outcome = run_python.run(guard, {}, preview_obj)
    assert outcome["exit_code"] == 0
    assert "got: ['a', 'b']" in outcome["stdout_tail"]


def test_full_loop_writes_new_file_then_runs_it(guard: PathGuard, tmp_path: Path) -> None:
    """R08 A12에서 확인한 병목(쓰기는 되는데 실행이 안 됨)을 해소했는지 끝-끝으로 확인."""
    recorder = SessionRecorder(new_session_id(), tmp_path / "sessions")
    approver = ScriptedApprover([True])
    adapter = MockAdapter(
        [
            tool_reply("run_python", {"path": "writes_output.py"}),
            final_reply("실행해서 output.txt를 만들었습니다"),
        ]
    )

    result = run(
        "writes_output.py를 실행해줘",
        guard=guard,
        adapter=adapter,
        registry=READ_WRITE_TOOLS,
        recorder=recorder,
        approver=approver,
    )

    assert result.status == "completed"
    assert (guard.root / "output.txt").read_text(encoding="utf-8") == "done"


def test_rejected_run_does_not_execute(guard: PathGuard, tmp_path: Path) -> None:
    recorder = SessionRecorder(new_session_id(), tmp_path / "sessions")
    approver = ScriptedApprover([False])
    adapter = MockAdapter(
        [
            tool_reply("run_python", {"path": "writes_output.py"}),
            final_reply("거절되어 실행하지 않았습니다"),
        ]
    )

    result = run(
        "writes_output.py를 실행해줘",
        guard=guard,
        adapter=adapter,
        registry=READ_WRITE_TOOLS,
        recorder=recorder,
        approver=approver,
    )

    assert result.status == "completed"
    assert not (guard.root / "output.txt").exists()


def test_path_outside_root_is_refused_before_asking(guard: PathGuard) -> None:
    outcome = run_python.preview(guard, {"path": "../escape.py"})
    assert outcome["error"] == "path_outside_root"
