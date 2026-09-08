"""도구 등록부.

1단계는 읽기 전용 두 개(D05). 2단계에서 승인이 필요한 두 개를 더한다.
승인 대상인지 여부는 도구 자신이 preview를 갖고 있는지로 정해진다.
루프가 도구 이름을 보고 판단하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..contracts import Preview, ToolSpec
from ..paths import PathGuard
from . import read_file, run_pytest, run_python, search_text, write_file

RunFn = Callable[..., dict[str, Any]]
PreviewFn = Callable[[PathGuard, dict[str, Any]], "Preview | dict[str, Any]"]

# 검사기가 막았다는 뜻의 error 코드. 루프가 guard_block 이벤트로 따로 기록한다.
GUARD_ERRORS = frozenset({"path_outside_root", "path_excluded"})


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    run: RunFn
    preview: PreviewFn | None = None  # None이면 승인 없이 바로 실행한다

    @property
    def needs_approval(self) -> bool:
        return self.preview is not None


def _entry(module, preview_fn=None) -> tuple[str, Tool]:
    return module.SPEC.name, Tool(spec=module.SPEC, run=module.run, preview=preview_fn)


READ_ONLY_TOOLS: dict[str, Tool] = dict(
    [_entry(read_file), _entry(search_text)]
)

READ_WRITE_TOOLS: dict[str, Tool] = dict(
    [
        _entry(read_file),
        _entry(search_text),
        _entry(write_file, write_file.preview),
        _entry(run_pytest, run_pytest.preview),
        _entry(run_python, run_python.preview),
    ]
)


def specs(registry: dict[str, Tool]) -> list[ToolSpec]:
    return [tool.spec for tool in registry.values()]
