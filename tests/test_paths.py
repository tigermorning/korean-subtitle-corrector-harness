"""경로 검사기 — ACCEPTANCE.md A05 근거."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.paths import PathGuard, PathRejected


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "rules.py").write_text("a = 1\n", encoding="utf-8")
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / ".venv" / "lib" / "big.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("secret\n", encoding="utf-8")
    return root


def test_allows_file_inside_root(workspace: Path) -> None:
    guard = PathGuard(workspace)
    assert guard.resolve("pkg/rules.py").is_file()


def test_rejects_parent_escape(workspace: Path) -> None:
    guard = PathGuard(workspace)
    with pytest.raises(PathRejected) as info:
        guard.resolve("../outside.txt")
    assert info.value.code == "path_outside_root"


def test_rejects_absolute_path_outside(workspace: Path) -> None:
    guard = PathGuard(workspace)
    with pytest.raises(PathRejected) as info:
        guard.resolve(str(workspace.parent / "outside.txt"))
    assert info.value.code == "path_outside_root"


def test_rejects_excluded_directory(workspace: Path) -> None:
    guard = PathGuard(workspace)
    with pytest.raises(PathRejected) as info:
        guard.resolve(".venv/lib/big.py")
    assert info.value.code == "path_excluded"
    assert info.value.extra["pattern"] == ".venv"


def test_rejects_symlink_escape(workspace: Path) -> None:
    link = workspace / "link.txt"
    try:
        link.symlink_to(workspace.parent / "outside.txt")
    except (OSError, NotImplementedError):
        pytest.skip("이 환경에서는 symlink를 만들 수 없습니다")
    guard = PathGuard(workspace)
    with pytest.raises(PathRejected) as info:
        guard.resolve("link.txt")
    assert info.value.code == "path_outside_root"


@pytest.mark.skipif(os.name != "nt", reason="Windows 디렉터리 junction")
def test_rejects_junction_escape_on_windows(workspace: Path) -> None:
    """junction은 symlink와 달리 관리자 권한 없이 만들 수 있어 실제로 마주칠 수 있는 탈출로다."""
    import subprocess

    link = workspace / "link"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(workspace.parent)],
        capture_output=True,
    )
    if created.returncode != 0:
        pytest.skip("이 환경에서는 junction을 만들 수 없습니다")

    guard = PathGuard(workspace)
    with pytest.raises(PathRejected) as info:
        guard.resolve("link/outside.txt")
    assert info.value.code == "path_outside_root"


@pytest.mark.skipif(os.name != "nt", reason="Windows의 대소문자 무시 비교")
def test_case_insensitive_exclusion_on_windows(workspace: Path) -> None:
    guard = PathGuard(workspace)
    with pytest.raises(PathRejected) as info:
        guard.resolve(".VENV/lib/big.py")
    assert info.value.code == "path_excluded"


def test_is_allowed_matches_resolve(workspace: Path) -> None:
    guard = PathGuard(workspace)
    assert guard.is_allowed(workspace / "pkg" / "rules.py")
    assert not guard.is_allowed(workspace / ".venv" / "lib" / "big.py")
    assert not guard.is_allowed(workspace.parent / "outside.txt")


def test_relative_uses_forward_slashes(workspace: Path) -> None:
    guard = PathGuard(workspace)
    assert guard.relative(workspace / "pkg" / "rules.py") == "pkg/rules.py"


def test_missing_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(PathRejected) as info:
        PathGuard(tmp_path / "does-not-exist")
    assert info.value.code == "root_not_a_directory"
