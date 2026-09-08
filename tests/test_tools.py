"""도구 두 개의 정상 반환과 오류 구조."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.paths import PathGuard
from harness.tools import read_file, search_text


@pytest.fixture()
def guard(tmp_path: Path) -> PathGuard:
    root = tmp_path / "work"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "rules.py").write_text(
        "\n".join(f"line {n}" for n in range(1, 11)) + "\n", encoding="utf-8"
    )
    (root / "top.py").write_text("보조용언 붙여쓰기\n", encoding="utf-8")
    (root / "notes.md").write_text("보조용언 문서\n", encoding="utf-8")
    (root / ".venv").mkdir()
    (root / ".venv" / "big.py").write_text("보조용언 라이브러리\n", encoding="utf-8")
    return PathGuard(root)


def test_read_file_returns_range_and_total(guard: PathGuard) -> None:
    out = read_file.run(guard, {"path": "pkg/rules.py", "start_line": 3, "max_lines": 2})
    assert out["path"] == "pkg/rules.py"
    assert out["start_line"] == 3
    assert out["end_line"] == 4
    assert out["total_lines"] == 10
    assert out["truncated"] is True
    assert out["content"] == "line 3\nline 4"


def test_read_file_not_found(guard: PathGuard) -> None:
    assert read_file.run(guard, {"path": "pkg/none.py"})["error"] == "not_found"


def test_read_file_directory(guard: PathGuard) -> None:
    assert read_file.run(guard, {"path": "pkg"})["error"] == "not_a_file"


def test_read_file_path_outside_root(guard: PathGuard) -> None:
    assert read_file.run(guard, {"path": "../secret"})["error"] == "path_outside_root"


def test_read_file_excluded(guard: PathGuard) -> None:
    assert read_file.run(guard, {"path": ".venv/big.py"})["error"] == "path_excluded"


@pytest.mark.parametrize("bad", [0, -1, 501, "10", True])
def test_read_file_invalid_max_lines(guard: PathGuard, bad: object) -> None:
    out = read_file.run(guard, {"path": "pkg/rules.py", "max_lines": bad})
    assert out["error"] == "invalid_argument"
    assert out["field"] == "max_lines"


def test_search_matches_top_level_and_nested(guard: PathGuard) -> None:
    out = search_text.run(guard, {"pattern": "보조용언", "glob": "**/*.py"})
    paths = {match["path"] for match in out["matches"]}
    assert "top.py" in paths  # **/ 는 0개 디렉터리도 포함해야 한다
    assert "notes.md" not in paths  # glob이 .py로 걸렀다
    assert ".venv/big.py" not in paths  # 제외 디렉터리는 훑지 않는다


def test_search_reports_line_numbers(guard: PathGuard) -> None:
    out = search_text.run(guard, {"pattern": "line 7", "glob": "**/*.py"})
    assert out["matches"][0]["line"] == 7


def test_search_truncates_and_reports_total(guard: PathGuard) -> None:
    out = search_text.run(guard, {"pattern": "line", "glob": "pkg/*.py", "max_results": 3})
    assert len(out["matches"]) == 3
    assert out["total"] == 10
    assert out["truncated"] is True


def test_search_invalid_pattern(guard: PathGuard) -> None:
    assert search_text.run(guard, {"pattern": "("})["error"] == "invalid_pattern"


def test_search_rejects_escaping_glob(guard: PathGuard) -> None:
    out = search_text.run(guard, {"pattern": "x", "glob": "../*.py"})
    assert out["error"] == "invalid_argument"
    assert out["field"] == "glob"
