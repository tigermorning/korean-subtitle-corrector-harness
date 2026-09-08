"""경로 검사기.

INTERFACES.md "실행 도구 계약"의 경로 검사 규칙 1~4를 구현한다.
모델의 지시와 무관하게 코드에서 적용한다. 도구는 이 클래스를 거치지 않고 파일에 접근하지 않는다.

주의: 이것은 작업 폴더 제한이지 운영체제 샌드박스가 아니다.
같은 프로세스의 다른 코드가 이 검사를 우회할 수 있다.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_EXCLUDED = (".venv", ".git", "__pycache__", ".pytest_cache")


class PathRejected(Exception):
    """검사기가 막은 경로. code는 도구 결과의 error 값이 된다."""

    def __init__(self, code: str, message: str, **extra: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


class PathGuard:
    def __init__(self, root: str | Path, excluded: tuple[str, ...] = DEFAULT_EXCLUDED) -> None:
        resolved = Path(root).expanduser().resolve()
        if not resolved.is_dir():
            raise PathRejected(
                "root_not_a_directory",
                f"작업 폴더가 없거나 디렉터리가 아닙니다: {resolved}",
                root=str(resolved),
            )
        self.root = resolved
        self.excluded = excluded
        self._excluded_norm = {os.path.normcase(name) for name in excluded}
        self._root_norm = os.path.normcase(str(self.root))

    def resolve(self, path: str) -> Path:
        """작업 폴더 기준 경로를 실제 경로로 바꾸고 규칙 1~4를 적용한다.

        존재하지 않는 파일도 해석한다(없는 파일 판정은 도구가 한다).
        """
        if not isinstance(path, str) or not path.strip():
            raise PathRejected("invalid_argument", "path는 비어 있지 않은 문자열이어야 합니다", field="path")

        # 규칙 1·2: 실제 경로로 정규화한 뒤 기준의 하위인지 확인한다.
        # ..·절대 경로·symlink 탈출이 모두 여기서 걸린다.
        candidate = (self.root / path).resolve()
        if not self._is_within(candidate):
            raise PathRejected(
                "path_outside_root",
                "작업 폴더 밖의 경로입니다",
                root=str(self.root),
            )

        # 규칙 3: 경로 구성요소 중 하나라도 제외 목록에 걸리면 거부한다.
        for part in self._relative_parts(candidate):
            if os.path.normcase(part) in self._excluded_norm:
                raise PathRejected("path_excluded", "제외 패턴에 걸린 경로입니다", pattern=part)

        return candidate

    def is_allowed(self, real_path: Path) -> bool:
        """이미 실제 경로인 항목이 허용 범위인지 확인한다(검색이 훑을 때 사용)."""
        if not self._is_within(real_path):
            return False
        return not any(
            os.path.normcase(part) in self._excluded_norm for part in self._relative_parts(real_path)
        )

    def relative(self, real_path: Path) -> str:
        """보고용 상대 경로. 항상 슬래시로 표시해 OS에 따라 답이 갈리지 않게 한다."""
        return "/".join(self._relative_parts(real_path))

    def _is_within(self, candidate: Path) -> bool:
        # 규칙 4: Windows에서는 대소문자를 구분하지 않고 비교한다.
        target = os.path.normcase(str(candidate))
        if target == self._root_norm:
            return True
        return target.startswith(self._root_norm + os.sep)

    def _relative_parts(self, candidate: Path) -> tuple[str, ...]:
        # _is_within을 통과한 경로만 들어오므로 접두사 길이로 잘라낸다.
        # os.path.relpath는 대소문자가 다를 때 Windows에서 어긋날 수 있어 쓰지 않는다.
        tail = str(candidate)[len(str(self.root)) :].strip(os.sep).strip("/")
        if not tail:
            return ()
        return Path(tail).parts
